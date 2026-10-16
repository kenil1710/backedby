// Live canonical registry state -> docs/SEEDS.md. Every row is read from the
// contract; explorer links on both chains for every read.
import { readFileSync, writeFileSync } from "node:fs";
import { actor } from "./lib/flow.mjs";
import { CHAINS } from "./lib/bridges.mjs";

const a = actor({ role: "patrol", registry: "BackedByRegistry", log: () => {} });
const SITE = "https://backedby-ledger.vercel.app";
const SYM = {
  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC", "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
  "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
  "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "wstETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
  "0xbe9895146f7af43049ca1c1ae358b0541ea49704": "cbETH",
};
const ex = (ch, kind, v) => `${CHAINS[ch].explorer}/${kind}/${v}`;
const short = (x) => `${x.slice(0, 6)}...${x.slice(-4)}`;
const fmt = (raw, d) => {
  const s = String(raw).padStart(d + 1, "0");
  return s.slice(0, s.length - d).replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (d ? "." + s.slice(s.length - d, s.length - d + 2) : "");
};
const iso = (t) => new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ");
const reg = a.regAddr;
const pairs = (await a.rv("get_pairs", [0, 50])).pairs;
const rows = [];
let final = 0, under = 0, backed = 0, latestEnd = 0;
for (const p of pairs) {
  const cid = p.latest_check || p.open_check;
  const c = cid ? await a.rv("get_check", [cid]) : null;
  const r = c ? await a.cv("get_reading", [reg, cid, c.ruling2 ? 2 : 1]) : null;
  const rd = r?.found ? r.reading : null;
  const d = p.dests[0];
  const v = c ? (c.verdict || c.verdict1) : "-";
  if (c?.status === "FINAL") { final++; if (v === "UNDER_BACKED") under++; if (v === "BACKED") backed++; }
  if (c?.contest_deadline > latestEnd) latestEnd = c.contest_deadline;
  rows.push({ p, c, rd, d, v });
}
let md = `# Seeds (canonical registry)

Registry [\`${reg}\`](https://explorer-studio-dev.genlayer.com/address/${reg}) on GenLayer Studio Dev. Generated from
contract state by \`node tools/seeds_md.mjs\` on ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC. Each pair was authenticated
on chain by its bridge's own mapping, then checked by a monitoring check at freshly pinned finalized blocks, read by
ChainReader from two RPCs per chain, ruled by code, and finalized after its 6 h contest window.

**${pairs.length} pairs; ${final} FINAL rulings: ${backed} BACKED, ${under} UNDER_BACKED.** Latest contest window ends
${latestEnd ? new Date(latestEnd * 1000).toISOString().replace(".000Z", "Z") : "-"}.

| Pair | Bridge | Check | Status | Ruling | Ratio | Locked (Ethereum) | Supply (destination) | Ethereum block | Destination block |
|---|---|---|---|---|---|---|---|---|---|
`;
for (const { p, c, rd, d, v } of rows) {
  const sb = rd?.blocks?.ethereum, db = rd?.blocks?.[d.chain];
  md += `| [${p.pair_id}. ${p.label}](${SITE}/pair/${p.pair_id}) | ${p.kind} | ${c ? `[#${c.check_id}](${SITE}/check/${c.check_id})` : "-"} | ${c?.status ?? "-"} | **${v}** | ${c?.ruling1 && c.ruling1.ratio_bps >= 0 ? (c.ruling1.ratio_bps / 100).toFixed(2) + "%" : "-"} | `
    + (rd?.status === "OK" ? `[${fmt(rd.locked, rd.source_decimals)} ${SYM[p.source_token] ?? ""}](${CHAINS.ethereum.explorer}/token/${p.source_token}?a=${p.vault}) in [${short(p.vault)}](${ex("ethereum", "address", p.vault)})` : "-") + " | "
    + (rd?.status === "OK" ? `[${fmt(rd.dests[0].supply, rd.dests[0].decimals)}](${ex(d.chain, "token", d.token)}) of [${short(d.token)}](${ex(d.chain, "address", d.token)})${rd.dests[0].deposits ? ` (deposits ${fmt(rd.dests[0].deposits, rd.source_decimals)})` : ""}` : "-") + " | "
    + (sb ? `[${sb.number}](${ex("ethereum", "block", sb.number)}) ${iso(sb.timestamp)}` : "-") + " | "
    + (db ? `[${db.number}](${ex(d.chain, "block", db.number)}) ${iso(db.timestamp)}` : "-") + " |\n";
}
md += `
## Notes

- **Nomad (5 pairs, UNDER_BACKED).** The Ethereum BridgeRouter was drained in the August 2022 exploit; the Moonbeam
  representations still circulate. Moonbeam has produced no block since 2026-08-10, so the pinned blocks are its last
  finalized block and the first Ethereum block after it; the gap rule holds (seconds).
- **USDT on Polygon (UNDER_BACKED).** The PoS bridge's ERC20Predicate holds a small fraction of the child token's
  supply, because Polygon's USDT is now also minted through USDT0's LayerZero adapter. By the rule BackedBy enforces
  (the canonical vault against the canonical token's supply) the PoS bridge does not back it; nothing here says USDT0
  is unbacked.
- **Over-backing** (for example OP Mainnet USDC.e, Base USDbC, OP DAI): the vault holds more than the counted supply.
  BackedBy reports the ratio and does not guess why; a vault can hold more than it owes, never less, and stay BACKED.
- Every number above is also on the pair's page with the bridge-mapping anchors that were re-read at the same blocks.
`;
writeFileSync(new URL("../docs/SEEDS.md", import.meta.url), md);
writeFileSync(new URL("../docs/seed-summary.json", import.meta.url), JSON.stringify({ pairs: pairs.length, final, backed, under, latest_window_end: latestEnd }, null, 2) + "\n");
console.log(`SEEDS.md: ${pairs.length} pairs, ${final} final (${backed} backed, ${under} under), latest window end ${latestEnd}`);
