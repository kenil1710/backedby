// Polygon PoS: the fastest a burn on Polygon can be released from the Ethereum
// predicate is bounded below by checkpoint latency: the burn's block must be
// inside a checkpoint (NewHeaderBlock on RootChainProxy) before an exit can be
// proven. Measures (L1 inclusion time - timestamp of the checkpoint's end block)
// over recent checkpoints. Output feeds docs/RULES.md.
import { rpc } from "./lib/evm.mjs";
import { CHAINS } from "./lib/bridges.mjs";
const E = "https://rpc.mevblocker.io", L = CHAINS.ethereum.rpcs[0], P = CHAINS.polygon.rpcs[1];
const ROOT = "0x86e4dc95c7fbdbf52e33d563bbdb00823894c287";
const TOPIC = "0xba5de06d22af2685c6c7765f60067f7d2b08c2d29f53cdf14d67f6d1c9bfb527"; // NewHeaderBlock
const head = parseInt(await rpc(E, "eth_blockNumber"));
const out = [];
for (let to = head; out.length < 60 && to > head - 7200 * 4; to -= 800) {
  const logs = await rpc(E, "eth_getLogs", [{ address: ROOT, topics: [TOPIC], fromBlock: "0x" + (to - 799).toString(16), toBlock: "0x" + to.toString(16) }]).catch((e) => { console.error(e.message); return []; });
  for (const l of logs) {
    const end = Number(BigInt("0x" + l.data.slice(2 + 64, 2 + 128)));
    const lb = await rpc(L, "eth_getBlockByNumber", [l.blockNumber, false]);
    const pb = await rpc(P, "eth_getBlockByNumber", ["0x" + end.toString(16), false]);
    out.push({ l1_block: parseInt(l.blockNumber), polygon_end: end, latency_s: parseInt(lb.timestamp) - parseInt(pb.timestamp) });
  }
}
out.sort((a, b) => a.latency_s - b.latency_s);
console.log(JSON.stringify({ n: out.length, min: out[0], median: out[Math.floor(out.length / 2)], max: out[out.length - 1] }, null, 1));
