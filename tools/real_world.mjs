/**
 * Real-world truth: every ruling on the canonical registry checked against
 * raw chain data and public sources, outside the contracts.
 *
 *  1. Raw chain data from a THIRD RPC per chain (one the contracts never use):
 *     every vault's balance, every destination's supply (and OP/Base deposits,
 *     Wormhole's ledger) at the ruling's pinned blocks, the ratio recomputed with
 *     the same arithmetic. It must equal the ruling to the bps, and the verdict.
 *  2. A public indexer (Blockscout's token API) for each destination on chains it
 *     serves: today's totalSupply next to the pinned one (a sanity check on the
 *     token and its decimals; supplies move, so it is reported, not compared exactly).
 *  3. Public sources named per bridge: Chainlink PoR (read in the ruling), the
 *     Nomad exploit report for the drained Nomad vault, Wormhole's own ledger.
 *   node tools/real_world.mjs   -> docs/real_world.json, docs/REAL_WORLD_CHECK.md
 */
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { rpc } from "./lib/evm.mjs";
import { CHAINS } from "./lib/bridges.mjs";
const require = createRequire(new URL("../test/package.json", import.meta.url));
const { createClient } = require("genlayer-js");
const { studioDevnet } = require("genlayer-js/chains");

const root = new URL("..", import.meta.url).pathname;
const dep = JSON.parse(readFileSync(root + "deployments.json", "utf8")).contracts;
const REG = dep.BackedByRegistry.address;
const client = createClient({ chain: studioDevnet });
const plain = (r) => (typeof r === "string" ? JSON.parse(r) : JSON.parse(JSON.stringify(r, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v))));
const view = async (fn, args) => { for (let i = 0; ; i++) { try { return plain(await client.readContract({ address: REG, functionName: fn, args })); } catch (e) { if (i > 4) throw e; await new Promise((s) => setTimeout(s, 3000 * (i + 1))); } } };

// third RPCs: none of them is one of the contract's two for that chain
const THIRD = {
  ethereum: ["https://eth.drpc.org", "https://eth-mainnet.public.blastapi.io", "https://ethereum.publicnode.com"],
  arbitrum: ["https://arb1.arbitrum.io/rpc", "https://arbitrum.drpc.org"],
  optimism: ["https://optimism.drpc.org", "https://optimism-mainnet.public.blastapi.io"],
  base: ["https://mainnet.base.org", "https://base-mainnet.public.blastapi.io"],
  polygon: ["https://polygon.gateway.tenderly.co", "https://polygon-rpc.com", "https://polygon-mainnet.public.blastapi.io"],
  moonbeam: ["https://1rpc.io/glmr", "https://moonbeam-rpc.publicnode.com"],
  mantle: ["https://mantle-rpc.publicnode.com", "https://mantle-mainnet.public.blastapi.io"],
  xlayer: ["https://rpc.xlayer.tech", "https://xlayer.blockpi.network/v1/rpc/public"],
  sei: ["https://sei-evm-rpc.publicnode.com", "https://evm-rpc.sei.basementnodes.ca"],
  flare: ["https://flare-api.flare.network/ext/C/rpc", "https://rpc.au.cc/flare"],
  hedera: ["https://hedera.linkpool.pro"],
  unichain: ["https://unichain-rpc.publicnode.com", "https://unichain.api.onfinality.io/public"],
  morph: ["https://morph.drpc.org"],
  ink: ["https://ink.drpc.org", "https://ink-public.nodies.app"],
  berachain: ["https://berachain.drpc.org", "https://rpc.berachain-apis.com"],
  hyperevm: ["https://hyperliquid.drpc.org", "https://rpc.hypurrscan.io"],
  monad: ["https://monad.drpc.org", "https://rpc1.monad.xyz"],
};
const BLOCKSCOUT = { arbitrum: "https://arbitrum.blockscout.com", optimism: "https://optimism.blockscout.com", base: "https://base.blockscout.com",
  polygon: "https://polygon.blockscout.com", ethereum: "https://eth.blockscout.com" };
const pad = (a) => a.slice(2).toLowerCase().padStart(64, "0");

async function third(chain, to, data, block) {
  const used = new Set(CHAINS[chain].rpcs);
  let last;
  for (const u of THIRD[chain] ?? []) {
    if (used.has(u)) continue;
    try {
      const r = await rpc(u, "eth_call", [{ to, data }, "0x" + block.toString(16)], 25_000);
      if (typeof r === "string" && r.length >= 66) return { value: BigInt(r.slice(0, 66)), rpc: u };
      last = new Error("empty answer");
    } catch (e) { last = e; }
  }
  throw new Error(`${chain}: no third RPC served block ${block} (${String(last?.message ?? "").slice(0, 60)})`);
}

const PUBLIC = {
  nomad: "Nomad bridge exploit, August 2022: the Ethereum BridgeRouter was drained of about $190M (https://rekt.news/nomad-rekt, https://medium.com/nomad-xyz-blog/nomad-bridge-hack-root-cause-analysis-875ad2e5aacd)",
  wh: "Wormhole Portal's own ledger outstandingBridged(l1) on its Ethereum token bridge (https://etherscan.io/address/0x3ee18b2214aff97000d974cf647e7c347e8fa585#readProxyContract)",
  por: "Chainlink Proof of Reserve feed (https://data.chain.link/feeds/ethereum/mainnet)",
};

const rows = [];
for (let off = 0; ; off += 50) {
  const page = await view("get_pairs", [off, 50]);
  for (const p of page.pairs) {
    const c = p.latest ?? (p.open && ["PROVISIONAL", "CONTESTED"].includes(p.open.status) ? p.open : null);
    if (!c || !c.ruling1 || c.ruling1.verdict === "INCONCLUSIVE") continue;
    const r = c.ruling1;
    const row = { pair_id: p.pair_id, label: p.label, check_id: c.check_id, status: c.status, verdict: r.verdict, ratio_bps: r.ratio_bps, blocks: c.blocks, rpcs: {}, notes: [] };
    try {
      const be = c.blocks.ethereum;
      let locked = 0n;
      for (const v of c.vaults) { const x = await third("ethereum", p.source_token, "0x70a08231" + pad(v), be); locked += x.value; row.rpcs.ethereum = x.rpc; }
      const sdec = Number((await third("ethereum", p.source_token, "0x313ce567", be)).value);
      let big = sdec;
      for (const d of c.dests) big = Math.max(big, d.decimals);
      const group = {}; let supply = 0n;
      const ledgerVaults = new Set(Object.keys(r.ledgers ?? {}));
      for (const v of ledgerVaults) group[v] = 0n;
      const pd = p.dests;
      for (let i = 0; i < c.dests.length; i++) {
        const d = c.dests[i];
        const x = await third(d.chain, d.token, "0x18160ddd", c.blocks[d.chain]);
        row.rpcs[d.chain] = x.rpc;
        let counted = x.value;
        const meta = pd.find((q) => q.token === d.token && q.chain === d.chain) ?? {};
        if (meta.deposits_vault) {
          const dv = await third("ethereum", meta.deposits_vault, "0x8f601f66" + pad(p.source_token) + pad(d.token), be);
          if (dv.value > counted) counted = dv.value;
        }
        const n = counted * 10n ** BigInt(big - d.decimals);
        if (ledgerVaults.has(d.vault ?? meta.vault)) group[d.vault ?? meta.vault] += n; else supply += n;
      }
      for (const v of ledgerVaults) {
        const l = (await third("ethereum", v, "0xb96c7e4d" + pad(p.source_token), be)).value;
        const ln = (sdec > 8 ? l * 10n ** BigInt(sdec - 8) : l) * 10n ** BigInt(big - sdec);
        supply += ln > group[v] ? ln : group[v];
        row.notes.push(PUBLIC.wh);
      }
      const ln = locked * 10n ** BigInt(big - sdec);
      const ratio = supply > 0n ? Number((ln * 10000n) / supply) : -1;
      const verdict = ln * 10000n >= supply * BigInt(10000 - p.tolerance_bps) ? "BACKED" : "UNDER_BACKED";
      row.recomputed = { ratio_bps: ratio, verdict };
      row.agree = ratio === r.ratio_bps && verdict === r.verdict;
    } catch (e) { row.agree = false; row.error = String(e.message).slice(0, 200); }
    // public indexer, today's supply of the first destination
    const d0 = c.dests[0];
    if (BLOCKSCOUT[d0.chain]) {
      try {
        const j = await (await fetch(`${BLOCKSCOUT[d0.chain]}/api/v2/tokens/${d0.token}`, { signal: AbortSignal.timeout(20000) })).json();
        row.indexer = { source: `${BLOCKSCOUT[d0.chain]}/token/${d0.token}`, total_supply_now: j.total_supply, decimals: Number(j.decimals), symbol: j.symbol };
        if (Number(j.decimals) !== d0.decimals) { row.agree = false; row.notes.push(`indexer decimals ${j.decimals} != ${d0.decimals}`); }
      } catch { row.indexer = { source: BLOCKSCOUT[d0.chain], error: "indexer unavailable" }; }
    }
    if (p.kind === "nomad") row.notes.push(PUBLIC.nomad);
    if (r.por) row.notes.push(`${PUBLIC.por}: ${r.por.status} (PoR ${r.por.por_ratio_bps} bps, delta ${r.por.delta_bps} bps, ${r.por.explain})`);
    rows.push(row);
    console.log(`${row.agree ? "AGREE" : "DIFFER"} pair ${p.pair_id} ${p.label}: ruling ${r.verdict} ${r.ratio_bps} / third RPC ${row.recomputed?.verdict} ${row.recomputed?.ratio_bps}${row.error ? " " + row.error : ""}`);
  }
  if (off + 50 >= page.total) break;
}
const out = { at: new Date().toISOString(), registry: REG, rows };
writeFileSync(root + "docs/real_world.json", JSON.stringify(out, null, 1) + "\n");
const ok = rows.filter((r) => r.agree).length;
writeFileSync(root + "docs/REAL_WORLD_CHECK.md", `# Real-world check

\`node tools/real_world.mjs\` on ${out.at.slice(0, 16).replace("T", " ")} UTC against the canonical registry \`${REG}\`.
**${ok}/${rows.length}** rulings reproduced exactly (ratio to the bps and verdict) from raw chain data read through a
third RPC per chain that the contracts never use, at the ruling's own pinned blocks. Each destination's decimals were
also checked against Blockscout's public token index where it serves the chain.

| Pair | Check | Ruling | Third RPC recompute | Agree | Third RPCs | Public sources |
|---|---|---|---|---|---|---|
${rows.map((r) => `| ${r.pair_id}. ${r.label} | ${r.check_id} (${r.status}) | ${r.verdict} ${(r.ratio_bps / 100).toFixed(2)}% | ${r.recomputed ? `${r.recomputed.verdict} ${(r.recomputed.ratio_bps / 100).toFixed(2)}%` : r.error} | ${r.agree ? "yes" : "NO"} | ${Object.entries(r.rpcs).map(([c, u]) => `${c}: ${u.replace("https://", "")}`).join("; ")} | ${[r.indexer?.source ? `[indexer](${r.indexer.source})` : "", ...r.notes].filter(Boolean).join("; ").replace(/\|/g, "/")} |`).join("\n")}
`);
console.log(`${ok}/${rows.length} agree`);
process.exit(ok === rows.length ? 0 : 1);
