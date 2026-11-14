/**
 * v2 feasibility: every new bridge template on real pairs, read the way
 * ChainReader reads them - each call at one finalized block, from the chain's
 * two RPCs, answers compared byte for byte - plus each vault's coverage (the
 * destinations the bridge's own config says it backs) and ledger.
 *   node tools/feasibility_v2.mjs   -> docs/feasibility-v2.json
 */
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { CHAINS, L1 } from "./lib/bridges.mjs";
import { WH, CCIP, SCAN_RPCS, LZ_SCAN, MULTICALL3, POR } from "./lib/v2const.mjs";
const require = createRequire(new URL("../test/package.json", import.meta.url));
const { keccak256, toHex, encodeFunctionData, decodeFunctionResult, parseAbi, decodeAbiParameters } = require("viem");

const sel = (s) => keccak256(toHex(s)).slice(0, 10);
const pad = (a) => String(a).toLowerCase().replace(/^0x/, "").padStart(64, "0");
const u = (n) => BigInt(n).toString(16).padStart(64, "0");
const A = (h) => (h && h.length >= 66 ? "0x" + h.slice(26, 66).toLowerCase() : "");
const W = (h) => (h && h.length >= 66 ? BigInt(h.slice(0, 66)) : -1n);
const str = (h) => { try { return decodeAbiParameters([{ type: "string" }], h)[0]; } catch { return ""; } };
const byt = (h) => { try { return decodeAbiParameters([{ type: "bytes" }], h)[0]; } catch { return ""; } };
const hx = (n) => "0x" + n.toString(16);

async function rpc(url, body) {
  for (let i = 0; ; i++) {
    try {
      const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(30000) });
      return JSON.parse(await r.text());
    } catch (e) { if (i >= 3) throw e; await new Promise((s) => setTimeout(s, 2000 * (i + 1))); }
  }
}
const fins = {};
async function fin(chain) {
  if (fins[chain]) return fins[chain];
  const ns = [];
  for (const url of CHAINS[chain].rpcs) { const j = await rpc(url, { jsonrpc: "2.0", id: 1, method: "eth_getBlockByNumber", params: ["finalized", false] }); ns.push(parseInt(j.result.number)); }
  return (fins[chain] = Math.min(...ns));
}
let reads = 0, agreed = 0;
const diffs = [];
/** [to, data] calls at the chain's finalized block on both RPCs, in chunks of 3; identical or throws */
async function q(chain, calls, urls = CHAINS[chain].rpcs) {
  const b = hx(await fin(chain));
  const outs = [];
  for (const url of urls) {
    const out = [];
    for (let i = 0; i < calls.length; i += 3) {
      const chunk = calls.slice(i, i + 3);
      const j = await rpc(url, chunk.map(([to, data], k) => ({ jsonrpc: "2.0", id: k, method: "eth_call", params: [{ to, data }, b] })));
      if (!Array.isArray(j)) throw new Error(`${url} not a batch: ${JSON.stringify(j).slice(0, 120)}`);
      for (let k = 0; k < chunk.length; k++) { const x = j.find((y) => y.id === k); out.push(x?.error ? (/revert/i.test(x.error.message) || x.error.code === 3 ? "REVERT" : "ERR " + x.error.message) : x?.result); }
    }
    outs.push(out);
  }
  reads += calls.length;
  const same = JSON.stringify(outs[0]) === JSON.stringify(outs[1]);
  if (same) agreed += calls.length; else diffs.push({ chain, calls: calls.map((c) => c[1].slice(0, 10)), a: outs[0], b: outs[1] });
  if (!same) throw new Error(`${chain}: the two RPCs disagree`);
  return outs[0];
}
const ETH_SEL = BigInt(CCIP.eth_selector);
const MC = parseAbi(["function aggregate3((address target,bool allowFailure,bytes callData)[] calls) payable returns ((bool success,bytes returnData)[] returnData)"]);

async function authWormhole(dest, l1, l2) {
  const [wid, tb] = WH.dests[dest];
  const e = await q("ethereum", [[WH.eth_bridge, sel("bridgeContracts(uint16)") + u(wid)], [l1, "0x313ce567"]]);
  if (A(e[0]) !== tb) throw new Error("ETH token bridge does not register " + dest);
  const d = await q(dest, [[tb, sel("wrappedAsset(uint16,bytes32)") + u(WH.eth_id) + pad(l1)], [tb, sel("isWrappedAsset(address)") + pad(l2)],
    [l2, sel("chainId()")], [l2, sel("nativeContract()")], [tb, sel("bridgeContracts(uint16)") + u(WH.eth_id)], [l2, "0x313ce567"]]);
  if (A(d[0]) !== l2) throw new Error("wrappedAsset(eth, l1) is " + A(d[0]));
  if (W(d[1]) !== 1n) throw new Error("not a wrapped asset");
  if (W(d[2]) !== BigInt(WH.eth_id) || A(d[3]) !== l1) throw new Error("wrapped token's origin is not (eth, l1)");
  if (A(d[4]) !== WH.eth_bridge) throw new Error("dest token bridge does not register the Ethereum bridge");
  return { vault: WH.eth_bridge, sd: Number(W(e[1])), dd: Number(W(d[5])) };
}
async function authCcip(dest, l1, l2) {
  const [dsel, dtar] = CCIP.dests[dest];
  const e = await q("ethereum", [[CCIP.eth_tar, sel("getPool(address)") + pad(l1)], [l1, "0x313ce567"]]);
  const pool = A(e[0]);
  const p = await q("ethereum", [[pool, sel("typeAndVersion()")], [pool, sel("getToken()")], [pool, sel("getRemoteToken(uint64)") + u(dsel)]]);
  const tv = str(p[0]);
  if (!/^LockReleaseTokenPool /.test(tv)) throw new Error("source pool is " + tv);
  if (A(p[1]) !== l1) throw new Error("source pool token");
  if (byt(p[2]).toLowerCase() !== "0x" + pad(l2)) throw new Error("source pool remote token is " + byt(p[2]));
  const d = await q(dest, [[dtar, sel("getPool(address)") + pad(l2)], [l2, "0x313ce567"]]);
  const dp = A(d[0]);
  const x = await q(dest, [[dp, sel("typeAndVersion()")], [dp, sel("getToken()")], [dp, sel("getRemoteToken(uint64)") + u(ETH_SEL)],
    [dp, sel("isRemotePool(uint64,bytes)") + u(ETH_SEL) + u(64) + u(32) + pad(pool)]]);
  const dtv = str(x[0]);
  if (!/^(BurnMintTokenPool|BurnFromMintTokenPool|BurnWithFromMintTokenPool) /.test(dtv)) throw new Error("dest pool is " + dtv);
  if (A(x[1]) !== l2) throw new Error("dest pool token");
  if (byt(x[2]).toLowerCase() !== "0x" + pad(l1)) throw new Error("dest pool remote token");
  if (W(x[3]) !== 1n) throw new Error("dest pool does not name the source pool");
  const back = await q("ethereum", [[pool, sel("isRemotePool(uint64,bytes)") + u(dsel) + u(64) + u(32) + pad(dp)]]);
  if (W(back[0]) !== 1n) throw new Error("source pool does not name the dest pool");
  return { vault: pool, sd: Number(W(e[1])), dd: Number(W(d[1])), tv, dtv, dpool: dp };
}
async function lzScan(adapter) {
  const b = hx(await fin("ethereum"));
  const calls = [];
  for (let e = LZ_SCAN[0]; e < LZ_SCAN[1]; e++) calls.push({ target: adapter, allowFailure: true, callData: sel("peers(uint32)") + u(e) });
  const data = encodeFunctionData({ abi: MC, functionName: "aggregate3", args: [calls] });
  const outs = [];
  for (const url of SCAN_RPCS) {
    const j = await rpc(url, { jsonrpc: "2.0", id: 1, method: "eth_call", params: [{ to: MULTICALL3, data }, b] });
    if (!j.result) throw new Error("scan " + url + " " + JSON.stringify(j.error).slice(0, 100));
    const r = decodeFunctionResult({ abi: MC, functionName: "aggregate3", data: j.result });
    outs.push(r.map((x, i) => (x.success && BigInt(x.returnData) !== 0n ? [LZ_SCAN[0] + i, x.returnData] : null)).filter(Boolean));
  }
  if (JSON.stringify(outs[0]) !== JSON.stringify(outs[1])) throw new Error("scan RPCs disagree");
  return outs[0];
}

const LZ_CHAIN = { 30101: "ethereum", 30109: "polygon", 30110: "arbitrum", 30111: "optimism", 30184: "base", 30181: "mantle", 30274: "xlayer", 30280: "sei", 30295: "flare", 30316: "hedera", 30320: "unichain", 30322: "morph", 30339: "ink", 30362: "berachain", 30367: "hyperevm", 30390: "monad" };
const CCIP_CHAIN = Object.fromEntries(Object.entries(CCIP.dests).map(([c, [s]]) => [s, c]));

const WHT = {
  USDC: { polygon: "0x4318cb63a2b8edf2de971e2f17f77097e499459d", arbitrum: "0xc96f2715e2a242d50d1b0bc923dbe1740b8ecf18", optimism: "0x711e53d031ea9b0bb0c24dd506df11b41aea419e", base: "0xec267c53f53807c2337c257f8ac3fc3cc07cc0ed" },
  WETH: { polygon: "0x11cd37bb86f65419713f30673a480ea33c826872", arbitrum: "0xd8369c2eda18dd6518eabb1f85bd60606deb39ec", optimism: "0xb47bc3ed6d70f04fe759b2529c9bc7377889678f", base: "0x71b35ecb35104773537f849fbc353f81303a5860" },
  USDT: { polygon: "0x9417669fbf23357d2774e9d421307bd5ea1006d2", arbitrum: "0xe4728f3e48e94c6da2b53610e677cc241dafb134", optimism: "0xf6b4185fcf8af291c0e3927fbeab7046b4f6a8ca", base: "0xff0c62a4979400841efaa6faadb07ac7d5c98b27" },
  WBTC: { polygon: "0x5d49c278340655b56609fdf8976eb0612af3a0c3", arbitrum: "0x397846a8078d4845c7f5c6ca76aebbcfdc044fae", optimism: "0xb214c19d81c99e75e84706a3aa0a757319023e26", base: "0xe6396f780b543df16ee3b784d789c75b68319db0" },
  DAI: { polygon: "0x732eb1747eccfc431ff19bc359ffc83755b1918c", arbitrum: "0x5c4f2fefb97f7df09e762d95c83f0ccf8bce8234", optimism: "0x098ea47d630b46df1e08e389e5e4466119c7dd30", base: "0x617edadb51bfb43a44bb91c7402129c23ba52381" },
};
const CCIP_PAIRS = {
  GHO: ["0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", { arbitrum: "0x7dff72693f6a4149b17e7c6314655f6a9f7c8b33", base: "0x6bb7a212910682dcfdbd5bcbb3e28fb4e8da10ee", ink: "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73", mantle: "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73", xlayer: "0xde6539018b095353a40753dc54c91c68c9487d4e", monad: "0xfc421ad3c883bf9e7c4f42de845c4e4405799e73" }],
  rsETH: ["0xa1290d69c65a6fe4df752f95823fae25cb99e5a7", { optimism: "0x043849686ee254ada46a432770e1a491491fc44d", base: "0xe2110d5a2722abd8c8002646c645af15f5e9db1f", mantle: "0x91a8aa510d20b2c1b27512777a1b6bd7e0552579", ink: "0x3c29af7a7b7ec62a481d27ed297b90c1974a0230" }],
  syrupUSDC: ["0x80ac24aa929eaf5013f6436cda2a7ba190f5cc0b", { xlayer: "0xd503b0581aa504e75b345bf4cb8c359d8d1a042f", arbitrum: "0x41ca7586cc1311807b4605fbb748a3b8862b42b5", base: "0x660975730059246a68521a3e2fbd4740173100f5", ink: "0x3c23e6fb09064e9a64829fa8fee27ad19a27bfa9", monad: "0xab6e5a0c3799d020c790d34f7b2c02639e238af7" }],
};
const LZ_ADAPTERS = { weETH: "0xcd2eb13d6831d4602d80e5db9230a57596cdca63", WBTC: "0x0555e30da8f98308edb960aa94c0db47230d2b9c", rsETH: "0x85d456b2dff1fd8245387c0bfb64dfb700e98ef3" };
const LZ_L1 = { weETH: "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee", WBTC: L1.WBTC, rsETH: "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7" };

const out = { at: new Date().toISOString(), wormhole: [], ccip: [], layerzero: [], por: [] };
const row = async (arr, base, fn) => { try { arr.push({ ...base, ok: true, ...(await fn()) }); console.log("OK  ", JSON.stringify(base)); } catch (e) { arr.push({ ...base, ok: false, why: String(e.message).slice(0, 160) }); console.log("FAIL", JSON.stringify(base), e.message); } };

for (const [sym, dests] of Object.entries(WHT)) {
  const l1 = L1[sym];
  const led = await q("ethereum", [[WH.eth_bridge, sel("outstandingBridged(address)") + pad(l1)], [l1, "0x70a08231" + pad(WH.eth_bridge)], [l1, "0x313ce567"]]);
  const sd = Number(W(led[2]));
  const ledger = W(led[0]) * 10n ** BigInt(Math.max(sd - 8, 0));
  const pair = { sym, l1, vault: WH.eth_bridge, locked: W(led[1]).toString(), ledger_native: ledger.toString(), dests: [] };
  for (const [c, l2] of Object.entries(dests)) await row(pair.dests, { chain: c, l2 }, async () => { const a = await authWormhole(c, l1, l2); const s = await q(c, [[l2, "0x18160ddd"]]); return { ...a, supply: W(s[0]).toString() }; });
  pair.ratio_vs_ledger_bps = ledger > 0n ? Number((W(led[1]) * 10000n) / ledger) : null;
  out.wormhole.push(pair);
}
for (const [sym, [l1, dests]] of Object.entries(CCIP_PAIRS)) {
  const pool = A((await q("ethereum", [[CCIP.eth_tar, sel("getPool(address)") + pad(l1)]]))[0]);
  const e = await q("ethereum", [[pool, sel("getSupportedChains()")], [l1, "0x70a08231" + pad(pool)]]);
  const supported = decodeAbiParameters([{ type: "uint64[]" }], e[0])[0].map(String);
  const pair = { sym, l1, vault: pool, locked: W(e[1]).toString(), supported, dests: [] };
  for (const [c, l2] of Object.entries(dests)) await row(pair.dests, { chain: c, l2 }, async () => { const a = await authCcip(c, l1, l2); const s = await q(c, [[l2, "0x18160ddd"]]); return { ...a, supply: W(s[0]).toString() }; });
  const listed = Object.keys(dests).map((c) => CCIP.dests[c][0]);
  pair.unlisted = supported.filter((s) => !listed.includes(s)).map((s) => ({ selector: s, chain: CCIP_CHAIN[s] ?? null }));
  out.ccip.push(pair);
}
for (const [sym, adapter] of Object.entries(LZ_ADAPTERS)) {
  const l1 = LZ_L1[sym];
  const peers = await lzScan(adapter);
  const bal = await q("ethereum", [[l1, "0x70a08231" + pad(adapter)]]);
  out.layerzero.push({ sym, l1, vault: adapter, locked: W(bal[0]).toString(), scan_range: LZ_SCAN, peers: peers.map(([e, p]) => ({ eid: e, chain: LZ_CHAIN[e] ?? null, peer: p })) });
  console.log("LZ", sym, peers.length, "peers;", peers.filter(([e]) => LZ_CHAIN[e]).length, "on readable chains");
}
for (const [tok, [feed, supTok, name]] of Object.entries(POR)) {
  const r = await q("ethereum", [[feed, sel("latestRoundData()")], [feed, "0x313ce567"], [supTok, "0x18160ddd"], [supTok, "0x313ce567"]]);
  out.por.push({ token: tok, feed, name, answer: BigInt("0x" + r[0].slice(66, 130)).toString(), updated_at: Number(BigInt("0x" + r[0].slice(194, 258))), decimals: Number(W(r[1])), supply: W(r[2]).toString(), supply_decimals: Number(W(r[3])) });
}
out.reads = reads; out.agreed = agreed; out.diffs = diffs;
writeFileSync(new URL("../docs/feasibility-v2.json", import.meta.url), JSON.stringify(out, null, 1) + "\n");
console.log(`reads ${reads}, identical on both RPCs ${agreed}`);
