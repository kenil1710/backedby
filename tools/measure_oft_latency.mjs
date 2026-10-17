// USDT0 (LayerZero OFT): how fast can tokens burned on a destination chain be
// released from the Ethereum adapter? Pairs OFTReceived on the Ethereum
// adapter (srcEid = Polygon or Arbitrum) with the OFTSent of the same guid
// on the source chain and measures Ethereum block time - send block time.
import { rpc as rpc0 } from "./lib/evm.mjs";
const rpc = async (...a) => { for (let i = 0; ; i++) { try { return await rpc0(...a); } catch (e) { if (i >= 4) throw e; await new Promise((r) => setTimeout(r, 3000 * (i + 1))); } } };
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";
const require = createRequire(new URL("../test/package.json", import.meta.url));
const { keccak256, toHex } = require("viem");
const ADAPTER = "0x6c96de32cea08842dcc4058c14d3aaad7fa41dee";
const SENT = keccak256(toHex("OFTSent(bytes32,uint32,address,uint256,uint256)"));
const RECV = keccak256(toHex("OFTReceived(bytes32,uint32,address,uint256)"));
const E = "https://rpc.mevblocker.io";
const SRC = { 30109: ["polygon", "https://polygon.gateway.tenderly.co", "0x6ba10300f0dc58b7a1e4c0e41f5dabb7d7829e13", 2], 30110: ["arbitrum", "https://arbitrum.gateway.tenderly.co", "0x14e4a1b13bf7f943c8ff7c51fb60fa964a298d92", 0.25] };
const head = parseInt(await rpc(E, "eth_blockNumber"));
const recv = [];
for (let to = head; recv.filter((r) => r.eid === 30109).length < 15 && to > head - 50400; to -= 500) {
  const logs = await rpc(E, "eth_getLogs", [{ address: ADAPTER, topics: [RECV], fromBlock: "0x" + (to - 499).toString(16), toBlock: "0x" + to.toString(16) }]).catch(() => []);
  for (const l of logs) { const eid = Number(BigInt("0x" + l.data.slice(2, 66))); if (SRC[eid]) recv.push({ guid: l.topics[1], eid, block: parseInt(l.blockNumber) }); }
}
console.log("received:", recv.filter((r) => r.eid === 30109).length, "from polygon,", recv.filter((r) => r.eid === 30110).length, "from arbitrum");
const out = { polygon: [], arbitrum: [] };
const tsCache = {};
const ts = async (u, n) => (tsCache[u + n] ??= parseInt((await rpc(u, "eth_getBlockByNumber", ["0x" + n.toString(16), false])).timestamp));
const pick = [...recv.filter((r) => r.eid === 30109).slice(0, 15), ...recv.filter((r) => r.eid === 30110).slice(0, 15)];
for (const r of pick) {
  const [name, u, peer, bt] = SRC[r.eid];
  const tr = await ts(E, r.block);
  const shead = parseInt(await rpc(u, "eth_blockNumber"));
  let found = null;
  for (let to = shead; !found && to > shead - Math.round(6 * 3600 / bt); to -= (name === "arbitrum" ? 10000 : 2000)) {
    const from = Math.max(0, to - (name === "arbitrum" ? 9999 : 1999));
    const logs = await rpc(u, "eth_getLogs", [{ address: peer, topics: [SENT, r.guid], fromBlock: "0x" + from.toString(16), toBlock: "0x" + to.toString(16) }]).catch(() => []);
    if (logs.length) found = parseInt(logs[0].blockNumber);
  }
  if (found) out[name].push((tr - (await ts(u, found))));
}
writeFileSync(new URL("../docs/oft-latency.json", import.meta.url), JSON.stringify({ measured_at: new Date().toISOString(), seconds: out }, null, 1) + "\n");
for (const k of Object.keys(out)) { const v = out[k].sort((a, b) => a - b); console.log(k, "n", v.length, "min", v[0], "median", v[Math.floor(v.length / 2)], "max", v[v.length - 1]); }
