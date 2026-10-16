/**
 * Seeds the CANONICAL registry with real authenticated pairs from
 * docs/FEASIBILITY.md: authenticate -> register -> monitoring check at freshly
 * pinned blocks -> read -> rule. Each ruling is then contestable for 6 h;
 * test/seed_finalize.mjs finalizes them after. Resumable: progress is kept
 * in docs/seed-canonical.json and every step is checked against contract state.
 *   node test/seed_canonical.mjs >> docs/seed-run.log
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { actor } from "../tools/lib/flow.mjs";
import { L1 } from "../tools/lib/bridges.mjs";

export const SEEDS = [
  ["arbitrum", "USDC", "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8", "USDC.e on Arbitrum"],
  ["arbitrum", "WBTC", "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f", "WBTC on Arbitrum"],
  ["arbitrum", "DAI", "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", "DAI on Arbitrum"],
  ["arbitrum", "wstETH", "0x5979d7b546e38e414f7e9822514be443a4800529", "wstETH on Arbitrum"],
  ["optimism", "USDC", "0x7f5c764cbc14f9669b88837ca1490cca17c31607", "USDC.e on OP Mainnet"],
  ["optimism", "WBTC", "0x68f180fcce6836688e9084f035309e29bf0a2095", "WBTC on OP Mainnet"],
  ["op_dai", "DAI", "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", "DAI on OP Mainnet"],
  ["base", "USDC", "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", "USDbC on Base"],
  ["base", "cbETH", "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22", "cbETH on Base"],
  ["polygon", "USDC", "0x2791bca1f2de4661ed88a30c99a7a9449aa84174", "USDC.e on Polygon"],
  ["polygon", "WBTC", "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6", "WBTC on Polygon"],
  ["polygon", "DAI", "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", "DAI on Polygon"],
  ["polygon", "USDT", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "USDT on Polygon"],
  ["nomad", "USDC", "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9", "madUSDC on Moonbeam (Nomad)"],
  ["nomad", "WETH", "0x30d2a9f5fdf90ace8c17952cbb4ee48a55d916a7", "madWETH on Moonbeam (Nomad)"],
  ["nomad", "WBTC", "0x1dc78acda13a8bc4408b207c9e48cdbc096d95e0", "madWBTC on Moonbeam (Nomad)"],
  ["nomad", "USDT", "0x8e70cd5b4ff3f62659049e74b6649c6603a0e594", "madUSDT on Moonbeam (Nomad)"],
  ["nomad", "DAI", "0xc234a67a4f840e61ade794be47de455361b52413", "madDAI on Moonbeam (Nomad)"],
];

if (process.argv[1].endsWith("seed_canonical.mjs")) {
  const path = new URL("../docs/seed-canonical.json", import.meta.url);
  const st = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : { seeds: {} };
  const save = () => writeFileSync(path, JSON.stringify(st, null, 2) + "\n");
  const a = actor({ role: "seeder", registry: "BackedByRegistry", log: (m) => console.log(m) });
  console.log(`\n=== seed run ${new Date().toISOString()}`);
  for (let pass = 1; pass <= 4; pass++) {
  const todo = SEEDS.filter(([, , , label]) => !["PROVISIONAL", "FINAL", "CONTESTED"].includes(st.seeds[label]?.status));
  if (todo.length === 0) break;
  console.log(`\n--- pass ${pass}: ${todo.length} to do`);
  for (const [kind, sym, l2, label] of todo) {
    const k = label;
    const s = (st.seeds[k] ??= { kind, sym, l1: L1[sym], l2, label });
    console.log(`\n== ${label}`);
    if (!s.pair_id) {
      const au = await a.authenticate(kind, L1[sym], l2);
      if (!au.auth_id) { console.log("  auth failed, skipping for now"); continue; }
      s.auth_id = au.auth_id; s.auth_tx = au.hash;
      const r = await a.register([au.auth_id], 0, label);
      if (!r.pair_id) { console.log("  register failed"); save(); continue; }
      s.pair_id = r.pair_id; s.register_tx = r.hash; save();
    }
    if (!s.check_id) {
      const pins = await a.pins(s.pair_id);
      const m = await a.monitor(s.pair_id, pins.blocks);
      if (!m.ok) { console.log("  monitor failed"); continue; }
      s.check_id = m.check_id; s.blocks = pins.blocks; s.monitor_tx = m.hash; save();
    }
    let c = await a.check(s.check_id);
    if (c.status === "OPEN") {
      const rd = await a.read(s.check_id);
      s.read_tx = rd.hash ?? s.read_tx;
      c = await a.rule(s.check_id);
    }
    s.status = c.status; s.verdict1 = c.verdict1; s.ratio_bps = c.ruling1?.ratio_bps; s.contest_deadline = c.contest_deadline;
    s.reason = c.reason || c.ruling1?.reason;
    save();
    console.log(`RESULT ${label}: check ${s.check_id} ${c.status} ${c.verdict1 || c.verdict} ratio_bps ${c.ruling1?.ratio_bps} ${c.reason || ""}`);
    if (c.status === "INCONCLUSIVE") { delete s.check_id; save(); }
  }
  }
}
