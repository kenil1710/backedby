/**
 * Where an over-backed pair's surplus comes from, from raw chain data. For
 * every pair on the canonical registry whose shown ruling is above 100%, the
 * surplus (vault minus counted supply, at the ruling's pinned blocks) is split
 * into parts that are each read from chain:
 *
 *   - escrow flows (DAI on OP Mainnet): every DAI Transfer into and out of the
 *     escrow since its creation, up to the pinned Ethereum block, matched by
 *     transaction to the bridge's own ERC20DepositInitiated /
 *     ERC20WithdrawalFinalized events. Bridge deposits - bridge withdrawals -
 *     L2 supply is what was burned on OP and is still escrowed (withdrawals
 *     not yet finalized, teleports not yet settled); the transfers that are
 *     not bridge deposits or withdrawals are the rest. The parts add up exactly.
 *   - unlisted destinations (coverage GAP): the supply of each destination
 *     the vault's bridge config names but the pair does not list, read from a
 *     public RPC of that chain (not used for any verdict).
 *   - Wormhole: the vault above the bridge's own ledger outstandingBridged.
 * Whatever is not attributed is shown as such.
 *   node tools/explain_surplus.mjs   -> docs/surplus.json, frontend/src/lib/surplus.json
 */
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { rpc } from "./lib/evm.mjs";
import { CHAINS } from "./lib/bridges.mjs";
const require = createRequire(new URL("../test/package.json", import.meta.url));
const { createClient } = require("genlayer-js");
const { studioDevnet } = require("genlayer-js/chains");
const { keccak256, toHex, decodeAbiParameters } = require("viem");

const root = new URL("..", import.meta.url).pathname;
const dep = JSON.parse(readFileSync(root + "deployments.json", "utf8")).contracts;
const REG = dep.BackedByRegistry.address;
const client = createClient({ chain: studioDevnet });
const view = async (fn, args) => { for (let i = 0; ; i++) { try { const r = await client.readContract({ address: REG, functionName: fn, args }); return typeof r === "string" ? JSON.parse(r) : JSON.parse(JSON.stringify(r, (k, v) => (typeof v === "bigint" ? v.toString() : v instanceof Map ? Object.fromEntries(v) : v))); } catch (e) { if (i > 4) throw e; await new Promise((s) => setTimeout(s, 3000 * (i + 1))); } } };
const topic = (s) => keccak256(toHex(s));
const pad = (a) => "0x" + a.slice(2).toLowerCase().padStart(64, "0");
const LOGS_RPC = "https://rpc.mevblocker.io";          // serves eth_getLogs over 500k-block ranges
const TR = topic("Transfer(address,address,uint256)");
const DEP = topic("ERC20DepositInitiated(address,address,address,address,uint256,bytes)");
const FIN = topic("ERC20WithdrawalFinalized(address,address,address,address,uint256,bytes)");

async function logs(filter, from, to, step = 500_000) {
  const out = [];
  for (let a = from; a <= to; a += step) {
    const b = Math.min(a + step - 1, to);
    for (let i = 0; ; i++) {
      try { out.push(...(await rpc(LOGS_RPC, "eth_getLogs", [{ ...filter, fromBlock: "0x" + a.toString(16), toBlock: "0x" + b.toString(16) }], 60_000))); break; }
      catch (e) { if (i > 5) throw e; await new Promise((s) => setTimeout(s, 4000 * (i + 1))); }
    }
  }
  return out;
}

/** DAI on OP: escrow inflows/outflows matched to the bridge's own events. */
async function escrowFlows({ token, escrow, from, to, supply }) {
  const ins = await logs({ address: token, topics: [TR, null, pad(escrow)] }, from, to);
  const outs = await logs({ address: token, topics: [TR, pad(escrow)] }, from, to);
  const deps = await logs({ topics: [DEP, pad(token)] }, from, to);
  const fins = await logs({ topics: [FIN, pad(token)] }, from, to);
  const depTx = new Set(deps.map((l) => l.transactionHash));
  const finTx = new Set(fins.map((l) => l.transactionHash));
  const amt = (l) => BigInt(l.data.slice(0, 66));
  let bridgeIn = 0n, otherIn = 0n, bridgeOut = 0n, otherOut = 0n;
  const otherInTx = [], otherOutTx = [];
  for (const l of ins) { if (depTx.has(l.transactionHash)) bridgeIn += amt(l); else { otherIn += amt(l); otherInTx.push([amt(l), l.transactionHash]); } }
  for (const l of outs) { if (finTx.has(l.transactionHash)) bridgeOut += amt(l); else { otherOut += amt(l); otherOutTx.push([amt(l), l.transactionHash]); } }
  const top = (xs) => xs.sort((a, b) => (b[0] > a[0] ? 1 : -1)).slice(0, 3).map((x) => `https://etherscan.io/tx/${x[1]}`);
  return {
    counts: { transfers_in: ins.length, transfers_out: outs.length, deposit_events: deps.length, withdrawal_events: fins.length },
    balance_from_logs: (bridgeIn + otherIn - bridgeOut - otherOut).toString(),
    components: [
      { name: "Burned on OP, still escrowed: withdrawals not yet finalized and teleports not yet settled", amount: (bridgeIn - bridgeOut - supply).toString(),
        source: `bridge deposits ${bridgeIn} - bridge withdrawals ${bridgeOut} (DAI Transfers in the same transactions as the bridge's ERC20DepositInitiated / ERC20WithdrawalFinalized, Ethereum blocks ${from}-${to}) - OP supply at the pinned block` },
      { name: "Moved into the escrow outside bridge deposits", amount: otherIn.toString(), source: `${otherInTx.length} DAI Transfers to the escrow without a bridge deposit event`, links: top(otherInTx) },
      { name: "Moved out of the escrow outside bridge withdrawals (Teleport settlements)", amount: (-otherOut).toString(), source: `${otherOutTx.length} DAI Transfers from the escrow without a bridge withdrawal event`, links: top(otherOutTx) },
    ],
  };
}

// one public RPC per chain id, for reading unlisted destinations' supply (explanation only, never a verdict)
const EXTRA_RPC = { 56: "https://bsc-rpc.publicnode.com", 43114: "https://api.avax.network/ext/bc/C/rpc", 100: "https://rpc.gnosischain.com",
  59144: "https://rpc.linea.build", 9745: "https://rpc.plasma.to" };
const ID_RPC = Object.fromEntries(Object.values(CHAINS).map((c) => [c.id, c.rpcs[1]]));
const ccipNames = JSON.parse(readFileSync(root + "frontend/src/lib/ccip-names.json", "utf8"));
const LZ_CHAIN_ID = { 30102: 56, 30106: 43114, 30145: 100, 30183: 59144, 30109: 137, 30110: 42161, 30111: 10, 30184: 8453, 30181: 5000, 30274: 196,
  30280: 1329, 30295: 14, 30316: 295, 30320: 130, 30322: 2818, 30339: 57073, 30362: 80094, 30367: 999, 30390: 143 };
const call = (url, to, data) => rpc(url, "eth_call", [{ to, data }, "latest"]);

async function unlistedSupply(pair, item, scale, srcDec) {
  const [fam, n] = item.id.split(":");
  let chainId, token;
  try {
    if (fam === "ccip") {
      chainId = ccipNames[n]?.chain_id;
      const r = await call(CHAINS.ethereum.rpcs[1], item.vault, "0xb7946580" + BigInt(n).toString(16).padStart(64, "0"));
      token = "0x" + decodeAbiParameters([{ type: "bytes" }], r)[0].slice(-40);
    } else if (fam === "lz") {
      chainId = LZ_CHAIN_ID[n];
      const r = await call(CHAINS.ethereum.rpcs[1], item.vault, "0xbb0b6a53" + BigInt(n).toString(16).padStart(64, "0"));
      token = "0x" + r.slice(26, 66);
    }
    const url = EXTRA_RPC[chainId] ?? ID_RPC[chainId];
    if (!url || !/^0x[0-9a-f]{40}$/.test(token)) return { name: `Unlisted ${item.id}`, amount: "0", source: "no public RPC of that chain is known here; not read" };
    // an OFT adapter's token() is the token, a native OFT is the token itself
    let t = token;
    try { const tk = await call(url, token, "0xfc0c546a"); if (tk && tk.length >= 66 && BigInt(tk) !== 0n) t = "0x" + tk.slice(26, 66); } catch { /* the token itself */ }
    const sup = BigInt(await call(url, t, "0x18160ddd"));
    const dec = Number(BigInt(await call(url, t, "0x313ce567")));
    const norm = sup * 10n ** BigInt(scale - dec);
    return { name: `Supply on ${fam === "ccip" ? ccipNames[n]?.name ?? n : "eid " + n}, not listed in the pair`, amount: norm.toString(),
      source: `${t} totalSupply() via ${url.replace("https://", "")} (chain id ${chainId}); the vault's own bridge config names it` };
  } catch (e) {
    return { name: `Unlisted ${item.id}`, amount: "0", source: "could not be read: " + String(e.message).slice(0, 80) };
  }
}

const out = { at: new Date().toISOString(), registry: REG, pairs: [] };
for (let off = 0; ; off += 50) {
  const page = await view("get_pairs", [off, 50]);
  for (const p of page.pairs) {
    const shown = p.latest ?? (p.open?.status === "PROVISIONAL" ? p.open : null);
    const r = shown?.ruling1;
    if (!r || r.ratio_bps <= 10000 || !r.locked_norm) continue;
    const scale = r.scale_decimals;
    const surplus = BigInt(r.locked_norm) - BigInt(r.supply_norm);
    const row = { pair_id: p.pair_id, registry: REG, label: p.label, check_id: shown.check_id, ratio_bps: r.ratio_bps, surplus_norm: surplus.toString(),
      scale_decimals: scale, symbol: p.label.split(" ")[0], components: [], residual: "0" };
    let attributed = 0n;
    if (p.kind === "op_dai") {
      const f = await escrowFlows({ token: p.source_token, escrow: p.vault, from: 12_400_000, to: shown.blocks.ethereum, supply: BigInt(r.counted[0]) });
      const k = 10n ** BigInt(scale - p.source_decimals);
      row.components.push(...f.components.map((c) => ({ ...c, amount: (BigInt(c.amount) * k).toString() })));
      row.note = `Read from ${f.counts.transfers_in} transfers in, ${f.counts.transfers_out} out, ${f.counts.deposit_events} deposit and ${f.counts.withdrawal_events} withdrawal events; their sum equals the escrow's balance at the pinned block: ${f.balance_from_logs}.`;
    }
    for (const [v, led] of Object.entries(r.ledgers ?? {})) {
      const locked = BigInt(r.locked_norm);
      if (BigInt(led.counted_norm) === BigInt(led.ledger_norm)) row.components.push({ name: "Vault above Wormhole's own ledger (outstandingBridged)", amount: (locked - BigInt(led.ledger_norm)).toString(), source: `${v}: ledger ${led.ledger_norm} at the pinned block` });
    }
    for (const item of r.coverage?.unlisted ?? []) row.components.push(await unlistedSupply(p, item, scale, p.source_decimals));
    for (const c of row.components) attributed += BigInt(c.amount);
    row.residual = (surplus - attributed).toString();
    out.pairs.push(row);
    console.log(`pair ${p.pair_id} ${p.label}: surplus ${surplus} (scale ${scale}), attributed ${attributed}, residual ${row.residual}`);
  }
  if (off + 50 >= page.total) break;
}
writeFileSync(root + "docs/surplus.json", JSON.stringify(out, null, 1) + "\n");
writeFileSync(root + "frontend/src/lib/surplus.json", JSON.stringify(out, null, 1) + "\n");
console.log(`wrote docs/surplus.json: ${out.pairs.length} over-backed pairs`);
