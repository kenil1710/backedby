"use client";

import Link from "next/link";
import useSWR from "swr";
import { getPairs, getConfig } from "@/lib/contract";
import { CHAIN_NAME, KIND_NAME, symbolOf } from "@/lib/chains";
import { relativeTime } from "@/lib/format";
import type { Pair } from "@/lib/types";
import { Loading, Problem, Span, Verdict, ratioText } from "./ui";

/** What the board shows for a pair: its latest ruling, or the open check's provisional one. */
export function standing(p: Pair) {
  const l = p.latest;
  const o = p.open;
  const prov = o && o.status === "PROVISIONAL" ? o : null;
  const shown = l ?? prov ?? null;
  return {
    verdict: shown ? (shown.verdict || shown.verdict1) : undefined,
    ratio: shown?.ruling1?.ratio_bps ?? null,
    at: shown?.source_time ?? 0,
    provisional: !l && Boolean(prov),
    check: shown?.check_id ?? 0,
  };
}

const ORDER: Record<string, number> = { UNDER_BACKED: 0, INCONCLUSIVE: 1, BACKED: 2 };

export function Board() {
  const { data, error } = useSWR("pairs", () => getPairs(), { refreshInterval: 30_000 });
  const cfg = useSWR("config", () => getConfig()).data;
  if (error && !data) return <Problem error={error} />;
  if (!data) return <Loading what="Reading every pair" />;
  const rows = [...data.pairs].sort((a, b) => {
    const x = standing(a), y = standing(b);
    return (ORDER[x.verdict ?? ""] ?? 3) - (ORDER[y.verdict ?? ""] ?? 3) || a.pair_id - b.pair_id;
  });
  const n = (v: string) => data.pairs.filter((p) => standing(p).verdict === v && !standing(p).provisional).length;
  if (rows.length === 0) return <p className="py-10 text-ink-2">No pairs registered on this registry yet.</p>;
  return (
    <div>
      <p className="mb-3 text-[14px] text-ink-2">
        <span className="num text-ink">{data.total}</span> pairs ·{" "}
        <span className="num text-backed">{n("BACKED")}</span> backed ·{" "}
        <span className="num text-under">{n("UNDER_BACKED")}</span> under-backed ·{" "}
        <span className="num text-inconc">{n("INCONCLUSIVE")}</span> inconclusive
        {cfg && <span className="text-ink-3"> · rulings final after a {cfg.window_s >= 3600 ? `${cfg.window_s / 3600} h` : `${cfg.window_s} s`} contest window</span>}
      </p>
      <div className="overflow-hidden rounded-md border border-seam">
        <div className="hidden grid-cols-[minmax(0,2.3fr)_minmax(0,2.2fr)_6.5rem_7rem_9.5rem] gap-4 border-b border-seam bg-plate px-4 py-2 text-[12.5px] text-ink-3 md:grid">
          <span>Pair</span><span>Locked against supply, 0 to 150%</span><span className="text-right">Ratio</span><span>Pinned</span><span>Ruling</span>
        </div>
        <ul>
          {rows.map((p) => {
            const s = standing(p);
            const d = p.dests[0];
            return (
              <li key={p.pair_id} className="border-b border-seam last:border-0">
                <Link href={`/pair/${p.pair_id}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-3.5 hover:bg-plate md:grid-cols-[minmax(0,2.2fr)_minmax(0,2fr)_6rem_7rem_12rem]">
                  <div className="min-w-0">
                    <div className="truncate text-[15px] font-medium">{p.label || `${symbolOf(p.source_token)} pair ${p.pair_id}`}</div>
                    <div className="truncate text-[12.5px] text-ink-3">
                      {symbolOf(p.source_token)} on Ethereum{p.vaults.length > 1 ? ` in ${p.vaults.length} vaults` : ""}, {p.dests.length > 1 ? `${p.dests.length} tokens on ${[...new Set(p.dests.map((x) => CHAIN_NAME[x.chain] ?? x.chain))].join(", ")}` : CHAIN_NAME[d?.chain] ?? d?.chain} · {p.vaults.map((v) => KIND_NAME[v.kind] ?? v.kind).join(" + ")}
                      {p.tolerance_bps > 0 ? ` · ${p.tolerance_bps} bps tolerance` : ""}
                    </div>
                  </div>
                  <div className="order-3 col-span-2 md:order-none md:col-span-1"><Span ratioBps={s.ratio} verdict={s.verdict} /></div>
                  <div className={`num text-right text-[15px] ${s.verdict === "UNDER_BACKED" ? "text-under" : "text-ink"}`}>{ratioText(s.ratio)}</div>
                  <div className="hidden text-[13px] text-ink-2 md:block">{s.at ? relativeTime(s.at) : "-"}</div>
                  <div className="hidden md:block"><Verdict v={s.verdict} provisional={s.provisional} /></div>
                  <div className="order-4 col-span-2 flex min-w-0 flex-wrap items-center justify-between gap-2 text-[12.5px] text-ink-3 md:hidden">
                    <Verdict v={s.verdict} provisional={s.provisional} /><span>{s.at ? `pinned ${relativeTime(s.at)}` : ""}</span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
