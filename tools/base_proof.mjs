/**
 * BASE proof for the milestone: every v1 contract (the accepted deployment and
 * the two retired ones) is read back from Studio Dev with gen_getContractCode
 * and compared byte for byte with the build file at the commit that deployed
 * it, and with the same file at BASE. Every v1 registry's eth_getBalance is
 * read and recorded. Nothing is written on chain.
 *
 *   node tools/base_proof.mjs <BASE commit>     -> docs/base-proof.json, exit 1 on any mismatch
 */
import { writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";

const root = new URL("..", import.meta.url).pathname;
const BASE = process.argv[2];
if (!BASE) { console.error("usage: node tools/base_proof.mjs <BASE commit>"); process.exit(1); }
const RPC = "https://studio-dev.genlayer.com/api";
const show = (commit, path) => execFileSync("git", ["-C", root, "show", `${commit}:${path}`], { maxBuffer: 1 << 26 });
const sha = (b) => createHash("sha256").update(b).digest("hex");
const base = execFileSync("git", ["-C", root, "rev-parse", BASE]).toString().trim();

async function rpc(method, params) {
  for (let i = 0; ; i++) {
    try {
      const r = await fetch(RPC, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }), signal: AbortSignal.timeout(30000) });
      const j = await r.json();
      if (j.error) throw new Error(JSON.stringify(j.error).slice(0, 200));
      return j.result;
    } catch (e) { if (i >= 5) throw e; await new Promise((s) => setTimeout(s, 4000 * (i + 1))); }
  }
}
/** gen_getContractCode answers base64 of the deployed file. */
async function codeOf(address) {
  const r = await rpc("gen_getContractCode", [address]);
  return Buffer.from(String(r), "base64");
}

const sets = [
  { set: "accepted", doc: JSON.parse(show(base, "deployments.json")) },
  { set: "retired 6f9431f", doc: JSON.parse(show(base, "docs/superseded/6f9431f/deployments.json")) },
  { set: "retired e915d21", doc: JSON.parse(show(base, "docs/superseded/e915d21/deployments.json")) },
];
const out = { base, read_at: new Date().toISOString(), rpc: RPC, method: "gen_getContractCode", contracts: [], registries: [] };
let bad = 0;
const seen = new Set();
for (const { set, doc } of sets) {
  for (const [name, rec] of Object.entries(doc.contracts)) {
    if (seen.has(rec.address)) continue;
    seen.add(rec.address);
    const onChain = await codeOf(rec.address);
    const atDeploy = show(rec.commit, rec.file);
    const identical = onChain.equals(atDeploy);
    // the accepted set must also equal build/ at BASE itself (contracts/ and build/ untouched since the deploy commit)
    const atBase = set === "accepted" ? onChain.equals(show(base, rec.file)) : null;
    const row = { set, name, address: rec.address, deploy_commit: rec.commit, file: rec.file, bytes: onChain.length,
      sha256_on_chain: sha(onChain), sha256_build_at_deploy_commit: sha(atDeploy), identical_to_deploy_commit: identical,
      identical_to_base: atBase, recorded_sha256_matches: rec.sha256 ? rec.sha256 === sha(onChain) : null };
    if (!identical || atBase === false || row.recorded_sha256_matches === false) bad++;
    out.contracts.push(row);
    console.log(`${set.padEnd(16)} ${name.padEnd(21)} ${rec.address} ${onChain.length} bytes sha256 ${row.sha256_on_chain} ${identical ? "IDENTICAL" : "DIFFERS"}${atBase === null ? "" : atBase ? " (and to BASE)" : " (DIFFERS from BASE)"}`);
    if (name.startsWith("BackedByRegistry")) {
      const wei = BigInt(await rpc("eth_getBalance", [rec.address, "latest"]));
      out.registries.push({ set, name, address: rec.address, eth_getBalance_wei: wei.toString() });
      console.log(`${"".padEnd(16)} eth_getBalance ${wei} wei`);
    }
  }
}
out.all_identical = bad === 0;
writeFileSync(root + "docs/base-proof.json", JSON.stringify(out, null, 2) + "\n");
console.log(bad ? `${bad} MISMATCH` : "every v1 contract is byte-identical to its build file");
process.exit(bad ? 1 : 0);
