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
  "0xbe9895146f7af43049ca1c1ae358b0541ea49704": "cbETH", "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f": "GHO",
  "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7": "rsETH", "0x80ac24aa929eaf5013f6436cda2a7ba190f5cc0b": "syrupUSDC",
  "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee": "weETH",
};
const CCIPN = JSON.parse(readFileSync(new URL("../frontend/src/lib/ccip-names.json", import.meta.url), "utf8"));
const LZN = { 30101: "Ethereum", 30102: "BNB Chain", 30106: "Avalanche", 30108: "Aptos", 30109: "Polygon PoS", 30110: "Arbitrum One", 30111: "OP Mainnet",
  30145: "Gnosis", 30165: "zkSync Era", 30168: "Solana", 30181: "Mantle", 30183: "Linea", 30184: "Base", 30212: "Conflux eSpace", 30214: "Scroll",
  30243: "Blast", 30260: "Mode", 30274: "X Layer", 30280: "Sei", 30295: "Flare", 30316: "Hedera", 30320: "Unichain", 30322: "Morph",
  30333: "Rootstock", 30339: "Ink", 30362: "Berachain", 30367: "HyperEVM", 30383: "Plasma", 30390: "Monad", 30396: "Stable", 30398: "MegaETH", 30410: "Tempo" };
const remoteName = (id) => { const [f, n] = id.split(":"); return f === "lz" ? `${LZN[n] ?? "eid " + n} (eid ${n})` : f === "ccip" ? `${CCIPN[n]?.name ?? "selector " + n}` : id; };
let keeper = null;
try { keeper = await (await fetch("https://raw.githubusercontent.com/kenil1710/backedby/keeper-state/status.json", { cache: "no-store" })).json(); } catch { /* keeper has not run */ }
let surplus = { pairs: [] };
try { surplus = JSON.parse(readFileSync(new URL("../docs/surplus.json", import.meta.url), "utf8")); } catch { /* not computed */ }
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
const pairs = [];
for (let off = 0; ; off += 50) { const pg = await a.rv("get_pairs", [off, 50]); pairs.push(...pg.pairs.map((p) => ({ ...p, label: LABELS[p.pair_id] ?? p.label }))); if (off + 50 >= pg.total) break; }
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

| Pair | Vaults | Check | Status | Ruling | Ratio | Coverage | Alert | PoR | Locked (Ethereum, per vault) | Supply (per destination) | Ethereum block | Destination blocks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
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
  md += `| [${p.pair_id}. ${p.label}](${SITE}/pair/${p.pair_id}) | ${p.vaults.map((x) => x.kind).join(" + ")} | ${c ? `[#${c.check_id}](${SITE}/check/${c.check_id})` : "-"} | ${c?.status ?? "-"} | **${v}** | ${c?.ruling1 && c.ruling1.ratio_bps >= 0 ? (c.ruling1.ratio_bps / 100).toFixed(2) + "%" : "-"} | ${c?.ruling1?.coverage ? c.ruling1.coverage.state + (c.ruling1.coverage.unlisted.length ? ` (${c.ruling1.coverage.unlisted.length} unlisted)` : "") : "-"} | ${c?.ruling1?.alert || "-"} | ${c?.ruling1?.por ? `${c.ruling1.por.status} ${(c.ruling1.por.por_ratio_bps / 100).toFixed(2)}% (${c.ruling1.por.delta_bps >= 0 ? "+" : ""}${c.ruling1.por.delta_bps} bps)` : "-"} | ${lockedCell} | ${supplyCell} | `
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
const LEFT_OUT = {
  30212: "its two public RPCs returned different totalSupply for the same block number",
  30333: "no public RPC serves the finalized tag",
  30383: "one public RPC only", 30396: "one public RPC only", 30398: "one public RPC only", 30410: "one public RPC only",
};
const canonK = Object.values(keeper?.contracts ?? {}).find((c) => c.address?.toLowerCase() === reg.toLowerCase());
const covLines = [];
for (const { p, c } of rows) {
  const cov = c?.ruling1?.coverage;
  if (!cov || cov.state === "COMPLETE") continue;
  const items = cov.unlisted.map((u) => {
    const listedNow = p.vaults.some((v) => (v.remotes ?? []).includes(u.id));
    const why = canonK?.unmatched?.[p.pair_id]?.[u.id]?.why ?? LEFT_OUT[u.id.split(":")[1]];
    return `${remoteName(u.id)}${listedNow ? " (added since this ruling)" : why ? ` (not added: ${why})` : ""}`;
  });
  covLines.push(`- [${p.pair_id}. ${p.label}](${SITE}/pair/${p.pair_id}): **${cov.state}**${cov.state === "OPEN" ? " (one escrow for every representation; not enumerable on chain)" : ""}${items.length ? ": " + items.join("; ") : ""}`);
}
const surplusLines = surplus.pairs.filter((s) => s.registry?.toLowerCase() === reg.toLowerCase()).map((s) => {
  const f = (x) => fmt((BigInt(x) < 0n ? -BigInt(x) : BigInt(x)).toString(), s.scale_decimals);
  return `- [${s.pair_id}. ${s.label}](${SITE}/pair/${s.pair_id}) (${(s.ratio_bps / 100).toFixed(2)}%, check ${s.check_id}): surplus ${f(s.surplus_norm)}. ${s.components.map((c) => `${c.name}: ${BigInt(c.amount) < 0n ? "-" : ""}${f(c.amount)}`).join("; ")}; not attributed: ${BigInt(s.residual) < 0n ? "-" : ""}${f(s.residual)}.`;
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

## Coverage

Each ruling records which destinations every vault's own bridge config names at the pinned Ethereum block (LayerZero
peers on every eid 30101-31100, CCIP supported chains, Wormhole's ledger, single-mapping bridges). Pairs whose latest
ruling is not COMPLETE, and why each unlisted destination is not in the pair (from the keeper's records):

${covLines.join("\n") || "- none"}

## Where over-backing comes from

From \`tools/explain_surplus.mjs\` (docs/surplus.json), each part read from chain:

${surplusLines.join("\n") || "- not computed"}

**Every other vault** was checked for further destinations:
${escrowLines.join("\n")}
  Each DAI escrow can be spent only by its own chain's DAI bridge and that chain's Teleport gateway; neither mints a
  second token, so L2 DAI on that chain is the escrow's only destination; OP DAI's surplus is explained above.
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
- **USDT0.** Polygon's USDT is minted by the PoS bridge (ERC20Predicate) and by USDT0's LayerZero adapter, so the
  pair holds both vaults and every USDT0 destination two RPCs can read; the peers on other chains are listed under
  Coverage. Earlier deployments read it against fewer chains (docs/superseded/).
- **OP and Base** pairs count the larger of supply and the bridge's own \`deposits\` ledger, so their ratio is the
  vault against what the bridge itself says it owes; several match it to the wei.
- **Over-backing**: the vault holds more than the counted supply; the sources read from chain are listed above.
- **Wormhole** pairs count the bridge's own ledger \`outstandingBridged\` (what it owes on every chain), so the
  wrapped tokens on chains the pair does not list are counted.
- Every number above is also on the pair's page with the bridge-mapping anchors that were re-read at the same blocks.
`;
writeFileSync(new URL("../docs/SEEDS.md", import.meta.url), md);
writeFileSync(new URL("../docs/seed-summary.json", import.meta.url), JSON.stringify({ pairs: pairs.length, final, backed, under, latest_window_end: latestEnd }, null, 2) + "\n");
console.log(`SEEDS.md: ${pairs.length} pairs, ${final} final (${backed} backed, ${under} under), latest window end ${latestEnd}`);
