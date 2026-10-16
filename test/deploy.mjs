/**
 * Deploys every BackedBy contract to Studio Dev FROM HEAD.
 *
 *   node deploy.mjs [--set=final|smoke] [--reason="..."]
 *
 * The bytes sent are `git show HEAD:build/<File>.py`, never the working tree,
 * and the script refuses to run if contracts/ or build/ has uncommitted
 * changes or build/ is stale - so what is on chain is byte-identical to the
 * pushed commit. Order:
 *
 *   ChainReader                                   (shared by both registries)
 *   BackedByRegistry      CANONICAL  (6 h contest window)
 *   BackedByRegistryDemo  DEMO       (90 s contest window, short timeouts)
 *   CollateralGate        on CANONICAL, max age 24 h
 *   CollateralGateDemo    on DEMO, max age 30 min
 *
 * --set=smoke writes to deployments.smoke.json instead (throwaway probes).
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, fundOnStudio, deploy, argOf } from "./harness.mjs";

const root = new URL("..", import.meta.url).pathname;
const git = (...a) => execFileSync("git", ["-C", root, ...a]).toString();
if (git("status", "--porcelain", "contracts", "build").trim() !== "") {
  console.error("contracts/ or build/ has uncommitted changes; commit first"); process.exit(1);
}
execFileSync("python3", [root + "tools/build.py", "--check"], { stdio: "inherit" });
const head = git("rev-parse", "HEAD").trim();
const set = argOf("set", "final");
const only = argOf("only", null);
const chain = CHAINS.studiodev;
const acc = accounts();
const account = createAccount(acc.deployer.key);
const wallet = createClient({ chain, account });
const read = createClient({ chain });
await fundOnStudio(chain, account.address, 1000n * 10n ** 18n);
console.log(`deployer ${account.address}  HEAD ${head}  set ${set}`);

const path = new URL(set === "final" ? "../deployments.json" : `../deployments.${set}.json`, import.meta.url);
const doc = existsSync(path) ? JSON.parse(readFileSync(path, "utf8"))
  : { network: "studiodev", chain_id: 61997, rpc: "https://studio-dev.genlayer.com/api", explorer: "https://explorer-studio-dev.genlayer.com/", contracts: {} };
const persist = () => writeFileSync(path, JSON.stringify(doc, null, 2) + "\n");
const sha = (b) => createHash("sha256").update(b).digest("hex");

async function one(name, file, args, extra = {}) {
  const prev = doc.contracts[name];
  if (prev?.commit === head && prev?.address && !process.argv.includes("--force")) {
    console.log(`${name} already deployed from HEAD at ${prev.address}`);
    return prev.address;
  }
  const code = execFileSync("git", ["-C", root, "show", `HEAD:build/${file}.py`]);
  console.log(`\n${name}  build/${file}.py  args=${JSON.stringify(args)}  ${code.length} bytes  sha256 ${sha(code)}`);
  const res = await deploy({ chain, wallet, read, code: code.toString("utf8"), args, label: name });
  if (!res.ok) { console.error(`${name} FAILED`, res.out?.status, res.reason ?? "", res.out?.revertReason ?? "", res.out?.stderr?.slice(-2000) ?? ""); process.exit(1); }
  console.log(`  address ${res.address}`);
  if (prev?.address && prev.address !== res.address) {
    doc.superseded ??= [];
    doc.superseded.push({ name, ...prev, superseded_by: res.address, why: argOf("reason", "redeployed") });
  }
  doc.contracts[name] = { address: res.address, deploy_tx: res.hash, file: `build/${file}.py`, source: `contracts/${file}.py`,
    commit: head, bytes: code.length, sha256: sha(code), constructor_args: args, deployer: account.address,
    deployed_at: new Date().toISOString(), ...extra };
  persist();
  return res.address;
}

const cr = await one("ChainReader", "ChainReader", []);
if (only === "reader") process.exit(0);
const rc = set === "smoke" ? null : await one("BackedByRegistry", "BackedByRegistry", ["CANONICAL", cr], { mode: "CANONICAL" });
const rd = await one("BackedByRegistryDemo", "BackedByRegistry", ["DEMO", cr], { mode: "DEMO" });
if (rc) await one("CollateralGate", "CollateralGate", [rc, 86400], { mode: "CANONICAL" });
await one("CollateralGateDemo", "CollateralGate", [rd, 1800], { mode: "DEMO" });
console.log(`\nwrote ${path.pathname}`);
