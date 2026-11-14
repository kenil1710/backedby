"use client";

import { useState } from "react";
import useSWR from "swr";
import { getAllHistory } from "@/lib/contract";
import { chainUrl, absoluteTime, shortAddress } from "@/lib/format";
import { FAMILY_TEXT, remoteName } from "@/lib/remote";
import type { Check, HistoryPoint, Pair } from "@/lib/types";
import SURPLUS from "@/lib/surplus.json";
import { Ext, Panel, ratioText } from "./ui";

const COV_TONE: Record<string, string> = { COMPLETE: "text-backed", GAP: "text-under", UNREAD: "text-inconc", OPEN: "text-inconc" };
const COV_TEXT: Record<string, string> = {
  COMPLETE: "every destination the vaults' bridges name is listed",
  GAP: "a vault backs destinations this pair does not list",
  UNREAD: "a coverage scan could not be read at the pinned block",
  OPEN: "a vault's bridge cannot be enumerated on chain",
};

export function Badge({ text, tone }: { text: string; tone: string }) {
  return <span className={`rounded border border-seam px-1.5 py-0.5 text-[11.5px] ${tone}`}>{text}</span>;
}

/** Which destinations each vault's own bridge config says it backs, and which of them the pair lists. */
export function CoveragePanel({ pair, check, unmatched }: { pair: Pair; check: Check | null | undefined; unmatched?: Record<string, { why: string }> }) {
  const cov = check?.ruling1?.coverage;
  return (
    <Panel title="Coverage: does the pair list everything its vaults back?" aside={cov ? <span className={COV_TONE[cov.state]}>{cov.state.toLowerCase()}</span> : "not ruled yet"}>
      {!cov && <p className="text-[14px] text-ink-3">Coverage is recorded with each ruling.</p>}
      {cov && (
        <>
          <p className="text-[13.5px] text-ink-2">{COV_TEXT[cov.state]} (check <span className="num">{check?.check_id}</span>, at its pinned Ethereum block).</p>
          <ul className="mt-2">
            {cov.by_vault.map((v) => {
              const vault = pair.vaults.find((x) => x.vault === v.vault);
              return (
                <li key={v.vault} className="border-b border-seam/60 py-2 text-[13.5px] last:border-0">
                  <div className="flex flex-wrap justify-between gap-2">
                    <Ext href={chainUrl("ethereum", "address", v.vault)}><span className="num">{shortAddress(v.vault, 6)}</span></Ext>
                    <span className={COV_TONE[v.state]}>{v.state.toLowerCase()}</span>
                  </div>
                  <div className="text-[12.5px] text-ink-3">{FAMILY_TEXT[v.family] ?? v.family}; listed: {(vault?.remotes ?? []).map(remoteName).join(", ") || "-"}</div>
                  {v.unlisted.length > 0 && (
                    <div className="mt-1 text-[12.5px] text-under">Not listed: {v.unlisted.map((id) => {
                      const why = unmatched?.[id]?.why;
                      return `${remoteName(id)}${why ? ` (keeper: ${why})` : ""}`;
                    }).join("; ")}</div>
                  )}
                </li>
              );
            })}
          </ul>
          {cov.state === "GAP" && <p className="mt-2 text-[12.5px] text-ink-3">The keeper adds every unlisted destination the bridge&apos;s config proves on a chain BackedBy reads from two RPCs; the rest stay listed here. Until the list is complete the ratio leaves that supply out, and CollateralGate refuses the pair.</p>}
        </>
      )}
    </Panel>
  );
}

const POR_TEXT: Record<string, string> = {
  BOTH_LAYERS_WITHIN_50BPS: "Both layers agree within 0.5%.",
  BRIDGE_VAULT_SURPLUS_EXCEEDS_CUSTODY_SURPLUS: "The bridge vault holds more against its bridged supply than the custodian holds against the token's whole supply. PoR measures custody (reserves / the token's supply on Ethereum); BackedBy measures the bridge (vault / the supply minted against it). The bridge's surplus is explained below.",
  BRIDGE_VAULT_BELOW_CUSTODY_RATIO: "The bridge vault covers its bridged supply by less than the custodian covers the token's supply: the bridge layer is the weaker one.",
  NO_BRIDGE_RATIO: "No bridge ratio to compare.",
};

/** Chainlink Proof of Reserve read at the same pinned Ethereum block, next to BackedBy's ratio. */
export function PorPanel({ check }: { check: Check | null | undefined }) {
  const por = check?.ruling1?.por;
  if (!por) return null;
  const parts = por.explain.split(";");
  return (
    <Panel title="Chainlink Proof of Reserve" aside={<span className={por.status === "MATCH" ? "text-backed" : por.status === "DIFF" ? "text-inconc" : "text-ink-3"}>{por.status}</span>}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13.5px]">
        <dt className="text-ink-3">BackedBy (bridge vault / bridged supply)</dt><dd className="num text-right">{ratioText(check?.ruling1?.ratio_bps ?? -1)}</dd>
        <dt className="text-ink-3">PoR (reserves / token supply)</dt><dd className="num text-right">{ratioText(por.por_ratio_bps)}</dd>
        <dt className="text-ink-3">Delta</dt><dd className="num text-right">{por.delta_bps >= 0 ? "+" : ""}{(por.delta_bps / 100).toFixed(2)} pts</dd>
        {por.age_s !== undefined && <><dt className="text-ink-3">Feed answer age at the pinned block</dt><dd className="num text-right">{(por.age_s / 3600).toFixed(1)} h</dd></>}
      </dl>
      {por.feed && <p className="mt-2 text-[12.5px] text-ink-3">Feed <Ext href={chainUrl("ethereum", "address", por.feed)}><span className="num">{shortAddress(por.feed, 6)}</span></Ext>, read with latestRoundData() from both Ethereum RPCs at the check&apos;s block.</p>}
      {por.status !== "MATCH" && <div className="mt-2 space-y-1 text-[13px] text-ink-2">{parts.map((p) => <p key={p}>{POR_TEXT[p] ?? p.replaceAll("_", " ").toLowerCase()}</p>)}</div>}
    </Panel>
  );
}

type SurplusRow = { pair_id: number; registry: string; check_id: number; surplus_norm: string; scale_decimals: number; symbol: string;
  components: { name: string; amount: string; source: string; links?: string[] }[]; residual: string; note?: string };

/** For a pair above 100%: where the vault's surplus comes from, each part read from chain. */
export function SurplusPanel({ pair, registry }: { pair: Pair; registry: string }) {
  const rows = (SURPLUS as { pairs?: SurplusRow[] }).pairs ?? [];
  const r = rows.find((x) => x.pair_id === pair.pair_id && x.registry.toLowerCase() === registry.toLowerCase());
  if (!r) return null;
  const n = (v: string) => (Number(BigInt(v) / 10n ** BigInt(Math.max(r.scale_decimals - 2, 0))) / 100).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return (
    <Panel title="Where the surplus comes from" aside={`check ${r.check_id}`}>
      <p className="text-[13.5px] text-ink-2">The vault holds <span className="num">{n(r.surplus_norm)} {r.symbol}</span> more than the counted supply. Read from chain:</p>
      <ul className="mt-2">
        {r.components.map((c) => (
          <li key={c.name} className="border-b border-seam/60 py-2 text-[13.5px] last:border-0">
            <div className="flex justify-between gap-2"><span>{c.name}</span><span className="num">{n(c.amount)}</span></div>
            <div className="text-[12.5px] text-ink-3">{c.source}{c.links?.length ? " · " : ""}{c.links?.slice(0, 3).map((l, i) => <Ext key={l} href={l}>{i ? ", " : ""}source {i + 1}</Ext>)}</div>
          </li>
        ))}
        <li className="flex justify-between py-2 text-[13.5px]"><span className="text-ink-3">Not attributed</span><span className="num">{n(r.residual)}</span></li>
      </ul>
      {r.note && <p className="mt-1 text-[12.5px] text-ink-3">{r.note}</p>}
    </Panel>
  );
}

/** The pair's FINAL rulings over time: the ratio, the tolerance line and the alert band. */
export function HistoryChart({ pair, alertMargin = 10 }: { pair: Pair; alertMargin?: number }) {
  const { data, error } = useSWR(["history", pair.pair_id, pair.history_points ?? 0], () => getAllHistory(pair.pair_id), { refreshInterval: 120_000 });
  const [hover, setHover] = useState<HistoryPoint | null>(null);
  const [table, setTable] = useState(false);
  const pts = (data?.points ?? []).filter((p) => p.ratio_bps >= 0).sort((a, b) => a.source_time - b.source_time);
  const line = 10000 - pair.tolerance_bps;
  const W = 640, H = 180, L = 52, R = 12, T = 12, B = 26;
  let lo = Math.min(line - 50, ...pts.map((p) => p.ratio_bps)), hi = Math.max(line + alertMargin + 50, ...pts.map((p) => p.ratio_bps));
  if (hi - lo < 100) { lo -= 50; hi += 50; }
  const t0 = pts[0]?.source_time ?? 0, t1 = pts.at(-1)?.source_time ?? 1;
  const x = (t: number) => L + (t1 === t0 ? (W - L - R) / 2 : ((t - t0) / (t1 - t0)) * (W - L - R));
  const y = (r: number) => T + (1 - (r - lo) / (hi - lo)) * (H - T - B);
  const ticks = [lo, line, hi].map((v) => Math.round(v));
  return (
    <Panel title="Backing over time" aside={<button className="text-steel" onClick={() => setTable(!table)}>{table ? "Chart" : "Table"}</button>}>
      {error && !data && <p className="text-[14px] text-under">Could not read the history.</p>}
      {!data && !error && <p className="text-[14px] text-ink-3">Reading the history</p>}
      {data && pts.length === 0 && <p className="text-[14px] text-ink-3">No final ruling yet. Every FINAL ruling becomes a point here.</p>}
      {data && pts.length > 0 && !table && (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`backing ratio over ${pts.length} final rulings`}
            onMouseLeave={() => setHover(null)}>
            {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--color-seam)" strokeWidth={1} />
              <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--color-ink-3)" className="num">{(v / 100).toFixed(2)}%</text></g>)}
            <rect x={L} width={W - L - R} y={y(line + alertMargin)} height={Math.max(y(line) - y(line + alertMargin), 1)} fill="var(--color-inconc)" opacity={0.15} />
            <line x1={L} x2={W - R} y1={y(line)} y2={y(line)} stroke="var(--color-under)" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={W - R} y={y(line) - 4} textAnchor="end" fontSize={11} fill="var(--color-ink-2)">tolerance line {(line / 100).toFixed(2)}%</text>
            {pts.length > 1 && <polyline fill="none" stroke="var(--color-steel)" strokeWidth={2} points={pts.map((p) => `${x(p.source_time)},${y(p.ratio_bps)}`).join(" ")} />}
            {pts.map((p) => (
              <g key={p.check_id} onMouseEnter={() => setHover(p)}>
                <circle cx={x(p.source_time)} cy={y(p.ratio_bps)} r={12} fill="transparent" />
                <circle cx={x(p.source_time)} cy={y(p.ratio_bps)} r={4} stroke="var(--color-plate)" strokeWidth={2}
                  fill={p.verdict === "UNDER_BACKED" ? "var(--color-under)" : p.alert === "ALERT" ? "var(--color-inconc)" : "var(--color-backed)"} />
              </g>
            ))}
            <text x={L} y={H - 6} fontSize={11} fill="var(--color-ink-3)">{absoluteTime(t0)}</text>
            <text x={W - R} y={H - 6} textAnchor="end" fontSize={11} fill="var(--color-ink-3)">{absoluteTime(t1)}</text>
          </svg>
          {hover && (
            <div className="pointer-events-none absolute right-2 top-2 rounded border border-seam bg-ground px-3 py-2 text-[12.5px]">
              <div className="num">check {hover.check_id} · {ratioText(hover.ratio_bps)}</div>
              <div className="text-ink-3">{hover.verdict.toLowerCase().replace("_", "-")}{hover.alert === "ALERT" ? ", alert" : ""} · coverage {hover.coverage.toLowerCase()}{hover.por ? ` · PoR ${hover.por}` : ""}</div>
              <div className="num text-ink-3">pinned {absoluteTime(hover.source_time)}</div>
            </div>
          )}
          <p className="mt-1 text-[12px] text-ink-3">Shaded: within {alertMargin} bps of the tolerance line (ALERT). Points: green backed, amber alert, red under-backed.</p>
        </div>
      )}
      {data && pts.length > 0 && table && (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-left text-ink-3"><th className="font-normal">Check</th><th className="font-normal">Pinned</th><th className="text-right font-normal">Ratio</th><th className="font-normal pl-3">Ruling</th><th className="font-normal">Coverage</th></tr></thead>
            <tbody>{[...pts].reverse().map((p) => (
              <tr key={p.check_id} className="border-t border-seam/60"><td className="num py-1">{p.check_id}</td><td className="num">{absoluteTime(p.source_time)}</td>
                <td className="num text-right">{ratioText(p.ratio_bps)}</td><td className="pl-3">{p.verdict.toLowerCase()}{p.alert === "ALERT" ? ", alert" : ""}</td><td>{p.coverage.toLowerCase()}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {data?.truncated && <p className="mt-1 text-[12px] text-ink-3">Showing the first 1,000 points.</p>}
    </Panel>
  );
}
