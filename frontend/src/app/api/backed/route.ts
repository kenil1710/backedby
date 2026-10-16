/**
 * GET /api/backed?pair=<id>[&registry=demo][&format=svg]
 * The pair's standing read from chain: the registry's latest ruling and the
 * CollateralGate's answer. JSON by default, an SVG badge with format=svg.
 */
import { createClient } from "genlayer-js";
import { studioDevnet } from "genlayer-js/chains";
import { ADDR } from "@/lib/deployments";

export const dynamic = "force-dynamic";
const client = createClient({ chain: studioDevnet });

function plain(v: unknown): unknown {
  if (v instanceof Map) return Object.fromEntries([...v.entries()].map(([k, x]) => [String(k), plain(x)]));
  if (Array.isArray(v)) return v.map(plain);
  if (typeof v === "bigint") return Number(v) <= Number.MAX_SAFE_INTEGER ? Number(v) : v.toString();
  return v;
}
async function view(address: string, fn: string, args: unknown[]) {
  let last: unknown;
  for (let i = 0; i < 3; i++) {
    try {
      const r = await client.readContract({ address: address as `0x${string}`, functionName: fn, args: args as never });
      return typeof r === "string" ? JSON.parse(r) : plain(r);
    } catch (e) { last = e; await new Promise((res) => setTimeout(res, 800 * (i + 1))); }
  }
  throw last;
}

const COLOR: Record<string, string> = { BACKED: "#4cc38a", UNDER_BACKED: "#ef5b52", INCONCLUSIVE: "#e9ad3c" };
function esc(s: string) { return s.replace(/[<>&"]/g, ""); }
function badge(label: string, value: string, color: string) {
  const lw = 8 + label.length * 6.6, vw = 10 + value.length * 6.8, w = lw + vw;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w.toFixed(0)}" height="20" role="img" aria-label="${esc(label)}: ${esc(value)}">
<rect width="${w.toFixed(0)}" height="20" rx="3" fill="#22262c"/><rect x="${lw.toFixed(0)}" width="${vw.toFixed(0)}" height="20" rx="3" fill="${color}"/>
<rect x="${lw.toFixed(0)}" width="4" height="20" fill="${color}"/>
<g font-family="Verdana,DejaVu Sans,sans-serif" font-size="11"><text x="6" y="14" fill="#e3e7ec">${esc(label)}</text>
<text x="${(lw + 5).toFixed(0)}" y="14" fill="#1b1e23" font-weight="bold">${esc(value)}</text></g></svg>`;
}

export async function GET(req: Request) {
  const u = new URL(req.url);
  const pair = Number(u.searchParams.get("pair"));
  const demo = u.searchParams.get("registry") === "demo";
  if (!Number.isInteger(pair) || pair <= 0) return Response.json({ error: "pair must be a positive integer" }, { status: 400 });
  const reg = demo ? ADDR.registryDemo : ADDR.registry;
  const gate = demo ? ADDR.gateDemo : ADDR.gate;
  try {
    const now = Math.floor(Date.now() / 1000);
    const [p, latest, g] = await Promise.all([view(reg, "get_pair", [pair]), view(reg, "get_latest", [pair]), view(gate, "is_backed", [pair, now])]);
    if (!p.found) return Response.json({ error: "no such pair" }, { status: 404 });
    const body = {
      pair, registry: reg, label: p.label, kind: p.kind, vault: p.vault, source_token: p.source_token, destinations: p.dests,
      tolerance_bps: p.tolerance_bps, latest: latest.found ? { check_id: latest.check_id, verdict: latest.verdict, status: latest.status, ratio_bps: latest.ratio_bps, pinned_source_time: latest.source_time, final_at: latest.final_at, reason: latest.reason } : null,
      gate: { contract: gate, backed: g.backed, reason: g.reason, max_age_s: g.max_age_s }, read_at: now,
      page: `${u.origin}/pair/${pair}`,
    };
    if (u.searchParams.get("format") === "svg") {
      const v = latest.found ? latest.verdict : "NOT CHECKED";
      const text = latest.found && latest.ratio_bps >= 0 ? `${v.replace("_", "-").toLowerCase()} ${(latest.ratio_bps / 100).toFixed(1)}%` : v.toLowerCase();
      return new Response(badge(`backedby ${p.label}`.slice(0, 40), text, COLOR[v] ?? "#6f7883"),
        { headers: { "content-type": "image/svg+xml", "cache-control": "public, s-maxage=120" } });
    }
    return Response.json(body, { headers: { "cache-control": "public, s-maxage=60" } });
  } catch (e) {
    return Response.json({ error: String((e as Error).message).slice(0, 200) }, { status: 502 });
  }
}
