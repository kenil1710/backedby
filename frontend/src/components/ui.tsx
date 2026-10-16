"use client";

import { useEffect, useState } from "react";

export const TONE: Record<string, { text: string; bg: string; fill: string; label: string }> = {
  BACKED: { text: "text-backed", bg: "bg-backed/12 border-backed/40", fill: "bg-backed", label: "Backed" },
  UNDER_BACKED: { text: "text-under", bg: "bg-under/12 border-under/45", fill: "bg-under", label: "Under-backed" },
  INCONCLUSIVE: { text: "text-inconc", bg: "bg-inconc/12 border-inconc/40", fill: "bg-inconc", label: "Inconclusive" },
  NONE: { text: "text-ink-3", bg: "bg-plate-2 border-seam", fill: "bg-ink-3", label: "Not checked" },
};

export function Verdict({ v, provisional = false, size = "sm" }: { v?: string; provisional?: boolean; size?: "sm" | "lg" }) {
  const t = TONE[v && TONE[v] ? v : "NONE"];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border ${t.bg} ${t.text} ${size === "lg" ? "px-3 py-1 text-[15px]" : "px-2 py-0.5 text-[12.5px]"} font-medium whitespace-nowrap`}>
      <span className={`size-1.5 rounded-full ${t.fill} ${provisional ? "live" : ""}`} />
      {t.label}{provisional ? ", provisional" : ""}
    </span>
  );
}

/**
 * The span. Two pylons (vault, destination) and a deck whose fill is the
 * backing ratio on a 0-150% scale; the white tick is 100%. Over-backing past
 * 150% is drawn to the end with a chevron.
 */
export function Span({ ratioBps, verdict, tall = false }: { ratioBps?: number | null; verdict?: string; tall?: boolean }) {
  const known = typeof ratioBps === "number" && ratioBps >= 0;
  const r = known ? Math.min(ratioBps! / 15000, 1) : 0;
  const t = TONE[verdict && TONE[verdict] ? verdict : "NONE"];
  return (
    <div className={`relative flex w-full items-center ${tall ? "h-7" : "h-4"}`} role="img"
      aria-label={known ? `backing ratio ${(ratioBps! / 100).toFixed(2)} percent` : "no ratio yet"}>
      <span className={`absolute left-0 w-[3px] rounded-sm bg-steel ${tall ? "h-7" : "h-4"}`} />
      <span className={`absolute right-0 w-[3px] rounded-sm bg-steel ${tall ? "h-7" : "h-4"}`} />
      <div className={`relative mx-[3px] w-full overflow-hidden rounded-[2px] bg-steel-deep/35 ${tall ? "h-3" : "h-2"} ${known ? "" : "hatch"}`}>
        {known && <div className={`deck-fill absolute inset-y-0 left-0 ${t.fill}`} style={{ width: `${r * 100}%` }} />}
      </div>
      <span className={`absolute w-[2px] bg-ink ${tall ? "h-5" : "h-3"}`} style={{ left: `calc(3px + (100% - 6px) * ${1 / 1.5})` }} aria-hidden="true" />
    </div>
  );
}

export function ratioText(bps?: number | null): string {
  if (typeof bps !== "number" || bps < 0) return bps === -1 ? "no supply" : "-";
  return `${(bps / 100).toFixed(2)}%`;
}

export function Ext({ href, children, className = "" }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer"
      className={`text-steel underline decoration-steel/30 underline-offset-2 hover:decoration-steel ${className}`}>{children}</a>
  );
}

export function Panel({ title, aside, children, className = "" }: { title?: React.ReactNode; aside?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-md border border-seam bg-plate ${className}`}>
      {title && (
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-seam px-4 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {aside && <div className="text-[13px] text-ink-3">{aside}</div>}
        </div>
      )}
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

export function KV({ k, children }: { k: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(7rem,38%)_1fr] gap-3 border-b border-seam/60 py-2 last:border-0 text-[14px]">
      <dt className="text-ink-3">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function Loading({ what = "Reading the contracts" }: { what?: string }) {
  return <p className="py-10 text-ink-3"><span className="live">{what}</span> on Studio Dev.</p>;
}

export function Problem({ error }: { error: unknown }) {
  return (
    <p className="rounded border border-under/40 bg-under/10 px-3 py-2 text-[14px] text-under">
      Could not read the contract: {String((error as Error)?.message ?? error).slice(0, 200)}. The page retries on its own.
    </p>
  );
}

/** Wall clock, ticking once a second, for countdowns. */
export function useNow(): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const t = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export function Btn({ children, onClick, disabled, kind = "primary", type = "button" }:
    { children: React.ReactNode; onClick?: () => void; disabled?: boolean; kind?: "primary" | "quiet" | "danger"; type?: "button" | "submit" }) {
  const cls = kind === "primary" ? "bg-steel text-ground hover:bg-ink" : kind === "danger" ? "bg-under/90 text-white hover:bg-under" : "border border-seam text-ink hover:bg-plate-2";
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`rounded px-3.5 py-2 text-[14px] font-medium disabled:cursor-not-allowed disabled:opacity-50 ${cls}`}>{children}</button>
  );
}
