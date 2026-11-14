/**
 * docs/MILESTONE.md below the BASE section: every milestone feature with links pinned to a commit, the compare link,
 * and test counts before (BASE) and after.
 *   node tools/milestone_md.mjs <FINAL commit>
 * The BASE section (written in step 0 by tools/base_proof.mjs) is kept as it is.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";

const root = new URL("..", import.meta.url).pathname;
const git = (...a) => execFileSync("git", ["-C", root, ...a]).toString().trim();
const FINAL = git("rev-parse", process.argv[2] ?? "HEAD");
const base = JSON.parse(readFileSync(root + "docs/base-proof.json", "utf8")).base;
const REPO = "https://github.com/kenil1710/backedby";
const L = (path, label, lines) => `[${label ?? path}](${REPO}/blob/${FINAL}/${path}${lines ? "#L" + lines : ""})`;
const line = (path, needle) => {
  const t = git("show", `${FINAL}:${path}`).split("\n");
  const i = t.findIndex((x) => x.includes(needle));
  if (i < 0) throw new Error(`${needle} not in ${path} at ${FINAL}`);
  return String(i + 1);
};
const at = (path, needle, label) => L(path, label ?? needle, line(path, needle));

// test counts at FINAL (this checkout must be FINAL)
const off = spawnSync("python3", ["-m", "unittest", "discover", "-p", "test_*.py"], { cwd: root + "test", encoding: "utf8" });
const py = Number(off.stderr.match(/Ran (\d+) tests/)?.[1] ?? 0);
const nodeCount = (f) => Number(spawnSync("node", ["--test", root + "test/" + f], { encoding: "utf8" }).stdout.match(/# pass (\d+)/)?.[1] ?? 0);
const pay = nodeCount("payout.test.mjs"), keep = nodeCount("keeper.test.mjs");
const dm = Number(spawnSync(root + ".venv-gl/bin/python", ["-m", "pytest", "tests/direct", "-q"], { cwd: root, encoding: "utf8" }).stdout.match(/(\d+) passed/)?.[1] ?? 0);
let e2e = 0;
try { e2e = JSON.parse(readFileSync(root + "docs/e2e/results.json", "utf8")).stats.expected; } catch { /* not run */ }

const F = [
  ["1. New bridge templates (LayerZero OFT, Wormhole, CCIP), each authenticated by the bridge's own config; real pairs read from two RPCs that must agree",
    [at("contracts/ChainReader.py", "def _auth_wormhole", "_auth_wormhole"), at("contracts/ChainReader.py", "def _auth_ccip", "_auth_ccip"), at("contracts/ChainReader.py", "def _auth_oft", "_auth_oft"),
      L("docs/feasibility-v2.json", "feasibility-v2.json (414/414 reads identical)"), L("docs/SEEDS.md", "SEEDS.md"), L("test/test_v2.py", "test_v2.py Wormhole/Ccip"), L("tests/direct/test_direct_reader.py", "Direct Mode")]],
  ["2. Auto-discovery and coverage: unlisted destinations named in every ruling, added by the keeper with proof, the rest shown",
    [at("contracts/ChainReader.py", "def lz_scan", "lz_scan"), at("contracts/ChainReader.py", "def ccip_scan", "ccip_scan"), at("contracts/BackedByRegistry.py", "def coverage_of", "coverage_of"),
      at("tools/lib/keeper_core.mjs", "discovery from the latest ruling's coverage", "keeper discovery"), at("tools/keeper.mjs", "async discover(p, id)", "discover()"), at("frontend/src/components/V2.tsx", "export function CoveragePanel", "CoveragePanel")]],
  ["3. Backing history and alerts: every FINAL ruling a point of a per-pair time series; ALERT within 10 bps of the tolerance line; charts",
    [at("contracts/BackedByRegistry.py", "def _history(", "_history"), at("contracts/BackedByRegistry.py", "def get_history(", "get_history"), at("contracts/BackedByRegistry.py", "def alert_state(", "alert_state"),
      at("frontend/src/components/V2.tsx", "export function HistoryChart", "HistoryChart")]],
  ["4. Over-backing explained from chain data",
    [L("tools/explain_surplus.mjs"), L("docs/surplus.json"), at("frontend/src/components/V2.tsx", "export function SurplusPanel", "SurplusPanel")]],
  ["5. Bounded recovery: transient reads PENDING, retried by anyone inside a window fixed at filing; validators derive the request from state",
    [at("contracts/ChainReader.py", "a transport failure (an RPC down", "PENDING path"), at("contracts/ChainReader.py", "READ_WINDOW_CLOSED_AT_", "fixed window"), at("contracts/BackedByRegistry.py", "the read window is fixed when the round opens", "read_by"),
      at("contracts/ChainReader.py", "def reading_agrees(", "reading_agrees"), at("test/test_v2.py", "class BoundedRecovery", "BoundedRecovery tests")]],
  ["6. CollateralGate: pair-bound interfaces, structured states, never favorable on missing, pending or stale data; copycat tests",
    [at("contracts/CollateralGate.py", "def bound_to(", "bound_to"), at("contracts/CollateralGate.py", "def gate_answer(", "gate_answer"), L("test/test_meaning.py", "test_meaning.py (Matrix, States, Copycats)")]],
  ["7. Keeper: durable checkpoints, paged reads from two endpoints with persisted cursors, idempotent, retry queue, FINALIZED + success + state verified, resume, hourly + 6-hourly",
    [L("tools/lib/keeper_core.mjs"), L("tools/keeper.mjs"), L(".github/workflows/keeper.yml"), L("test/keeper.test.mjs"), `[keeper-state branch](${REPO}/tree/keeper-state)`]],
  ["8. Payouts through external sends, each verified at the recipient; every v2 registry at eth_getBalance 0 after the demo",
    [at("contracts/BackedByRegistry.py", "def _send(", "_send"), L("tools/lib/payout.mjs"), L("docs/payouts.json"), L("docs/demo-run.log")]],
  ["9. Frontend: bounded pagination, caching, backoff, history charts, keeper page, /verify, /docs matching code",
    [at("frontend/src/lib/contract.ts", "async function backoff", "backoff"), at("frontend/src/lib/contract.ts", "export const MAX_PAGES", "bounded pages"), L("frontend/src/app/api/view/route.ts", "cached views"),
      L("frontend/src/app/keeper/page.tsx", "/keeper"), L("frontend/src/app/docs/page.tsx", "/docs"), "https://backedby-ledger.vercel.app"]],
  ["10. Chainlink Proof of Reserve next to the ratio: MATCH or DIFF with the delta, every DIFF explained",
    [at("contracts/ChainReader.py", "def por_read(", "por_read"), at("contracts/BackedByRegistry.py", "def por_compare(", "por_compare"), at("frontend/src/components/V2.tsx", "export function PorPanel", "PorPanel")]],
];

const old = readFileSync(root + "docs/MILESTONE.md", "utf8");
const baseSection = old.split("\n## Features")[0].trimEnd();
const md = `${baseSection}

## Features

FINAL is \`${FINAL}\`. Every link below is pinned to it.

Compare: ${REPO}/compare/${base}...${FINAL}

| Feature | Where (pinned to FINAL) |
|---|---|
${F.map(([f, ls]) => `| ${f} | ${ls.join(" · ")} |`).join("\n")}

Evidence: ${L("docs/FINAL_CHECK.md")} · ${L("docs/AUDIT.md")} · ${L("docs/REAL_WORLD_CHECK.md")} · ${L("docs/ATTACK_REPORT.md")} · ${L("docs/SEEDS.md")} · ${L("docs/e2e/README.md", "docs/e2e")}

## Tests

| Suite | BASE (\`${base.slice(0, 7)}\`) | FINAL (\`${FINAL.slice(0, 7)}\`) |
|---|---|---|
| Offline contract, rule, attack, meaning tests (Python, \`test/\`) | 467 | ${py} |
| Payout fee guard and delivery (node) | 12 | ${pay} |
| Keeper (node, offline) | 0 | ${keep} |
| GenLayer Direct Mode (\`tests/direct\`) | 0 | ${dm} |
| Playwright e2e on the live site | 0 | ${e2e} |
| **Total** | **479** | **${py + pay + keep + dm + e2e}** |
`;
writeFileSync(root + "docs/MILESTONE.md", md);
console.log(`MILESTONE.md at ${FINAL}: ${py} + ${pay} + ${keep} + ${dm} + ${e2e}`);
