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
import { L1, USDT0_DESTS } from "../tools/lib/bridges.mjs";

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
  ["polygon", "USDT", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "USDT on Polygon",
    // minted by the PoS bridge AND by USDT0's LayerZero adapter: both vaults, and the adapter's other readable tokens
    { vaults: [["oft_polygon", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"]],
      dests: USDT0_DESTS }],
  ["nomad", "USDC", "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9", "madUSDC on Moonbeam (Nomad)"],
  ["nomad", "WETH", "0x30d2a9f5fdf90ace8c17952cbb4ee48a55d916a7", "madWETH on Moonbeam (Nomad)"],
  ["nomad", "WBTC", "0x1dc78acda13a8bc4408b207c9e48cdbc096d95e0", "madWBTC on Moonbeam (Nomad)"],
  ["nomad", "USDT", "0x8e70cd5b4ff3f62659049e74b6649c6603a0e594", "madUSDT on Moonbeam (Nomad)"],
  ["nomad", "DAI", "0xc234a67a4f840e61ade794be47de455361b52413", "madDAI on Moonbeam (Nomad)"],
  // v2: Wormhole (vault: Portal's token bridge, ledger outstandingBridged), CCIP lock-release pools, LayerZero OFT adapters
  ["wh_polygon", "USDC", "0x4318cb63a2b8edf2de971e2f17f77097e499459d", "USDC through Wormhole (Portal)", { dests: [["wh_arbitrum", "0xc96f2715e2a242d50d1b0bc923dbe1740b8ecf18"], ["wh_optimism", "0x711e53d031ea9b0bb0c24dd506df11b41aea419e"], ["wh_base", "0xec267c53f53807c2337c257f8ac3fc3cc07cc0ed"]] }],
  ["wh_polygon", "WETH", "0x11cd37bb86f65419713f30673a480ea33c826872", "WETH through Wormhole (Portal)", { dests: [["wh_arbitrum", "0xd8369c2eda18dd6518eabb1f85bd60606deb39ec"], ["wh_optimism", "0xb47bc3ed6d70f04fe759b2529c9bc7377889678f"], ["wh_base", "0x71b35ecb35104773537f849fbc353f81303a5860"]] }],
  ["wh_polygon", "USDT", "0x9417669fbf23357d2774e9d421307bd5ea1006d2", "USDT through Wormhole (Portal)", { dests: [["wh_arbitrum", "0xe4728f3e48e94c6da2b53610e677cc241dafb134"], ["wh_optimism", "0xf6b4185fcf8af291c0e3927fbeab7046b4f6a8ca"], ["wh_base", "0xff0c62a4979400841efaa6faadb07ac7d5c98b27"]] }],
  ["wh_polygon", "WBTC", "0x5d49c278340655b56609fdf8976eb0612af3a0c3", "WBTC through Wormhole (Portal)", { dests: [["wh_arbitrum", "0x397846a8078d4845c7f5c6ca76aebbcfdc044fae"], ["wh_optimism", "0xb214c19d81c99e75e84706a3aa0a757319023e26"], ["wh_base", "0xe6396f780b543df16ee3b784d789c75b68319db0"]] }],
  ["wh_polygon", "DAI", "0x732eb1747eccfc431ff19bc359ffc83755b1918c", "DAI through Wormhole (Portal)", { dests: [["wh_arbitrum", "0x5c4f2fefb97f7df09e762d95c83f0ccf8bce8234"], ["wh_optimism", "0x098ea47d630b46df1e08e389e5e4466119c7dd30"], ["wh_base", "0x617edadb51bfb43a44bb91c7402129c23ba52381"]] }],
  ["ccip_arbitrum", "GHO", "0x7dff72693f6a4149b17e7c6314655f6a9f7c8b33", "GHO through Chainlink CCIP", { l1: "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", dests: [["ccip_base", "0x6bb7a212910682dcfdbd5bcbb3e28fb4e8da10ee"], ["ccip_ink", "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73"], ["ccip_mantle", "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73"], ["ccip_xlayer", "0xde6539018b095353a40753dc54c91c68c9487d4e"], ["ccip_monad", "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73"]] }],
  ["ccip_optimism", "rsETH", "0x043849686ee254ada46a432770e1a491491fc44d", "rsETH through Chainlink CCIP", { l1: "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7", dests: [["ccip_base", "0xe2110d5a2722abd8c8002646c645af15f5e9db1f"], ["ccip_mantle", "0x91a8aa510d20b2c1b27512777a1b6bd7e0552579"], ["ccip_ink", "0x3c29af7a7b7ec62a481d27ed297b90c1974a0230"]] }],
  ["ccip_xlayer", "syrupUSDC", "0xd503b0581aa504e75b345bf4cb8c359d8d1a042f", "syrupUSDC through Chainlink CCIP", { l1: "0x80ac24aa929eaf5013f6436cda2a7ba190f5cc0b", dests: [["ccip_arbitrum", "0x41ca7586cc1311807b4605fbb748a3b8862b42b5"], ["ccip_base", "0x660975730059246a68521a3e2fbd4740173100f5"], ["ccip_ink", "0x3c23e6fb09064e9a64829fa8fee27ad19a27bfa9"], ["ccip_monad", "0xab6e5a0c3799d020c790d34f7b2c02639e238af7"]] }],
  ["oft_optimism", "weETH", "0x5a7facb970d094b6c7ff1df0ea68d99e6e73cbff", "weETH through LayerZero (OFT adapter)", { l1: "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee", dests: [["oft_base", "0x04c0599ae5a44757c0af6f9ec3b93da8976c150a"], ["oft_unichain", "0x7dcc39b4d1c53cb31e1abc0e358b43987fef80f7"], ["oft_morph", "0x7dcc39b4d1c53cb31e1abc0e358b43987fef80f7"], ["oft_ink", "0xa3d68b74bf0528fdd07263c60d6488749044914b"], ["oft_berachain", "0x7dcc39b4d1c53cb31e1abc0e358b43987fef80f7"], ["oft_hyperevm", "0xa3d68b74bf0528fdd07263c60d6488749044914b"], ["oft_monad", "0xa3d68b74bf0528fdd07263c60d6488749044914b"]] }],
  ["oft_optimism", "WBTC", "0xc3f854b2970f8727d28527ece33176fac67fef48", "WBTC through LayerZero (OFT adapter)", { l1: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", dests: [["oft_base", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"], ["oft_sei", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"], ["oft_hedera", "0xd7d4d91d64a6061fa00a94e2b3a2d2a5fb677849"], ["oft_unichain", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"], ["oft_berachain", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"], ["oft_hyperevm", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"], ["oft_monad", "0x0555e30da8f98308edb960aa94c0db47230d2b9c"]] }],
  ["oft_arbitrum", "rsETH", "0x4186bfc76e2e237523cbc30fd220fe055156b41f", "rsETH through LayerZero (OFT adapter)", { l1: "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7", dests: [] }],
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
  for (const [kind, sym, l2, label, extra] of todo) {
    const k = label;
    const s = (st.seeds[k] ??= { kind, sym, l1: extra?.l1 ?? L1[sym], l2, label });
    console.log(`\n== ${label}`);
    if (!s.pair_id) {
      const au = await a.authenticateP(kind, s.l1, l2);
      if (!au.auth_id) { console.log("  auth failed, skipping for now"); continue; }
      s.auth_id = au.auth_id; s.auth_tx = au.hash;
      const r = await a.register([au.auth_id], 0, label);
      if (!r.pair_id) { console.log("  register failed"); save(); continue; }
      s.pair_id = r.pair_id; s.register_tx = r.hash; save();
    }
    if (extra && !s.extras_done) {
      const p = await a.rv("get_pair", [s.pair_id]);
      for (const [vk, vt] of extra.vaults ?? []) {
        const au = await a.authenticateP(vk, s.l1, vt);
        if (!p.vaults.some((v) => v.vault === (au.ret?.vault ?? ""))) await a.send("reg", "add_vault", [s.pair_id, au.auth_id]);
      }
      s.skipped ??= {};
      for (const [dk, dt] of extra.dests ?? []) {
        if (p.dests.some((d) => d.token === dt || d.kind === dk) || s.skipped[dk]) continue;
        const au = await a.authenticateP(dk, s.l1, dt);
        if (!au.auth_id) {
          // the bridge's own config does not prove it: recorded, and the coverage scan keeps it visible as unlisted
          if (/NOT_AUTHENTICATED/.test(String(au.revertReason))) { s.skipped[dk] = String(au.revertReason).slice(0, 160); save(); }
          continue;
        }
        await a.send("reg", "add_destination", [s.pair_id, au.auth_id]);
      }
      const q = await a.rv("get_pair", [s.pair_id]);
      if (q.vaults.length === 1 + (extra.vaults?.length ?? 0) && q.dests.length === 1 + (extra.dests?.length ?? 0) - Object.keys(s.skipped).length) { s.extras_done = true; save(); }
      else { console.log("  extras incomplete, retry next pass"); continue; }
    }
    let c;
    if (!s.check_id) {
      const r = await a.fileReadRule(label, async () => { const pins = await a.pins(s.pair_id); s.blocks = pins.blocks; return a.monitor(s.pair_id, pins.blocks); });
      if (!r.check) { console.log("  monitor failed"); continue; }
      c = r.check; s.check_id = c.check_id; save();
    } else {
      c = await a.check(s.check_id);
      if (c.status === "OPEN") { await a.read(s.check_id); c = await a.rule(s.check_id); }
    }
    s.status = c.status; s.verdict1 = c.verdict1; s.ratio_bps = c.ruling1?.ratio_bps; s.contest_deadline = c.contest_deadline;
    s.reason = c.reason || c.ruling1?.reason;
    save();
    console.log(`RESULT ${label}: check ${s.check_id} ${c.status} ${c.verdict1 || c.verdict} ratio_bps ${c.ruling1?.ratio_bps} ${c.reason || ""}`);
    if (c.status === "INCONCLUSIVE") { delete s.check_id; save(); }
  }
  }
}
