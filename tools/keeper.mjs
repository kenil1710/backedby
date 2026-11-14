/**
 * The keeper bot (GitHub Actions, hourly and 6-hourly; runnable by hand). For
 * the v2 registries in deployments.json (canonical and demo): files monitoring
 * checks, reads (retrying PENDING reads inside their window), rules,
 * finalizes and expires checks, and adds the destinations a vault's own
 * bridge config names but its pair does not list. Logic: tools/lib/keeper_core.mjs.
 *
 *   node tools/keeper.mjs --state=<dir> [--push] [--contracts=BackedByRegistry,BackedByRegistryDemo] [--max=30] [--settle=600]
 *
 * State lives in <dir>/keeper-state-<Contract>-<address>.json: in CI <dir> is a
 * worktree of the `keeper-state` branch and every checkpoint is committed there
 * (and pushed with --push), so a run that dies resumes from its stored
 * transaction hashes and cursors. <dir>/status.json is what the site's /keeper
 * page shows. The signer is BACKEDBY_KEEPER_KEY (CI secret) or the keeper role
 * in test/.accounts.json.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { CHAINS as STUDIO, accounts, fundOnStudio, outcomeOf, retry, argOf, sleep, returnedJson, estimateWriteFees } from "../test/harness.mjs";
import { runKeeper, totals } from "./lib/keeper_core.mjs";
import { CHAINS } from "./lib/bridges.mjs";
import { CCIP } from "./lib/v2const.mjs";
import { rpc, pad } from "./lib/evm.mjs";
import { pinBlocks } from "./lib/pin.mjs";

const { createClient, createAccount } = createRequire(new URL("../test/package.json", import.meta.url))("genlayer-js");
const root = new URL("..", import.meta.url).pathname;
const dir = argOf("state", root + "state").replace(/\/$/, "");
const push = process.argv.includes("--push");
mkdirSync(dir, { recursive: true });
const dep = JSON.parse(readFileSync(root + "deployments.json", "utf8")).contracts;
const only = (argOf("contracts", "") || "BackedByRegistry,BackedByRegistryDemo").split(",");
const targets = only.filter((n) => dep[n]).map((n) => ({ name: n, address: dep[n].address }));
const READER = dep.ChainReader.address;

const key = accounts().keeper?.key;
if (!key) { console.error("no keeper key (BACKEDBY_KEEPER_KEY or test/.accounts.json)"); process.exit(1); }
const account = createAccount(key);
const wallet = createClient({ chain: STUDIO.studiodev, account });
// two read endpoints: Studio itself and the site's relay to it; a page counts only when both return it identically
const RELAY = process.env.BACKEDBY_RELAY ?? "https://backedby-ledger.vercel.app/api/rpc";
const readers = [createClient({ chain: STUDIO.studiodev }),
  createClient({ chain: { ...STUDIO.studiodev, rpcUrls: { ...STUDIO.studiodev.rpcUrls, default: { ...STUDIO.studiodev.rpcUrls.default, http: [RELAY] } } } })];
await fundOnStudio(STUDIO.studiodev, account.address, 50n * 10n ** 18n);
const plain = (v) => JSON.parse(JSON.stringify(v, (k, x) => (typeof x === "bigint" ? x.toString() : x instanceof Map ? Object.fromEntries(x) : x)));
const asObj = (v) => plain(typeof v === "string" ? JSON.parse(v) : v);

const git = (...a) => execFileSync("git", ["-C", dir, ...a], { stdio: ["ignore", "pipe", "pipe"] }).toString();
const isRepo = existsSync(dir + "/.git");
let lastPush = 0;
function commit(files, why, force = false) {
  if (!isRepo) return;
  try {
    git("add", ...files);
    if (git("status", "--porcelain").trim() === "") return;
    git("-c", "user.name=backedby-keeper", "-c", "user.email=keeper@users.noreply.github.com", "commit", "-qm", "keeper: " + why);
    if (push && (force || why.includes("submitted") || Date.now() - lastPush > 30_000)) { git("push", "-q", "origin", "HEAD:keeper-state"); lastPush = Date.now(); }
  } catch (e) { console.log("  state commit/push failed: " + String(e.message).slice(0, 160)); }
}

// --- chains: two RPCs per chain for heads, the bridge's own config for discovery
const LZ_CHAIN = { 30109: "polygon", 30110: "arbitrum", 30111: "optimism", 30184: "base", 30181: "mantle", 30274: "xlayer", 30280: "sei",
  30295: "flare", 30316: "hedera", 30320: "unichain", 30322: "morph", 30339: "ink", 30362: "berachain", 30367: "hyperevm", 30390: "monad" };
const CCIP_CHAIN = Object.fromEntries(Object.entries(CCIP.dests).map(([c, [s]]) => [s, c]));
async function both(chainName, to, data) {
  const out = [];
  for (const u of CHAINS[chainName].rpcs) out.push(await rpc(u, "eth_call", [{ to, data }, "finalized"]));
  if (out[0] !== out[1]) throw new Error(`${chainName}: the two RPCs disagree`);
  return out[0];
}
const chain = {
  async pins(p) {
    const dests = [...new Set(p.dests.map((d) => d.chain))];
    for (const c of ["ethereum", ...dests]) {
      for (const u of CHAINS[c].rpcs) await rpc(u, "eth_getBlockByNumber", ["finalized", false]);   // both must answer
    }
    const r = await pinBlocks("ethereum", dests, { margin: 90 });
    return Object.fromEntries(Object.entries(r.blocks).map(([c, b]) => [c, b.number]));
  },
  async discover(p, id) {
    const [fam, num] = id.split(":");
    const vault = (p.vaults ?? []).find((v) => v.family === (fam === "lz" ? "LZ" : "CCIP"))?.vault;
    if (!vault) return { unmatched: "no vault of that bridge in the pair" };
    if (fam === "lz") {
      const c = LZ_CHAIN[num];
      if (!c) return { unmatched: `LayerZero eid ${num} is not a chain BackedBy reads from two RPCs` };
      const peer = await both("ethereum", vault, "0xbb0b6a53" + BigInt(num).toString(16).padStart(64, "0"));
      return { kind: "oft_" + c, l1: p.source_token, l2: "0x" + peer.slice(26, 66) };
    }
    if (fam === "ccip") {
      const c = CCIP_CHAIN[num];
      if (!c) return { unmatched: `CCIP chain selector ${num} is not a chain BackedBy reads from two RPCs` };
      const r = await both("ethereum", vault, "0xb7946580" + BigInt(num).toString(16).padStart(64, "0"));
      return { kind: "ccip_" + c, l1: p.source_token, l2: "0x" + r.slice(r.length - 40) };
    }
    return { unmatched: "unknown id " + id };
  },
};

function regFor(address) {
  const view = (to, fn, args, i = 0) => retry(() => readers[i].readContract({ address: to, functionName: fn, args }), { label: fn }).then(asObj);
  const FN = { MONITOR: [address, "monitor"], READ: [READER, "read_check"], RULE: [address, "rule"], FINALIZE: [address, "finalize"],
    EXPIRE: [address, "expire"], AUTH: [READER, "authenticate"], ADD: [address, "add_destination"] };
  return {
    now: () => Math.floor(Date.now() / 1000),
    endpoints: 2,
    page: (e, off, lim) => view(address, "get_pairs", [off, lim], e),
    getPair: (id) => view(address, "get_pair", [id]),
    getCheck: (id) => view(address, "get_check", [id]),
    getReading: (cid, rnd) => view(READER, "get_reading", [address, cid, rnd]),
    getAuth: (id) => view(READER, "get_auth", [id]),
    config: null,
    async submit(kind, args) {
      const [to, fn] = FN[kind];
      const a = kind === "READ" ? [address, ...args] : args;
      const fees = await estimateWriteFees(wallet, { address: to, functionName: fn, args: a });
      return retry(() => wallet.writeContract({ address: to, functionName: fn, args: a, value: 0n, ...(fees ? { fees } : {}) }), { label: fn });
    },
    async getTx(hash) {
      const tx = await retry(() => readers[0].getTransaction({ hash }), { attempts: 4, label: "poll" }).catch(() => null);
      if (!tx) return null;
      const o = outcomeOf(tx);
      return { statusName: o.status, ok: o.ok, reason: o.revertReason, returned: returnedJson(o) };
    },
    sleep,
  };
}

let prev = {};
try { prev = JSON.parse(readFileSync(`${dir}/status.json`, "utf8")).contracts ?? {}; } catch { /* first run */ }
const status = { keeper: account.address, started_at: new Date().toISOString(), contracts: { ...prev } };
for (const { name, address } of targets) {
  const file = `${dir}/keeper-state-${name}-${address.slice(0, 10).toLowerCase()}.json`;
  const store = {
    async load() {
      if (!existsSync(file)) return null;
      const s = JSON.parse(readFileSync(file, "utf8"));
      return s.address && s.address.toLowerCase() !== address.toLowerCase() ? null : s;
    },
    async save(state, why) {
      state.contract = name; state.address = address; state.keeper = account.address; state.saved_at = new Date().toISOString();
      writeFileSync(file, JSON.stringify(state, null, 1) + "\n");
      commit([file.slice(dir.length + 1)], `${name} ${why}`, why === "run finished");
    },
  };
  const reg = regFor(address);
  reg.config = await retry(() => readers[0].readContract({ address, functionName: "get_config", args: [] })).then(asObj);
  console.log(`keeper ${account.address}  ${name} ${address}  state ${file}${isRepo ? " (git)" : ""}`);
  const { run, state } = await runKeeper({ reg, chain, store, log: (l) => console.log("  " + l),
    maxActions: Number(argOf("max", "30")), settleMs: Number(argOf("settle", "600")) * 1000, rounds: Number(argOf("rounds", "3")) });
  console.log(`  run: resumed ${run.resumed}, pairs ${run.pairs}, pages ${run.pages} (failed ${run.pages_failed}), pins failed ${run.pins_failed}, queued ${run.queued}, submitted ${run.submitted}, done ${run.done}, already ${run.already}, pending ${run.pending}, retry ${run.retry}, failed ${run.failed}, unmatched ${run.unmatched}`);
  for (const u of state.unprocessed) console.log(`  unprocessed ${u.key}: ${u.why}`);
  status.contracts[name] = { address, last_run: run, totals: totals(state), pairs: state.pairs, unmatched: state.unmatched, unprocessed: state.unprocessed,
    actions: Object.values(state.actions).slice(-300).map((a) => ({ key: a.key, kind: a.kind, pair_id: a.pair_id, status: a.status, result: a.result ?? "",
      tx: a.tx ?? a.tx_history?.at(-1) ?? "", attempts: a.attempts, last_error: a.last_error ?? "" })) };
}
status.finished_at = new Date().toISOString();
status.trigger = process.env.GITHUB_EVENT_NAME ?? "manual";
status.run_url = process.env.GITHUB_RUN_ID ? `https://github.com/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}` : "";
let hist = [];
try { hist = JSON.parse(readFileSync(`${dir}/status.json`, "utf8")).history ?? []; } catch { /* first run */ }
status.history = [...hist, { started_at: status.started_at, finished_at: status.finished_at, trigger: status.trigger, run_url: status.run_url,
  runs: Object.fromEntries(Object.entries(status.contracts).map(([n, c]) => [n, { submitted: c.last_run.submitted, done: c.last_run.done, pages: c.last_run.pages, pages_failed: c.last_run.pages_failed }])) }].slice(-100);
writeFileSync(`${dir}/status.json`, JSON.stringify(status, null, 1) + "\n");
commit(["status.json"], "status", true);
