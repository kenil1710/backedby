/** GET /api/pins?chains=arbitrum[,optimism] -> blocks that satisfy the pin rules right now. */
import { pinBlocks, RPCS } from "@/lib/pins";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const chains = (new URL(req.url).searchParams.get("chains") ?? "").split(",").filter(Boolean);
  if (chains.length < 1 || chains.length > 4 || chains.some((c) => !RPCS[c] || c === "ethereum")) {
    return Response.json({ error: "chains must name 1-4 destination chains" }, { status: 400 });
  }
  try {
    const p = await pinBlocks(chains);
    return Response.json({ blocks: Object.fromEntries(Object.entries(p.blocks).map(([k, v]) => [k, v.number])), detail: p.blocks, gap_s: p.gap },
      { headers: { "cache-control": "public, s-maxage=30" } });
  } catch (e) {
    return Response.json({ error: String((e as Error).message).slice(0, 200) }, { status: 502 });
  }
}
