// Server-side: pick pinned blocks for a pair the way tools/lib/pin.mjs does,
// so the Challenge and Monitor forms can prefill them. The contract re-checks
// every rule; these are only a starting point.
export const RPCS: Record<string, string[]> = {
  ethereum: ["https://eth-pokt.nodies.app", "https://rpc.mevblocker.io"],
  arbitrum: ["https://arb-pokt.nodies.app", "https://arbitrum.gateway.tenderly.co"],
  optimism: ["https://mainnet.optimism.io", "https://optimism.drpc.org"],
  base: ["https://base-pokt.nodies.app", "https://base.drpc.org"],
  polygon: ["https://polygon.drpc.org", "https://rpc-mainnet.matic.quiknode.pro"],
  moonbeam: ["https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public"],
  mantle: ["https://rpc.mantle.xyz", "https://mantle.drpc.org"],
  xlayer: ["https://xlayerrpc.okx.com", "https://xlayer.drpc.org"],
  sei: ["https://evm-rpc.sei-apis.com", "https://sei.api.pocket.network"],
  flare: ["https://flare-api.flare.network/ext/C/rpc", "https://rpc.ankr.com/flare"],
  hedera: ["https://mainnet.hashio.io/api", "https://hedera.linkpool.pro"],
  unichain: ["https://mainnet.unichain.org", "https://unichain.drpc.org"],
  morph: ["https://rpc.morphl2.io", "https://rpc-quicknode.morphl2.io"],
  ink: ["https://rpc-gel.inkonchain.com", "https://ink.drpc.org"],
  berachain: ["https://rpc.berachain.com", "https://berachain.drpc.org"],
  hyperevm: ["https://rpc.hyperliquid.xyz/evm", "https://hyperliquid.drpc.org"],
  monad: ["https://rpc.monad.xyz", "https://monad-mainnet-rpc.spidernode.net"],
};

type Blk = { number: number; timestamp: number };

async function rpc(url: string, method: string, params: unknown[]): Promise<unknown> {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }), signal: AbortSignal.timeout(12_000), cache: "no-store" });
  const j = await r.json();
  if (j.error) throw new Error(j.error.message);
  return j.result;
}

async function blk(chain: string, tag: number | string): Promise<Blk> {
  let last: unknown;
  for (const u of RPCS[chain]) {
    try {
      const b = (await rpc(u, "eth_getBlockByNumber", [typeof tag === "number" ? "0x" + tag.toString(16) : tag, false])) as { number: string; timestamp: string };
      if (b) return { number: parseInt(b.number, 16), timestamp: parseInt(b.timestamp, 16) };
    } catch (e) { last = e; }
  }
  throw last ?? new Error("no block");
}

async function finalized(chain: string): Promise<Blk> {
  const out: Blk[] = [];
  for (const u of RPCS[chain]) {
    const b = (await rpc(u, "eth_getBlockByNumber", ["finalized", false])) as { number: string; timestamp: string };
    out.push({ number: parseInt(b.number, 16), timestamp: parseInt(b.timestamp, 16) });
  }
  return out[0].number <= out[1].number ? out[0] : out[1];
}

async function search(chain: string, hi: Blk, t: number, mode: "first_ge" | "last_le"): Promise<Blk> {
  let H = hi.number, L = Math.max(0, H - 1), step = 64;
  for (;;) {
    const b = await blk(chain, L);
    if (b.timestamp < t || L === 0) break;
    H = L; L = Math.max(0, L - step); step *= 2;
  }
  while (H - L > 1) {
    const m = Math.floor((L + H) / 2);
    const b = await blk(chain, m);
    if (b.timestamp >= t) H = m; else L = m;
  }
  if (mode === "first_ge") return blk(chain, H);
  const h = await blk(chain, H);
  return h.timestamp <= t ? h : blk(chain, L);
}

export async function pinBlocks(dests: string[], margin = 90) {
  const chains = [...new Set(dests)];
  const fins: Record<string, Blk> = { ethereum: await finalized("ethereum") };
  for (const d of chains) fins[d] = await finalized(d);
  const T = Math.min(...Object.values(fins).map((b) => b.timestamp)) - margin;
  const src = await search("ethereum", fins.ethereum, T, "first_ge");
  const blocks: Record<string, Blk> = { ethereum: src };
  for (const d of chains) blocks[d] = await search(d, fins[d], src.timestamp, "last_le");
  const gap = src.timestamp - Math.min(...chains.map((d) => blocks[d].timestamp));
  return { blocks, gap };
}
