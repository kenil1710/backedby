// Live canonical registry state -> docs/SEEDS.md. Every row is read from the
// contract; explorer links on both chains for every read.
import { readFileSync, writeFileSync } from "node:fs";
import { actor } from "./lib/flow.mjs";
import { CHAINS, explorerLink } from "./lib/bridges.mjs";

const a = actor({ role: "patrol", registry: "BackedByRegistry", log: () => {} });
const SITE = "https://backedby-ledger.vercel.app";
const SYM = {
  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC", "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
  "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
  "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "wstETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
  "0xbe9895146f7af43049ca1c1ae358b0541ea49704": "cbETH",
};
const ex = (ch, kind, v) => explorerLink(ch, kind, v);
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

| Pair | Vaults | Check | Status | Ruling | Ratio | Locked (Ethereum, per vault) | Supply (per destination) | Ethereum block | Destination blocks |
|---|---|---|---|---|---|---|---|---|---|
`;
for (const { p, c, rd, d, v } of rows) {
  const sb = rd?.blocks?.ethereum;
  const lockedCell = rd?.status === "OK"
    ? p.vaults.map((x, i) => `[${fmt(rd.locked_by_vault[i], rd.source_decimals)} ${SYM[p.source_token] ?? ""}](${CHAINS.ethereum.explorer}/token/${p.source_token}?a=${x.vault}) in [${short(x.vault)}](${ex("ethereum", "address", x.vault)}) (${x.kind})`).join("<br>")
    : "-";
  const supplyCell = rd?.status === "OK"
    ? rd.dests.map((y) => `[${fmt(y.supply, y.decimals)}](${ex(y.chain, "token", y.token)}) of [${short(y.token)}](${ex(y.chain, "address", y.token)}) on ${y.chain}${y.deposits ? ` (bridge ledger ${fmt(y.deposits, rd.source_decimals)})` : ""}`).join("<br>")
    : "-";
  const destBlocks = rd?.blocks ? Object.entries(rd.blocks).filter(([k]) => k !== "ethereum").map(([k, bl]) => `[${bl.number}](${ex(k, "block", bl.number)}) ${k} ${iso(bl.timestamp)}`).join("<br>") : "-";
  md += `| [${p.pair_id}. ${p.label}](${SITE}/pair/${p.pair_id}) | ${p.vaults.map((x) => x.kind).join(" + ")} | ${c ? `[#${c.check_id}](${SITE}/check/${c.check_id})` : "-"} | ${c?.status ?? "-"} | **${v}** | ${c?.ruling1 && c.ruling1.ratio_bps >= 0 ? (c.ruling1.ratio_bps / 100).toFixed(2) + "%" : "-"} | ${lockedCell} | ${supplyCell} | `
    + (sb ? `[${sb.number}](${ex("ethereum", "block", sb.number)}) ${iso(sb.timestamp)}` : "-") + ` | ${destBlocks} |\n`;
}
md += `
## Notes

- **Nomad (5 pairs, UNDER_BACKED).** The Ethereum BridgeRouter was drained in the August 2022 exploit; the Moonbeam
  representations still circulate. Moonbeam has produced no block since 2026-08-10, so the pinned blocks are its last
  finalized block and the first Ethereum block after it; the gap rule holds (seconds).
- **USDT on Polygon (two vaults).** Polygon's USDT is minted by the PoS bridge (ERC20Predicate) and by USDT0's
  LayerZero adapter, so the pair holds both vaults, and its destinations are USDT0 on Polygon, Arbitrum and OP
  Mainnet, every chain BackedBy reads where the adapter has a peer. The adapter also backs USDT0 on chains BackedBy
  does not read, so this ratio leaves that supply out. The first deployment read this pair against the predicate
  alone and called it UNDER_BACKED at 0.64%; that record is in docs/superseded/e915d21/.
- **OP and Base** pairs count the larger of supply and the bridge's own \`deposits\` ledger, so their ratio is the
  vault against what the bridge itself says it owes; several match it to the wei.
- **Over-backing** (for example OP Mainnet USDC.e, Base USDbC, OP DAI): the vault holds more than the counted supply.
  BackedBy reports the ratio and does not guess why; a vault can hold more than it owes, never less, and stay BACKED.
- Every number above is also on the pair's page with the bridge-mapping anchors that were re-read at the same blocks.
`;
writeFileSync(new URL("../docs/SEEDS.md", import.meta.url), md);
writeFileSync(new URL("../docs/seed-summary.json", import.meta.url), JSON.stringify({ pairs: pairs.length, final, backed, under, latest_window_end: latestEnd }, null, 2) + "\n");
console.log(`SEEDS.md: ${pairs.length} pairs, ${final} final (${backed} backed, ${under} under), latest window end ${latestEnd}`);
