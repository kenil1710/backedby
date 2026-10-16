/**
 * STEP 0. Reads real numbers for candidate bridge pairs from TWO public RPCs
 * per chain, at one finalized block per chain, with plain JSON-RPC.
 *
 *   node tools/feasibility.mjs     -> docs/feasibility.json + docs/FEASIBILITY.md
 *
 * Each pair is authenticated by the bridge's own on-chain mapping (the same
 * rules ChainReader applies) before anything is read; every value is read
 * from both RPCs and must be identical.
 */
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { rpc } from "./lib/evm.mjs";
import { pinBlocks } from "./lib/pin.mjs";
import { CHAINS, BRIDGE, L1 } from "./lib/bridges.mjs";
const require = createRequire(new URL("../test/package.json", import.meta.url));
const { toFunctionSelector } = require("viem");
const S = (sig) => toFunctionSelector(sig);
const pad = (a) => String(a).toLowerCase().replace(/^0x/, "").padStart(64, "0");
const asAddr = (h) => (h && h.length >= 66 ? "0x" + h.slice(-40) : null);

let fin = {};
/** Both RPCs must return the identical header for the pinned block. */
async function checkBlock(chain, b) {
  const hx = "0x" + b.number.toString(16);
  const [ba, bb] = await Promise.all(CHAINS[chain].rpcs.map((u) => rpc(u, "eth_getBlockByNumber", [hx, false])));
  return { ...b, agree: ba.hash === bb.hash && ba.timestamp === bb.timestamp && parseInt(ba.timestamp) === b.timestamp };
}

/** eth_call at the pinned block on both RPCs -> { a, b, agree } (null on revert). */
async function dual(chain, to, data) {
  const hx = "0x" + fin[chain].number.toString(16);
  const one = async (u) => {
    for (let i = 0; i < 3; i++) {
      try { return await rpc(u, "eth_call", [{ to, data }, hx]); }
      catch (e) { if (/revert|execution reverted|VM Exception/i.test(e.message)) return null; if (i === 2) return "ERR:" + e.message.slice(0, 60); await new Promise((r) => setTimeout(r, 1500)); }
    }
  };
  const [a, b] = await Promise.all(CHAINS[chain].rpcs.map(one));
  return { a, b, agree: a === b && !(String(a).startsWith("ERR")), v: a === b ? a : undefined };
}
const notes = [];
async function v(chain, to, sig, args = "") {
  const r = await dual(chain, to, S(sig) + args);
  if (!r.agree) notes.push(`${chain} ${to} ${sig}: RPC A=${String(r.a).slice(0, 20)} B=${String(r.b).slice(0, 20)}`);
  return r;
}
const uint = (r) => (r.v && r.v !== "0x" ? BigInt(r.v.slice(0, 66)) : null);

/** Authenticate a candidate with the bridge's own mapping -> { ok, vault, dest, why, proof[] } */
async function authenticate(c) {
  const proof = [];
  const l1 = L1[c.sym];
  const eq = (x, y) => x && y && x.toLowerCase() === y.toLowerCase();
  if (c.kind === "arbitrum") {
    const gw = asAddr((await v("ethereum", BRIDGE.arb_l1_router, "getGateway(address)", pad(l1))).v);
    const l2 = asAddr((await v("ethereum", BRIDGE.arb_l1_router, "calculateL2TokenAddress(address)", pad(l1))).v);
    const l2b = asAddr((await v("arbitrum", BRIDGE.arb_l2_router, "calculateL2TokenAddress(address)", pad(l1))).v);
    proof.push(`L1GatewayRouter.getGateway = ${gw}`, `L1GatewayRouter.calculateL2TokenAddress = ${l2}`, `L2GatewayRouter.calculateL2TokenAddress = ${l2b}`);
    if (!gw || /^0x0+$/.test(gw)) return { ok: false, why: "router has no gateway for this token", proof };
    if (!eq(l2, l2b)) return { ok: false, why: "L1 and L2 routers disagree", proof };
    const esc = await v("ethereum", gw, "l1Escrow()");
    const vault = esc.v && esc.v.length >= 66 ? asAddr(esc.v) : gw;
    proof.push(esc.v && esc.v.length >= 66 ? `gateway.l1Escrow = ${vault}` : `gateway holds the escrow (no l1Escrow())`);
    return { ok: true, vault, dest: [{ chain: "arbitrum", token: l2 }], proof };
  }
  if (c.kind === "optimism" || c.kind === "base") {
    const l2 = c.dest;
    let rt = asAddr((await v(c.kind, l2, "remoteToken()")).v);
    if (!rt) rt = asAddr((await v(c.kind, l2, "l1Token()")).v);
    let br = asAddr((await v(c.kind, l2, "bridge()")).v);
    if (!br) br = asAddr((await v(c.kind, l2, "l2Bridge()")).v);
    proof.push(`l2token.remoteToken/l1Token = ${rt}`, `l2token.bridge/l2Bridge = ${br}`);
    if (!eq(rt, l1)) return { ok: false, why: "remote token is not the source token", proof };
    if (!eq(br, BRIDGE.l2_std_bridge)) return { ok: false, why: "not minted by the L2StandardBridge", proof };
    const vault = c.kind === "optimism" ? BRIDGE.op_l1_bridge : BRIDGE.base_l1_bridge;
    const dep = uint(await v("ethereum", vault, "deposits(address,address)", pad(l1) + pad(l2)));
    proof.push(`L1StandardBridge.deposits(l1,l2) = ${dep}`);
    return { ok: true, vault, dest: [{ chain: c.kind, token: l2 }], proof, deposits: dep };
  }
  if (c.kind === "op_dai") {
    const a = asAddr((await v("ethereum", BRIDGE.op_dai_l1_bridge, "l1Token()")).v);
    const b = asAddr((await v("ethereum", BRIDGE.op_dai_l1_bridge, "l2Token()")).v);
    const esc = asAddr((await v("ethereum", BRIDGE.op_dai_l1_bridge, "escrow()")).v);
    const c1 = asAddr((await v("optimism", BRIDGE.op_dai_l2_bridge, "l1Token()")).v);
    const c2 = asAddr((await v("optimism", BRIDGE.op_dai_l2_bridge, "l2Token()")).v);
    const c3 = asAddr((await v("optimism", BRIDGE.op_dai_l2_bridge, "l1DAITokenBridge()")).v);
    proof.push(`L1DAITokenBridge l1Token=${a} l2Token=${b} escrow=${esc}`, `L2DAITokenBridge l1Token=${c1} l2Token=${c2} l1DAITokenBridge=${c3}`);
    if (!eq(a, l1) || !eq(c1, l1) || !eq(b, c2) || !eq(c3, BRIDGE.op_dai_l1_bridge)) return { ok: false, why: "DAI bridge mapping mismatch", proof };
    return { ok: true, vault: esc, dest: [{ chain: "optimism", token: b }], proof };
  }
  if (c.kind === "polygon") {
    const child = asAddr((await v("ethereum", BRIDGE.pol_root_manager, "rootToChildToken(address)", pad(l1))).v);
    const typ = (await v("ethereum", BRIDGE.pol_root_manager, "tokenToType(address)", pad(l1))).v;
    const pred = asAddr((await v("ethereum", BRIDGE.pol_root_manager, "typeToPredicate(bytes32)", (typ || "0x").slice(2))).v);
    const root = child ? asAddr((await v("polygon", BRIDGE.pol_child_manager, "childToRootToken(address)", pad(child))).v) : null;
    proof.push(`RootChainManager.rootToChildToken = ${child}`, `RootChainManager.typeToPredicate(tokenToType) = ${pred}`, `ChildChainManager.childToRootToken = ${root}`);
    if (!child || /^0x0+$/.test(child) || !eq(root, l1)) return { ok: false, why: "root/child mapping mismatch", proof };
    return { ok: true, vault: pred, dest: [{ chain: "polygon", token: child }], proof };
  }
  if (c.kind === "nomad") {
    const rep = c.dest;
    const reg = asAddr((await v("moonbeam", BRIDGE.nomad_beam_router, "tokenRegistry()")).v);
    const tid = (await v("moonbeam", reg, "getTokenId(address)", pad(rep))).v;
    const dom = tid ? Number(BigInt("0x" + tid.slice(2, 66))) : -1;
    const id = tid ? "0x" + tid.slice(-40) : null;
    const back = asAddr((await v("moonbeam", reg, "getLocalAddress(uint32,bytes32)", pad(BRIDGE.nomad_eth_domain.toString(16)) + pad(l1))).v);
    const remote = asAddr((await v("moonbeam", BRIDGE.nomad_beam_router, "remotes(uint32)", pad(BRIDGE.nomad_eth_domain.toString(16)))).v);
    const ereg = asAddr((await v("ethereum", BRIDGE.nomad_eth_router, "tokenRegistry()")).v);
    const etid = (await v("ethereum", ereg, "getTokenId(address)", pad(l1))).v;
    const edom = etid ? Number(BigInt("0x" + etid.slice(2, 66))) : -1;
    proof.push(`Moonbeam TokenRegistry ${reg}: getTokenId(rep) = (domain ${dom}, ${id})`, `getLocalAddress(eth, l1) = ${back}`,
      `Moonbeam BridgeRouter.remotes(eth) = ${remote}`, `Ethereum TokenRegistry.getTokenId(l1) domain = ${edom} (local origin)`);
    if (dom !== BRIDGE.nomad_eth_domain || !eq(id, l1) || !eq(back, rep) || !eq(remote, BRIDGE.nomad_eth_router) || edom !== BRIDGE.nomad_eth_domain)
      return { ok: false, why: "Nomad mapping mismatch", proof };
    return { ok: true, vault: remote, dest: [{ chain: "moonbeam", token: rep }], proof };
  }
  return { ok: false, why: "unknown kind", proof };
}

const CAND = [
  ...["USDC", "DAI", "WBTC", "LINK", "UNI", "AAVE", "CRV", "LDO", "wstETH", "USDT"].map((sym) => ({ kind: "arbitrum", sym })),
  { kind: "optimism", sym: "USDC", dest: "0x7f5c764cbc14f9669b88837ca1490cca17c31607" },
  { kind: "optimism", sym: "USDT", dest: "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58" },
  { kind: "optimism", sym: "WBTC", dest: "0x68f180fcce6836688e9084f035309e29bf0a2095" },
  { kind: "optimism", sym: "LINK", dest: "0x350a791bfc2c21f9ed5d10980dad2e2638ffa7f6" },
  { kind: "optimism", sym: "UNI", dest: "0x6fd9d7ad17242c41f7131d257212c54a0e816691" },
  { kind: "optimism", sym: "AAVE", dest: "0x76fb31fb4af56892a25e32cfc43de717950c9278" },
  { kind: "optimism", sym: "CRV", dest: "0x0994206dfe8de6ec6920ff4d779b0d950605fb53" },
  { kind: "optimism", sym: "LDO", dest: "0xfdb794692724153d1488ccdbe0c56c252596735f" },
  { kind: "op_dai", sym: "DAI" },
  { kind: "base", sym: "USDC", dest: "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca" },
  { kind: "base", sym: "DAI", dest: "0x50c5725949a6f0c72e6c4a641f24049a917db0cb" },
  { kind: "base", sym: "cbETH", dest: "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22" },
  { kind: "base", sym: "rETH", dest: "0xb6fe221fe9eef5aba221c348ba20a1bf5e73624c" },
  { kind: "base", sym: "LINK", dest: "0x88fb150bdc53a65fe94dea0c9ba0a6daf8c6e196" },
  ...["USDC", "USDT", "DAI", "WBTC", "LINK", "AAVE", "UNI", "CRV", "LDO"].map((sym) => ({ kind: "polygon", sym })),
  { kind: "nomad", sym: "USDC", dest: "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9" },
  { kind: "nomad", sym: "WETH", dest: "0x30d2a9f5fdf90ace8c17952cbb4ee48a55d916a7" },
  { kind: "nomad", sym: "WBTC", dest: "0x1dc78acda13a8bc4408b207c9e48cdbc096d95e0" },
  { kind: "nomad", sym: "USDT", dest: "0x8e70cd5b4ff3f62659049e74b6649c6603a0e594" },
  { kind: "nomad", sym: "DAI", dest: "0xc234a67a4f840e61ade794be47de455361b52413" },
  // a fake: an arbitrary token passed off as bridged USDC (must be refused)
  { kind: "optimism", sym: "USDC", dest: "0x0b2c639c533813f4aa9d7837caf62653d097ff85", fake: "native USDC on OP, not a bridge token" },
];

const started = new Date().toISOString();
const destOf = (k) => ({ op_dai: "optimism", nomad: "moonbeam" }[k] ?? k);
const PINS = {};
for (const d of [...new Set(CAND.map((c) => destOf(c.kind)))]) {
  const p = await pinBlocks("ethereum", [d]);
  PINS[d] = { ethereum: await checkBlock("ethereum", p.blocks.ethereum), [d]: await checkBlock(d, p.blocks[d]), gap_s: p.gap };
  console.log(`pins for ${d}: ethereum ${p.blocks.ethereum.number} @${new Date(p.blocks.ethereum.timestamp * 1000).toISOString()}  ${d} ${p.blocks[d].number} @${new Date(p.blocks[d].timestamp * 1000).toISOString()}  gap ${p.gap}s`);
}
const rows = [];
for (const c of CAND) {
  notes.length = 0;
  fin = PINS[destOf(c.kind)];
  const l1 = L1[c.sym];
  const auth = await authenticate(c);
  const row = { kind: c.kind, sym: c.sym, source_token: l1, fake: c.fake ?? null, ...auth, blocks: fin };
  if (auth.ok) {
    const sd = uint(await v("ethereum", l1, "decimals()"));
    const locked = uint(await v("ethereum", l1, "balanceOf(address)", pad(auth.vault)));
    let supply = 0n; const dd = [];
    for (const d of auth.dest) {
      const dec = uint(await v(d.chain, d.token, "decimals()"));
      const sup = uint(await v(d.chain, d.token, "totalSupply()"));
      d.decimals = Number(dec); d.supply = String(sup); dd.push(Number(dec));
      supply += sup * 10n ** BigInt(18 - Number(dec));
    }
    const lockedN = locked * 10n ** BigInt(18 - Number(sd));
    row.source_decimals = Number(sd); row.locked = String(locked);
    row.locked_norm = String(lockedN); row.supply_norm = String(supply);
    row.ratio = supply === 0n ? null : Number((lockedN * 1000000n) / supply) / 1e6;
    row.decimals_match = dd.every((x) => x === Number(sd));
    row.agree = notes.length === 0 && fin.ethereum.agree && fin[destOf(c.kind)].agree;
    row.disagreements = [...notes];
    row.verdict = !row.agree ? "INCONCLUSIVE" : supply === 0n ? "BACKED" : lockedN >= supply ? "BACKED" : "UNDER_BACKED";
  }
  rows.push(row);
  console.log(`${c.kind.padEnd(8)} ${c.sym.padEnd(6)} ${auth.ok ? "AUTH" : "REFUSED " + auth.why}${auth.ok ? `  ratio ${row.ratio}  ${row.verdict}  agree ${row.agree}` : ""}`);
}
writeFileSync(new URL("../docs/feasibility.json", import.meta.url), JSON.stringify({ started, pins: PINS, rows }, (k, x) => (typeof x === "bigint" ? String(x) : x), 2) + "\n");
