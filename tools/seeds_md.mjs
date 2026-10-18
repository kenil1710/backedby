// Live canonical registry state -> docs/SEEDS.md. Every row is read from the
// contract; explorer links on both chains for every read.
import { readFileSync, writeFileSync } from "node:fs";
import { actor } from "./lib/flow.mjs";
import { CHAINS, explorerLink, USDT0_DESTS } from "./lib/bridges.mjs";
import { call, block, pad } from "./lib/evm.mjs";

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
// display names from the site's labels.json (the label stored at register_pair cannot be changed)
const LABELS = JSON.parse(readFileSync(new URL("../frontend/src/lib/labels.json", import.meta.url), "utf8"))[reg.toLowerCase()] ?? {};
const pairs = (await a.rv("get_pairs", [0, 50])).pairs.map((p) => ({ ...p, label: LABELS[p.pair_id] ?? p.label }));
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
// --- shared vaults: every vault, which destinations it backs, and what was checked for more -----------------
// Each value below is read from BOTH Ethereum RPCs at one finalized block and must be identical.
const [ra, rb] = CHAINS.ethereum.rpcs;
const again = async (f) => { for (let i = 0; ; i++) { try { return await f(); } catch (e) { if (i === 9) throw e; await new Promise((r) => setTimeout(r, 10000 * (i + 1))); } } };
const fin = parseInt((await again(() => block(ra, "finalized"))).number, 16) - 5;
async function both(to, data) {
  const [x, y] = await Promise.all([again(() => call(ra, to, data, fin)), again(() => call(rb, to, data, fin))]);
  if (x !== y) throw new Error(`RPCs disagree on ${to} ${data.slice(0, 10)} at ${fin}`);
  return x;
}
const DAI = "0x6b175474e89094c44da98b954eedeac495271d0f";
const MAXU = (1n << 256n) - 1n;
const allow = async (owner, spender) => { const v = BigInt(await both(DAI, "0xdd62ed3e" + pad(owner) + pad(spender))); return v === MAXU ? "unlimited" : v.toString(); };
// Sky's chainlog names every contract that may move DAI out of each escrow
const ESCROWS = [
  ["OP Mainnet DAI escrow", "0x467194771dae2967aef3ecbedd3bf9a310c76c65", [["OPTIMISM_DAI_BRIDGE", "0x10e6593cdda8c58a1d0f14c5164b376352a55f2f"], ["OPTIMISM_TELEPORT_BRIDGE", "0x920347f49a9dbe50865eb6161c3b2774ac046a7f"], ["OPTIMISM_TOKEN_BRIDGE (USDS)", "0x3d25b7d486cae1810374d37a48bcf0963c9b8057"], ["ARBITRUM_DAI_BRIDGE", "0xd3b5b60020504bc3489d6949d545893982ba3011"]]],
  ["Arbitrum DAI escrow", "0xa10c7ce4b876998858b1a9e12b10092229539400", [["ARBITRUM_DAI_BRIDGE", "0xd3b5b60020504bc3489d6949d545893982ba3011"], ["ARBITRUM_TELEPORT_BRIDGE", "0x22218359e78bc34e532b653198894b639ac3ed72"], ["ARBITRUM_TOKEN_BRIDGE (USDS)", "0x84b9700e28b23f873b82c1beb23d86c091b6079e"], ["Arbitrum Nova L1DaiGateway", "0x97f63339374fce157aa8ee27830172d2af76a786"], ["OPTIMISM_DAI_BRIDGE", "0x10e6593cdda8c58a1d0f14c5164b376352a55f2f"]]],
];
const escrowLines = [];
for (const [name, esc, spenders] of ESCROWS) {
  const got = [];
  for (const [label, s] of spenders) got.push(`${label} ${await allow(esc, s)}`);
  escrowLines.push(`  - ${name} [\`${short(esc)}\`](${ex("ethereum", "address", esc)}): DAI allowance to ${got.join(", ")}.`);
}
const ADAPTER = "0x6c96de32cea08842dcc4058c14d3aaad7fa41dee";
const LZ = { 30109: "polygon", 30110: "arbitrum", 30111: "optimism", 30181: "mantle", 30212: "Conflux eSpace", 30274: "xlayer", 30280: "sei",
  30295: "flare", 30316: "hedera", 30320: "unichain", 30322: "morph", 30333: "Rootstock", 30339: "ink", 30362: "berachain", 30367: "hyperevm",
  30383: "Plasma", 30390: "monad", 30396: "Stable", 30398: "MegaETH", 30410: "Tempo" };
const LEFT_OUT = {
  "Conflux eSpace": "its two public RPCs (BlockPI, confluxrpc.com) returned different totalSupply for the same block number",
  Rootstock: "no public RPC serves the finalized tag (\"invalid blocknumber finalized\" from all three)",
  Plasma: "one public RPC only (rpc.plasma.to; dRPC's free tier does not serve it)",
  Stable: "one public RPC only (rpc.stable.xyz)", MegaETH: "one public RPC only (mainnet.megaeth.com)",
  Tempo: "one public RPC only (rpc.mainnet.tempo.xyz)",
};
const peers = [];
for (let e = 30100; e <= 30420; e++) {
  const r = await both(ADAPTER, "0xbb0b6a53" + pad("0x" + e.toString(16)));
  if (BigInt(r) !== 0n) peers.push([e, "0x" + r.slice(26)]);
}
const usdtPair = pairs.find((p) => p.vaults.some((v) => v.vault === ADAPTER));
const readChains = usdtPair ? usdtPair.dests.map((d) => d.chain) : [];
const peerLines = peers.map(([e, o]) => {
  const c = LZ[e] ?? `eid ${e}`;
  return `  - ${e} ${c}: ${readChains.includes(c) ? "**in the pair**" : LEFT_OUT[c] ? "left out: " + LEFT_OUT[c] : "not in the pair"}`;
});
const byVault = {};
for (const { p } of rows) for (const v of p.vaults) (byVault[v.vault + "|" + p.source_token] ??= []).push({ p, v });
const vaultRows = Object.values(byVault).map((xs) => {
  const { p, v } = xs[0];
  return `| [\`${short(v.vault)}\`](${ex("ethereum", "address", v.vault)}) | ${v.kind} | ${SYM[p.source_token] ?? short(p.source_token)} | ${xs.map((x) => `[${x.p.pair_id}](${SITE}/pair/${x.p.pair_id})`).join(", ")} | ${p.dests.length} | ${p.dests.map((d) => d.chain).join(", ")} |`;
});
md += `
## Shared vaults

A vault that backs the same token on several chains is judged against all of them, or its ratio would count the
vault once per chain. The registry enforces it: a vault and source token belong to exactly one pair
(\`VAULT_ALREADY_IN_PAIR_n_ADD_A_DESTINATION_INSTEAD\`), and anyone can add a destination the vault backs with the
bridge's own proof. Every vault in the registry, and every destination its pair lists:

| Vault | Kind | Token | Pair | Destinations | Chains |
|---|---|---|---|---|---|
${vaultRows.join("\n")}

**USDT0's Ethereum adapter** [\`${short(ADAPTER)}\`](${ex("ethereum", "address", ADAPTER)}) backs USDT0 on every chain it has a
LayerZero peer on. Its \`peers(eid)\` for every endpoint id 30100-30420, read from both Ethereum RPCs at block ${fin}:
${peerLines.join("\n")}

Each destination in the pair is authenticated through the OFT on its own chain (\`OFT.peers(Ethereum)\` is the
adapter, the adapter's \`peers(chain)\` is that OFT, both on that chain's LayerZero endpoint) and read from two RPCs
run by different operators that serve the finalized tag and gave identical headers and calls in testing. Hedera's
USDT0 is a native HTS token; it is authenticated through its OFT, whose \`token()\` names it. The chains left out
still hold USDT0 the adapter backs, so this ratio overstates backing by their supply; the verdict can only move
towards UNDER_BACKED if they were added.

**Every other vault** was checked for further destinations:
${escrowLines.join("\n")}
  Each DAI escrow can be spent only by its own chain's DAI bridge and that chain's Teleport gateway; neither mints a
  second token, so L2 DAI on that chain is the escrow's only destination. OP DAI's surplus (vault above supply) is
  reported as read; BackedBy does not guess its cause.
- **Arbitrum gateways** (standard ERC20, USDC, Lido wstETH) escrow for Arbitrum One only; Arbitrum Nova has its own
  gateways and escrows (its DAI gateway has no allowance on the One escrow above).
- **OP and Base Standard Bridges** keep \`deposits(l1, l2)\` per destination token; the pair counts each destination
  as the larger of its supply and that ledger, so DAI-, USDC- or WBTC-backed tokens a bridge also mints elsewhere on
  the same chain show up as vault minus ledger, which the table above gives per pair.
- **Polygon's ERC20Predicate** maps each root token to exactly one child (\`RootChainManager.rootToChildToken\`).
- **Nomad's Ethereum router** also backed representations on other Nomad domains (Evmos, Milkomeda, Gnosis, Avalanche)
  that BackedBy does not read; adding them could only lower the five ratios, which are already UNDER_BACKED.

## Notes

- **Nomad (5 pairs, UNDER_BACKED).** The Ethereum BridgeRouter was drained in the August 2022 exploit; the Moonbeam
  representations still circulate. Moonbeam has produced no block since 2026-08-10, so the pinned blocks are its last
  finalized block and the first Ethereum block after it; the gap rule holds (seconds).
- **USDT0 (pair 13: two vaults, ${usdtPair ? usdtPair.dests.length : "-"} destinations).** Polygon's USDT is minted by the PoS bridge
  (ERC20Predicate) and by USDT0's LayerZero adapter, so the pair holds both vaults and every USDT0 destination listed
  above. The first deployment read it against the predicate alone (UNDER_BACKED at 0.64%, docs/superseded/e915d21/);
  the second against Polygon, Arbitrum and OP Mainnet only (docs/superseded/6f9431f/).
- **OP and Base** pairs count the larger of supply and the bridge's own \`deposits\` ledger, so their ratio is the
  vault against what the bridge itself says it owes; several match it to the wei.
- **Over-backing** (for example OP Mainnet USDC.e, Base USDbC, OP DAI): the vault holds more than the counted supply.
  BackedBy reports the ratio and does not guess why; a vault can hold more than it owes, never less, and stay BACKED.
- Every number above is also on the pair's page with the bridge-mapping anchors that were re-read at the same blocks.
`;
writeFileSync(new URL("../docs/SEEDS.md", import.meta.url), md);
writeFileSync(new URL("../docs/seed-summary.json", import.meta.url), JSON.stringify({ pairs: pairs.length, final, backed, under, latest_window_end: latestEnd }, null, 2) + "\n");
console.log(`SEEDS.md: ${pairs.length} pairs, ${final} final (${backed} backed, ${under} under), latest window end ${latestEnd}`);
