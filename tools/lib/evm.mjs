// Minimal JSON-RPC helpers for off-chain scripts (feasibility, patrol, seeds).
export async function rpc(url, method, params = [], timeout = 20000) {
  const res = await fetch(url, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    signal: AbortSignal.timeout(timeout),
  });
  const txt = await res.text();
  let j;
  try { j = JSON.parse(txt); } catch { throw new Error(`http ${res.status} non-json: ${txt.slice(0, 80)}`); }
  if (j.error) { const e = new Error(`rpc error ${j.error.code}: ${j.error.message}`); e.rpc = j.error; throw e; }
  return j.result;
}
export const pad = (a) => a.toLowerCase().replace(/^0x/, "").padStart(64, "0");
export const sel = {
  balanceOf: "0x70a08231", totalSupply: "0x18160ddd", decimals: "0x313ce567",
};
export async function call(url, to, data, block = "latest") {
  return rpc(url, "eth_call", [{ to, data }, typeof block === "number" ? "0x" + block.toString(16) : block]);
}
export const word = (hex, i = 0) => BigInt("0x" + (hex.replace(/^0x/, "").slice(64 * i, 64 * (i + 1)) || "0"));
export const addrOf = (hex, i = 0) => "0x" + hex.replace(/^0x/, "").slice(64 * i + 24, 64 * (i + 1));
export async function block(url, tag) {
  return rpc(url, "eth_getBlockByNumber", [typeof tag === "number" ? "0x" + tag.toString(16) : tag, false]);
}
