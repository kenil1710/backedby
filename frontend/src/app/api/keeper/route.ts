/**
 * GET /api/keeper - the keeper's status.json from the keeper-state branch,
 * where the scheduled workflow commits a checkpoint after every step. Cached
 * by the CDN for 60 s.
 */
export const dynamic = "force-dynamic";
const URL_ = "https://raw.githubusercontent.com/kenil1710/backedby/keeper-state/status.json";

export async function GET() {
  let last = "";
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(URL_, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
      if (r.status === 404) return Response.json({ error: "the keeper has not run yet" }, { status: 404, headers: { "cache-control": "public, s-maxage=60" } });
      if (!r.ok) throw new Error("http " + r.status);
      return Response.json(await r.json(), { headers: { "cache-control": "public, s-maxage=60, stale-while-revalidate=300" } });
    } catch (e) { last = String((e as Error).message); await new Promise((res) => setTimeout(res, 600 * 2 ** i)); }
  }
  return Response.json({ error: last.slice(0, 200) }, { status: 502, headers: { "cache-control": "no-store" } });
}
