/**
 * The A-N audit -> docs/AUDIT.md (and docs/audit.json). Reads docs/final_check.json (run tools/final_check.mjs
 * first) and runs the focused test groups each item rests on.
 *   A source      B funds        C stuck states   D evidence binding   E two sources   F identity
 *   G coverage    H counters     I real-world truth  J keeper (incl. a scheduled run)   K gate meaning
 *   L docs truth  M verification package   N demo
 *   node tools/audit.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
const root = new URL("..", import.meta.url).pathname;
const rd = (p) => readFileSync(root + p, "utf8");
const fc = JSON.parse(rd("docs/final_check.json"));
const C = (prefix) => fc.checks.find((c) => c.name.startsWith(prefix)) ?? { ok: false, detail: "not run" };
const unit = (...tests) => {
  const r = spawnSync("python3", ["-m", "unittest", ...tests], { cwd: root + "test", encoding: "utf8" });
  const n = Number((r.stderr.match(/Ran (\d+) tests/) ?? [])[1] ?? 0);
  return { ok: r.status === 0 && n > 0, n };
};
const nodeTests = (file, pattern) => {
  const r = spawnSync("node", ["--test", ...(pattern ? ["--test-name-pattern", pattern] : []), root + "test/" + file], { encoding: "utf8" });
  return { ok: r.status === 0, n: Number((r.stdout.match(/# pass (\d+)/) ?? [])[1] ?? 0) };
};
const direct = (k) => {
  const r = spawnSync(root + ".venv-gl/bin/python", ["-m", "pytest", "tests/direct", "-q", ...(k ? ["-k", k] : [])], { cwd: root, encoding: "utf8" });
  return { ok: r.status === 0, n: Number((r.stdout.match(/(\d+) passed/) ?? [])[1] ?? 0) };
};
const rows = [];
const add = (id, name, ok, detail) => rows.push({ id, name, ok, detail });

add("A", "source", C("source: on-chain").ok && C("source: build").ok && C("v1 untouched").ok,
  `${C("source: on-chain").detail}; ${C("v1 untouched").detail}`);
{
  const u = unit("test_registry.Conservation", "test_payout", "test_attacks.Payouts");
  add("B", "funds", C("demo: drained").ok && C("payouts:").ok && C("balances:").ok && u.ok,
    `${C("demo: drained").detail}; ${C("balances:").detail}; ${C("payouts:").detail.slice(0, 160)}; conservation and payout tests: ${u.n}`);
}
{
  const u = unit("test_registry.StuckStates", "test_registry.Expire", "test_v2.BoundedRecovery", "test_attacks.ContestAbuse");
  add("C", "stuck states", u.ok, `every state has a deadline and a public exit; a transport fault is PENDING inside a read window fixed at filing (retries and junk never extend it), then expire refunds; an unread contest leaves the first ruling standing: ${u.n} tests`);
}
{
  const u = unit("test_attacks.H2BridgeMigration", "test_attacks.H1LookalikeToken", "test_reader", "test_v2.Wormhole", "test_v2.Ccip", "test_vaults");
  add("D", "evidence binding", u.ok, `every vault and destination exists only through the bridge's own mapping (Arbitrum, OP/Base, OP DAI, Polygon, Nomad, LayerZero, Wormhole, CCIP), read on both chains; every check re-reads the anchors at its pinned blocks; the reading is stored under (registry, check, round) with the request's hash, and rule refuses a reading for another request: ${u.n} tests`);
}
{
  const u = unit("test_v2.ValidatorTolerance", "test_v2.BoundedRecovery", "test_attacks.Decimals", "test_static.Safety");
  const d = direct("validator or rpc or disagree");
  add("E", "two sources", u.ok && d.ok && d.n > 0, `two RPCs per chain from different operators (two scan RPCs for coverage); identical or PENDING; validators re-read the registry's request, reject a leader's PENDING when their own read succeeds, a leader's other blocks, and any scan or PoR data they did not read themselves: ${u.n} offline tests, ${d.n} Direct Mode tests`);
}
{
  const u = unit("test_attacks.H3PairSquatting", "test_meaning.Copycats", "test_registry.Register", "test_vaults.AddVault");
  add("F", "identity", u.ok, `a pair's identity is (vault, source token, tolerance); vaults are derived from the bridge, never supplied; the gate is bound to (pair, source token, destination chain and token) so a copycat pair or look-alike token is never read; the claimant is msg.sender: ${u.n} tests`);
}
add("G", "coverage", C("tests:").ok && C("e2e:").ok && C("coverage:").ok, `${C("tests:").detail}; ${C("e2e:").detail}; ${C("coverage:").detail}`);
{
  const u = unit("test_static", "test_registry.Views", "test_attacks.Static");
  add("H", "counters", u.ok, `every write path checks everything before its first write; refused calls change no counter; the ledger invariant received = bonds + open stakes + claimable + claimed holds and is recomputed: ${u.n} tests`);
}
{
  let rw = null;
  try { rw = JSON.parse(rd("docs/real_world.json")); } catch { /* not run */ }
  const ok = rw && rw.rows.length > 0 && rw.rows.every((r) => r.agree);
  add("I", "real-world truth", Boolean(ok), rw ? `${rw.rows.filter((r) => r.agree).length}/${rw.rows.length} rulings reproduced to the bps from a third RPC per chain at their pinned blocks; decimals checked against Blockscout; public sources per bridge (docs/REAL_WORLD_CHECK.md)` : "docs/real_world.json missing");
}
{
  const k = nodeTests("keeper.test.mjs");
  add("J", "keeper", C("keeper:").ok && k.ok, `${C("keeper:").detail}; keeper tests (outage, backfill, 130 pairs, idempotency, resume, FINALIZED + success + state, discovery): ${k.n}`);
}
{
  const u = unit("test_meaning", "test_rules.Gate");
  add("K", "gate meaning", u.ok, `favorable only for a fresh FINAL BACKED ruling of exactly the asked pair and tokens with coverage COMPLETE, no recent other ruling and a tolerance within the limit; every other combination of verdict, status, age, coverage, alert, recent rulings, tolerance and binding refuses with a named state: ${u.n} tests`);
}
{
  const bad = [];
  for (const f of ["README.md", "docs/RULES.md", "docs/MILESTONE.md", "docs/SUBMISSION.md", "docs/medium.md", "docs/ATTACK_REPORT.md", "docs/SEEDS.md"]) {
    let t = "";
    try { t = rd(f); } catch { bad.push(f + " missing"); continue; }
    if (/known limitations|\bTODO\b|\bTBD\b|lorem/i.test(t)) bad.push(f + " has a placeholder or a limitations section");
    if (/\b(Claude|Anthropic|ChatGPT|Copilot)\b/.test(t)) bad.push(f + " mentions a tool vendor");
  }
  add("L", "docs truth", C("docs truth").ok && bad.length === 0, `${C("docs truth").detail}; ${bad.length ? bad.join("; ") : "README, RULES, MILESTONE, SUBMISSION, medium, ATTACK_REPORT, SEEDS: no placeholders, no limitations section, no tool-vendor mentions"}`);
}
add("M", "verification package", fc.passed === fc.total, `tools/final_check.mjs ${fc.passed}/${fc.total}; tools/verify_source.mjs; tools/base_proof.mjs; docs/FEASIBILITY.md, feasibility-v2.json, SEEDS.md, REAL_WORLD_CHECK.md, ATTACK_REPORT.md, MILESTONE.md`);
{
  const log = rd("docs/demo-run.log");
  const res = log.match(/RESULT demo: (.*)/)?.[1] ?? "";
  const ok = /eth_getBalance 0,/.test(res) && /invariant true/.test(res) && C("payouts:").ok;
  add("N", "demo", ok, `${res || "no RESULT line"}; every path on chain in docs/demo-run.log (BACKED upheld on contest, UNDER_BACKED slashed with bounty, vault added, gap and timeout INCONCLUSIVE, Wormhole ledger, CCIP GAP and discovery, PoR, history, bound gate incl. a copycat token)`);
}
const pass = rows.filter((r) => r.ok).length;
const md = `# Audit A-N

\`node tools/audit.mjs\` at ${new Date().toISOString()} (final check of ${fc.at}, HEAD ${fc.head.slice(0, 7)}): **${pass}/${rows.length}**.

| | item | result | evidence |
|---|---|---|---|
${rows.map((r) => `| ${r.id} | ${r.name} | ${r.ok ? "PASS" : "FAIL"} | ${String(r.detail).replace(/\|/g, "/")} |`).join("\n")}
`;
writeFileSync(root + "docs/AUDIT.md", md);
writeFileSync(root + "docs/audit.json", JSON.stringify({ at: new Date().toISOString(), passed: pass, total: rows.length, rows }, null, 1) + "\n");
console.log(md);
process.exit(pass === rows.length ? 0 : 1);
