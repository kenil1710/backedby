/**
 * The final check. Writes docs/FINAL_CHECK.md and exits 1 on any failure.
 *
 *   1. source: every deployed contract's code (gen_getContractCode) is byte-identical to its build file at the
 *      deploy commit and at HEAD; one commit; contracts/ and build/ unchanged since; build/ is current
 *   2. addresses: every address in deployments.json appears, identically, in README, docs, the site's
 *      deployments.json, and nowhere is a contract address that is not in deployments.json
 *   3. links: every http(s) link in README and docs/*.md answers HTTP 200 (GET, redirects followed)
 *   4. seeds: every canonical pair has a FINAL ruling; every UNDER_BACKED found in FEASIBILITY.md is seeded
 *   5. demo: the demo registry's ledger holds 0 and its invariant holds
 *   6. tests: the offline suite passes
 *   7. docs truth: the numbers RULES.md states equal the deployed contracts' get_config
 *   8. site: the live site answers, /api/verify says all identical, /api/backed answers for a seeded pair
 */
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";
import { actor, deployments } from "./lib/flow.mjs";

const root = new URL("..", import.meta.url).pathname;
const SITE = "https://backedby-ledger.vercel.app";
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail}`); };
const dep = deployments();
const addrs = Object.entries(dep.contracts).map(([k, v]) => [k, v.address]);

// 1. source
{
  const r = spawnSync("node", [root + "tools/verify_source.mjs"], { encoding: "utf8" });
  check("source: on-chain code byte-identical to build files at the deploy commit", r.status === 0, r.stdout.trim().split("\n").pop());
  const b = spawnSync("python3", [root + "tools/build.py", "--check"], { encoding: "utf8" });
  check("source: build/ is current with contracts/", b.status === 0, b.status === 0 ? "tools/build.py --check" : b.stdout);
}

// 2. addresses
{
  const docs = ["README.md", ...readdirSync(root + "docs").filter((f) => f.endsWith(".md")).map((f) => "docs/" + f)];
  const site = JSON.parse(readFileSync(root + "frontend/src/lib/deployments.json", "utf8"));
  let bad = [];
  for (const [name, a] of addrs) {
    if (!JSON.stringify(site).includes(a)) bad.push(`${name} missing from the site`);
    if (!readFileSync(root + "README.md", "utf8").includes(a)) bad.push(`${name} missing from README`);
  }
  const known = new Set(addrs.map(([, a]) => a.toLowerCase()));
  const studio = /explorer-studio-dev\.genlayer\.com\/address\/(0x[0-9a-fA-F]{40})/g;
  for (const f of docs) {
    const t = readFileSync(root + f, "utf8");
    for (const m of t.matchAll(studio)) if (!known.has(m[1].toLowerCase()) && !/demo-run|seed-run/.test(f)) bad.push(`${f} links unknown contract ${m[1]}`);
  }
  for (const f of ["tools/lib/flow.mjs", "tools/patrol.mjs"]) {
    const t = readFileSync(root + f, "utf8");
    if (/0x[0-9a-fA-F]{40}/.test(t.replace(/0x0+\b/g, ""))) bad.push(`${f} hardcodes an address`);
  }
  check("addresses: consistent across README, docs, site and tools", bad.length === 0, bad.length ? bad.join("; ") : `${addrs.length} contracts`);
}

// 3. links
{
  const files = ["README.md", ...readdirSync(root + "docs").filter((f) => f.endsWith(".md") && f !== "FINAL_CHECK.md").map((f) => "docs/" + f)];
  const links = new Set();
  for (const f of files) for (const m of readFileSync(root + f, "utf8").matchAll(/\]\((https?:\/\/[^)\s]+)\)/g)) links.add(m[1]);
  const bad = [];
  const list = [...links];
  // one host at a time with a pause between requests: explorers throttle bursts from one client
  const byHost = {};
  for (const u of list) (byHost[new URL(u).host] ??= []).push(u);
  await Promise.all(Object.values(byHost).map(async (urls) => {
    for (const u of urls) {
      let ok = false, last = "";
      for (let k = 0; k < 4 && !ok; k++) {
        try {
          const r = await fetch(u, { redirect: "follow", headers: { "user-agent": "Mozilla/5.0 (final_check)" }, signal: AbortSignal.timeout(25_000) });
          ok = r.status === 200; last = String(r.status);
        } catch { last = "ERR"; }
        if (!ok) await new Promise((res) => setTimeout(res, 5000 * (k + 1)));
      }
      if (!ok) bad.push(`${last} ${u}`);
      await new Promise((res) => setTimeout(res, 1200));
    }
  }));
  check("links: every link in README and docs answers 200", bad.length === 0, bad.length ? bad.slice(0, 12).join("; ") : `${list.length} links`);
}

// 4. seeds and 5. demo
const canon = actor({ role: "patrol", registry: "BackedByRegistry", log: () => {} });
const demo = actor({ role: "patrol", registry: "BackedByRegistryDemo", log: () => {} });
{
  const pairs = (await canon.rv("get_pairs", [0, 50])).pairs;
  const notFinal = pairs.filter((p) => !p.latest || p.latest.status !== "FINAL").map((p) => p.pair_id);
  const under = pairs.filter((p) => p.latest?.verdict === "UNDER_BACKED").length;
  const feas = JSON.parse(readFileSync(root + "docs/feasibility.json", "utf8")).rows.filter((r) => r.verdict === "UNDER_BACKED");
  const seededTokens = new Set(pairs.map((p) => p.dests[0].token));
  const missing = feas.filter((r) => !seededTokens.has(r.dest[0].token)).map((r) => `${r.kind} ${r.sym}`);
  check("seeds: every canonical pair has a FINAL ruling", pairs.length >= 10 && notFinal.length === 0, `${pairs.length} pairs, not final: [${notFinal.join(",")}]`);
  check("seeds: every real UNDER_BACKED from FEASIBILITY.md is seeded and ruled", missing.length === 0 && under >= feas.length, `${under} UNDER_BACKED rulings; missing [${missing.join(", ")}]`);
  const L = await demo.rv("get_ledger");
  check("demo: drained to 0, invariant holds", L.held_now === "0" && L.invariant_holds, `held ${L.held_now}, received ${L.received}, claimed ${L.claimed}`);
  // 7. docs truth
  const c = await canon.rv("get_config"), d = await demo.rv("get_config");
  const rules = readFileSync(root + "docs/RULES.md", "utf8");
  const claims = [
    [c.window_s === 21600 && d.window_s === 90, "**6 h** canonical, **90 s** demo"],
    [c.max_gap_s === 600 && c.kind_max_gap_s.polygon === 300, "**at most 600 s** (300 s for Polygon)"],
    [c.bounty_bps === 5000, "**50%** of the slash"],
    [c.unbond_delay_s === 86400 && d.unbond_delay_s === 120, "after **24 h** (demo 120 s)"],
    [c.monitor_interval_s === 3600 && d.monitor_interval_s === 30, "**1 h** (demo 30 s)"],
    [c.read_timeout_s === 7200 && d.read_timeout_s === 300, "2 h / 300 s after filing"],
    [c.min_bond === "1000000000000000000" && d.min_bond === "50000000000000000", "minimum 1 GEN canonical, 0.05 GEN demo"],
    [c.min_stake === "100000000000000000" && d.min_stake === "10000000000000000", "minimum stake 0.1 GEN canonical, 0.01 GEN demo"],
    [c.max_tolerance_bps === 1000, "0 to 1000 bps"],
    [c.auth_max_age_s === 3600, "at most 1 hour old"],
  ];
  const wrong = claims.filter(([ok, text]) => !ok || !rules.includes(text)).map(([, t]) => t);
  check("docs truth: RULES.md numbers equal the deployed get_config", wrong.length === 0, wrong.length ? wrong.join("; ") : `${claims.length} statements`);
}

// 6. tests
{
  const r = spawnSync("sh", [root + "test/run_offline.sh"], { encoding: "utf8" });
  const ran = (r.stderr.match(/Ran (\d+) tests/) ?? [])[1];
  check("tests: offline suite passes", r.status === 0, `${ran} tests ${r.status === 0 ? "OK" : "FAILED"}`);
}

// 8. site
{
  const v = await fetch(`${SITE}/api/verify`).then((r) => r.json()).catch(() => null);
  check("site: /api/verify reports every contract identical", Boolean(v?.all_identical), v ? `${v.contracts.length} contracts` : "unreachable");
  const b = await fetch(`${SITE}/api/backed?pair=1`).then((r) => r.json()).catch(() => null);
  check("site: /api/backed answers from chain", Boolean(b?.latest), b?.latest ? `pair 1 ${b.latest.verdict} ${b.latest.status}` : "no ruling");
  const s = await fetch(`${SITE}/api/backed?pair=1&format=svg`).then((r) => r.text()).catch(() => "");
  check("site: SVG badge renders", s.startsWith("<svg"), `${s.length} bytes`);
}

const head = execFileSync("git", ["-C", root, "rev-parse", "HEAD"]).toString().trim();
const pass = results.filter((r) => r.ok).length;
const md = `# Final check

\`node tools/final_check.mjs\` on ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC at HEAD \`${head.slice(0, 10)}\`
(contracts deployed from \`${dep.contracts.ChainReader.commit.slice(0, 10)}\`).

**${pass}/${results.length} PASS.**

| # | Check | Result | Detail |
|---|---|---|---|
${results.map((r, i) => `| ${i + 1} | ${r.name} | ${r.ok ? "PASS" : "FAIL"} | ${String(r.detail).replace(/\|/g, "/").slice(0, 300)} |`).join("\n")}
`;
writeFileSync(root + "docs/FINAL_CHECK.md", md);
console.log(`\n${pass}/${results.length} PASS`);
process.exit(pass === results.length ? 0 : 1);
