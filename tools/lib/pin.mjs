// Picks one finalized block per chain so that the source (locked) block is
// at or after every destination block and the gap is as small as possible:
//   T      = the oldest finalized head among all chains involved
//   source = the first source block with timestamp >= T
//   dest_d = the last block on d with timestamp <= source.timestamp
// The contract re-checks every one of these conditions; this only finds them.
import { rpc } from "./evm.mjs";
import { CHAINS } from "./bridges.mjs";

const hx = (n) => "0x" + n.toString(16);
async function blk(chain, tag) {
  let last;
  for (const u of CHAINS[chain].rpcs) {
    for (let i = 0; i < 3; i++) {
      try {
        const b = await rpc(u, "eth_getBlockByNumber", [typeof tag === "number" ? hx(tag) : tag, false]);
        if (b) return { number: parseInt(b.number), timestamp: parseInt(b.timestamp), hash: b.hash };
      } catch (e) { last = e; await new Promise((r) => setTimeout(r, 1000 * (i + 1))); }
    }
  }
  throw last ?? new Error("no block");
}

/** The finalized head as the LOWER of the two RPCs' views. */
export async function finalized(chain) {
  const out = [];
  for (const u of CHAINS[chain].rpcs) {
    const b = await rpc(u, "eth_getBlockByNumber", ["finalized", false]);
    out.push({ number: parseInt(b.number), timestamp: parseInt(b.timestamp), hash: b.hash });
  }
  return out[0].number <= out[1].number ? out[0] : out[1];
}

/** first block (<= hi) with timestamp >= t, or last block with timestamp <= t. */
async function search(chain, hi, t, mode) {
  let H = hi.number, L = Math.max(0, H - 1);
  // widen downwards until L's timestamp is < t
  let step = 64;
  for (;;) {
    const b = await blk(chain, L);
    if (b.timestamp < t || L === 0) break;
    H = L; L = Math.max(0, L - step); step *= 2;
  }
  // invariant: ts(L) < t (or L==0), ts(H) >= t or H==hi
  while (H - L > 1) {
    const m = Math.floor((L + H) / 2);
    const b = await blk(chain, m);
    if (b.timestamp >= t) H = m; else L = m;
  }
  if (mode === "first_ge") return blk(chain, H);
  // last block with ts <= t
  const h = await blk(chain, H);
  return h.timestamp <= t ? h : blk(chain, L);
}

export async function pinBlocks(source, dests, { margin = 0 } = {}) {
  const chains = [...new Set(dests)];
  const fins = { [source]: await finalized(source) };
  for (const d of chains) fins[d] = await finalized(d);
  let T = Math.min(...Object.values(fins).map((b) => b.timestamp)) - margin;
  const src = await search(source, fins[source], T, "first_ge");
  const out = { [source]: src };
  for (const d of chains) {
    out[d] = fins[d].timestamp <= src.timestamp && margin === 0 ? fins[d] : await search(d, fins[d], src.timestamp, "last_le");
  }
  const gap = src.timestamp - Math.min(...chains.map((d) => out[d].timestamp));
  return { blocks: out, gap, fins };
}
