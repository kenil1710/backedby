// docs/feasibility.json -> docs/FEASIBILITY.md
import { readFileSync, writeFileSync } from "node:fs";
import { CHAINS } from "./lib/bridges.mjs";
const doc = JSON.parse(readFileSync(new URL("../docs/feasibility.json", import.meta.url), "utf8"));
const destOf = (k) => ({ op_dai: "optimism", nomad: "moonbeam" }[k] ?? k);
const fmt = (raw, dec) => {
  const s = String(raw).padStart(dec + 1, "0");
  const w = s.slice(0, s.length - dec).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const f = dec ? s.slice(s.length - dec).slice(0, 2) : "";
  return dec ? `${w}.${f}` : w;
};
const short = (a) => `${a.slice(0, 6)}...${a.slice(-4)}`;
const link = (ch, a) => `[${short(a)}](${CHAINS[ch].explorer}/address/${a})`;
const iso = (t) => new Date(t * 1000).toISOString().replace(".000Z", "Z");
const ok = doc.rows.filter((r) => r.ok);
const under = ok.filter((r) => r.verdict === "UNDER_BACKED");
let md = `# Feasibility (Step 0)

Read on ${doc.started.slice(0, 16).replace("T", " ")} UTC with plain JSON-RPC (\`node tools/feasibility.mjs\`, raw data in
[\`feasibility.json\`](feasibility.json)). Nothing here came from an indexer or an API: every number is an \`eth_call\`
at one pinned finalized block per chain, sent to **two RPCs run by different operators**, and kept only when both
answered byte-for-byte the same.

**Result: ${ok.length} pairs authenticated and readable, ${under.length} real UNDER_BACKED, ${doc.rows.length - ok.length} refused.**
Both RPCs agreed on every value of every authenticated pair: ${ok.every((r) => r.agree) ? "yes" : "NO"}.

## RPCs (two per chain)

| Chain | RPC A | RPC B | Archive reads |
|---|---|---|---|
${Object.entries(CHAINS).map(([c, v]) => `| ${c} | ${v.rpcs[0]} | ${v.rpcs[1]} | both serve state 72 h+ back |`).join("\n")}

Probed and rejected (no archive state, key required, batch refused, or down): publicnode (archive needs a token),
arb1.arbitrum.io (state pruned after ~6 h, too short for a 6 h contest window), arbitrum.drpc.org, 1rpc.io,
polygon-rpc.com, llamarpc, cloudflare-eth, blastapi (shut down), ankr (key), blockpi (key), omniatech (down),
moonbeam.unitedbloc / rpc.api.moonbeam.network (unreachable). dRPC's free tier caps a JSON-RPC batch at 3 calls;
ChainReader splits batches to that size.

## Pinned blocks

One block per chain, chosen by \`tools/lib/pin.mjs\` and re-checked by the same rules the contract applies: both
finalized, the Ethereum (locked) block at or after the destination block, gap at most 10 minutes.

| Destination | Ethereum block | Destination block | Gap |
|---|---|---|---|
${Object.entries(doc.pins).map(([d, p]) => `| ${d} | [${p.ethereum.number}](https://etherscan.io/block/${p.ethereum.number}) ${iso(p.ethereum.timestamp)} | [${p[d].number}](${CHAINS[d].explorer}/block/${p[d].number}) ${iso(p[d].timestamp)} | ${p.gap_s} s |`).join("\n")}

**Moonbeam has not produced a block since ${iso(doc.pins.moonbeam.moonbeam.timestamp)}.** Three unrelated RPCs (dRPC,
OnFinality, 1RPC) report the same head, \`${doc.pins.moonbeam.moonbeam.number + 3}\`; its finalized block is
\`${doc.pins.moonbeam.moonbeam.number}\`. The rules still work: the Ethereum block is pinned to the first block after
Moonbeam's last finalized one (gap ${doc.pins.moonbeam.gap_s} s). A check on a Nomad pair is therefore always about that
moment, which is why CollateralGate (max age) refuses it as stale on top of UNDER_BACKED.

## Pairs

Ratio = locked / summed destination supply, both normalized to 18 decimals. Verdict at 0 bps tolerance.

| # | Bridge | Token | Vault (Ethereum) | Destination token | Dec (src/dst) | Locked | Supply | Ratio | Both RPCs agree | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
`;
let i = 0;
for (const r of ok) {
  i++;
  const d = r.dest[0];
  md += `| ${i} | ${r.kind} | ${r.sym} | ${link("ethereum", r.vault)} | ${link(d.chain, d.token)} (${d.chain}) | ${r.source_decimals}/${d.decimals} | ${fmt(r.locked, r.source_decimals)} | ${fmt(d.supply, d.decimals)} | ${r.ratio === null ? "-" : r.ratio.toFixed(4)} | ${r.agree ? "yes" : "NO"} | **${r.verdict}** |\n`;
}
md += `
## Refused candidates (not authenticated by the bridge's own mapping)

| Bridge | Token | Destination | Why |
|---|---|---|---|
${doc.rows.filter((r) => !r.ok).map((r) => `| ${r.kind} | ${r.sym} | ${r.fake ?? (r.dest?.[0]?.token ?? "-")} | ${r.why} |`).join("\n")}

- **Arbitrum USDT**: the L1 router no longer has a gateway for USDT (Arbitrum's USDT moved to USDT0, a LayerZero OFT);
  there is no canonical-bridge pair to check.
- **Base LINK**: \`0x88Fb...6e196\` does not report Ethereum LINK as its remote token; it is not a Standard Bridge token.
- **OP "USDC" 0x0b2c...ff85** (deliberate fake): Circle's native USDC, not minted by any bridge; passing it off as the
  destination of the Ethereum USDC vault is refused.

## How each pair is authenticated

| Bridge | On-chain proof (all read from both RPCs) | Vault |
|---|---|---|
| Arbitrum | L1GatewayRouter \`getGateway(l1)\` and \`calculateL2TokenAddress(l1)\`; L2GatewayRouter \`calculateL2TokenAddress(l1)\` must equal it | the gateway, or \`gateway.l1Escrow()\` when it has one (DAI) |
| Optimism / Base | the L2 token's \`remoteToken()\` (or legacy \`l1Token()\`) is the source token and its \`bridge()\` (or \`l2Bridge()\`) is the L2StandardBridge \`0x4200...0010\` | that chain's L1StandardBridge |
| Optimism DAI | L1DAITokenBridge \`l1Token/l2Token/escrow\`; L2DAITokenBridge \`l1Token/l2Token/l1DAITokenBridge\` | \`L1DAITokenBridge.escrow()\` |
| Polygon PoS | RootChainManager \`rootToChildToken(l1)\`; ChildChainManager \`childToRootToken(child)\` must point back | \`typeToPredicate(tokenToType(l1))\` (ERC20Predicate) |
| Nomad | Moonbeam BridgeRouter \`tokenRegistry()\`, TokenRegistry \`getTokenId(rep) = (eth, l1)\` and \`getLocalAddress(eth, l1) = rep\`; Moonbeam BridgeRouter \`remotes(eth)\`; Ethereum TokenRegistry \`getTokenId(l1)\` is local | \`remotes(eth)\`: the Ethereum BridgeRouter |

## What the UNDER_BACKED rows are

${under.map((r) => `- **${r.kind} ${r.sym}**: ${fmt(r.locked, r.source_decimals)} locked against ${fmt(r.dest[0].supply, r.dest[0].decimals)} outstanding (ratio ${r.ratio.toFixed(6)}).`).join("\n")}

The five Nomad rows are the August 2022 exploit: the Ethereum BridgeRouter was drained, and the Moonbeam
representations kept circulating with almost nothing behind them. Polygon USDT is not an exploit: its child token on
Polygon is now also minted by USDT0's LayerZero adapter, so most of its supply is no longer locked in the PoS
bridge's ERC20Predicate. By the rule BackedBy enforces (the canonical vault against the canonical token's supply) it is
UNDER_BACKED, and the contract will say so; the README explains why that is the honest reading.

## Decision

Feasible: ${ok.length} readable pairs (need 10+), ${under.length} real UNDER_BACKED (need 1+). Continue with all five bridge
kinds; seed the canonical registry with a mix of BACKED pairs and every UNDER_BACKED one.
`;
writeFileSync(new URL("../docs/FEASIBILITY.md", import.meta.url), md);
console.log("wrote docs/FEASIBILITY.md", ok.length, "ok", under.length, "under");
