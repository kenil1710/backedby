"use client";

import Link from "next/link";
import { use } from "react";
import useSWR from "swr";
import { getBond, getCheck, getConfig, getPair, registry } from "@/lib/contract";
import { CHAIN_NAME, KIND_NAME, symbolOf } from "@/lib/chains";
import { absoluteTime, chainUrl, formatGen, relativeTime, shortAddress } from "@/lib/format";
import type { Check } from "@/lib/types";
import { standing } from "@/components/Board";
import { Readings } from "@/components/Readings";
import { Act } from "@/components/Act";
import { Ext, KV, Loading, Panel, Problem, Span, Verdict, ratioText } from "@/components/ui";

export default function PairPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const { data: p, error, mutate } = useSWR(["pair", id], () => getPair(id), { refreshInterval: 30_000 });
  const cfg = useSWR("config", () => getConfig()).data;
  const recent = p ? [...p.checks].reverse().slice(0, 12) : [];
  const { data: checks } = useSWR(p ? ["pair-checks", id, recent.join(",")] : null, () => Promise.all(recent.map((c) => getCheck(c))));
  const { data: bonds } = useSWR(p ? ["pair-bonds", id, p.bonds.join(",")] : null, () => Promise.all(p!.bonds.map((b) => getBond(b))));
  const { data: shown } = useSWR(p && (p.latest_check || p.open_check) ? ["shown", p.latest_check || p.open_check] : null,
    () => getCheck(p!.latest_check || p!.open_check));
  if (error && !p) return <div className="pt-10"><Problem error={error} /></div>;
  if (!p) return <Loading what="Reading the pair" />;
  if (p.found === false) return <p className="pt-10 text-ink-2">There is no pair {id} on this registry.</p>;
  const s = standing({ ...p, latest: shown && p.latest_check ? shown : null, open: shown && !p.latest_check ? shown : null });
  const destChains = [...new Set(p.dests.map((d) => d.chain))];
  return (
    <div className="pt-8">
      <Link href="/" className="text-[13px] text-ink-3 hover:text-ink-2">Board</Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="wide text-[28px] font-semibold tracking-tight sm:text-[34px]">{p.label || `Pair ${p.pair_id}`}</h1>
          <p className="mt-1 text-[14px] text-ink-2">
            {symbolOf(p.source_token)} locked on Ethereum by {p.vaults.map((v) => KIND_NAME[v.kind] ?? v.kind).join(" and ")}, minted on {destChains.map((c) => CHAIN_NAME[c] ?? c).join(", ")}.
            Pair <span className="num">{p.pair_id}</span>.
          </p>
        </div>
        <Verdict v={s.verdict} provisional={s.provisional} size="lg" />
      </div>
      <div className="mt-6 rounded-md border border-seam bg-plate px-4 py-4">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-[13px] text-ink-3">Locked divided by supply{s.at ? `, pinned ${relativeTime(s.at)}` : ""}</span>
          <span className={`num text-[22px] ${s.verdict === "UNDER_BACKED" ? "text-under" : ""}`}>{ratioText(s.ratio)}</span>
        </div>
        <div className="mt-3"><Span ratioBps={s.ratio} verdict={s.verdict} tall /></div>
        <div className="mt-1.5 flex justify-between text-[11.5px] text-ink-3 num"><span>0%</span><span style={{ marginLeft: "33%" }}>100%</span><span>150%</span></div>
      </div>

      {shown && <div className="mt-6"><Readings pair={p} check={shown} round={shown.ruling2 ? 2 : 1} /></div>}
      {!shown && <p className="mt-6 text-ink-2">Nothing has been read for this pair yet. File a monitoring check below.</p>}

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Check history" aside={`${p.checks.length} checks`}>
          {!checks && p.checks.length > 0 && <p className="text-ink-3 text-[14px]">Reading checks</p>}
          {checks && checks.length === 0 && <p className="text-ink-3 text-[14px]">No checks yet.</p>}
          <ul>
            {checks?.map((c) => <CheckRow key={c.check_id} c={c} />)}
          </ul>
        </Panel>
        <div className="space-y-4">
          <Panel title="Terms, frozen at registration">
            <dl>
              <KV k="Tolerance"><span className="num">{p.tolerance_bps} bps</span></KV>
              <KV k="Max gap"><span className="num">{p.max_gap_s} s</span></KV>
              {p.vaults.map((v) => (
                <KV key={v.vault} k="Vault"><Ext href={chainUrl("ethereum", "address", v.vault)}><span className="num">{shortAddress(v.vault, 6)}</span></Ext>{" "}
                  <span className="text-[12.5px] text-ink-3">{KIND_NAME[v.kind] ?? v.kind} · auth {v.auth_id}</span></KV>
              ))}
              <KV k="Source token"><Ext href={chainUrl("ethereum", "address", p.source_token)}>{symbolOf(p.source_token)}</Ext> <span className="num text-ink-3">{p.source_decimals} dec</span></KV>
              {p.dests.map((d) => (
                <KV key={d.token} k={`On ${CHAIN_NAME[d.chain] ?? d.chain}`}>
                  <Ext href={chainUrl(d.chain, "address", d.token)}><span className="num">{shortAddress(d.token, 6)}</span></Ext>{" "}
                  <span className="num text-ink-3">{d.decimals} dec · auth {d.auth_id}</span>
                </KV>
              ))}
              <KV k="Registered"><span className="num">{absoluteTime(p.registered_at)}</span></KV>
            </dl>
          </Panel>
          <Panel title="Bonds" aside={<Link className="text-steel" href={`/bond?pair=${p.pair_id}`}>Bond this pair</Link>}>
            {(!bonds || bonds.length === 0) && <p className="text-[14px] text-ink-3">No operator has bonded this pair.</p>}
            <ul className="text-[14px]">
              {bonds?.map((b) => (
                <li key={b.bond_id} className="flex flex-wrap justify-between gap-2 border-b border-seam/60 py-2 last:border-0">
                  <span>Bond <span className="num">{b.bond_id}</span> by <span className="num">{shortAddress(b.operator)}</span></span>
                  <span className="num">{formatGen(b.amount, 3)} GEN · {b.status.toLowerCase()}</span>
                  {b.status !== "WITHDRAWN" && b.status !== "SLASHED" && <Link className="text-steel" href={`/challenge?bond=${b.bond_id}`}>Challenge</Link>}
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Monitoring check">
            <p className="mb-3 text-[13.5px] text-ink-2">
              No stake. Pins fresh finalized blocks on Ethereum and {destChains.map((c) => CHAIN_NAME[c]).join(", ")} and opens a check
              {cfg ? `; at most one ruled check per ${cfg.monitor_interval_s >= 3600 ? cfg.monitor_interval_s / 3600 + " h" : cfg.monitor_interval_s + " s"}` : ""}.
            </p>
            <Act label="File a monitoring check" address={registry()} fn="monitor" disabled={p.open_check > 0}
              note={p.open_check > 0 ? `Check ${p.open_check} is open on this pair.` : undefined}
              args={async () => {
                const r = await fetch(`/api/pins?chains=${destChains.join(",")}`).then((x) => x.json());
                if (r.error) throw new Error("Could not pin blocks: " + r.error);
                return [p.pair_id, JSON.stringify(r.blocks)];
              }}
              onDone={() => void mutate()} />
          </Panel>
        </div>
      </div>
    </div>
  );
}

function CheckRow({ c }: { c: Check }) {
  const v = c.verdict || c.verdict1;
  return (
    <li className="border-b border-seam/60 last:border-0">
      <Link href={`/check/${c.check_id}`} className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-3 py-2.5 text-[14px] hover:bg-plate-2">
        <span className="num text-ink-3">#{c.check_id}</span>
        <span className="min-w-0">
          <span className="block truncate">{c.purpose === "CHALLENGE" ? `Challenge of bond ${c.bond_id}` : "Monitoring"} · {c.status.toLowerCase()}</span>
          <span className="num block text-[12.5px] text-ink-3">{c.source_time ? `pinned ${absoluteTime(c.source_time)}` : `filed ${absoluteTime(c.filed_at)}`}{c.ruling1 && c.ruling1.ratio_bps >= 0 ? ` · ${ratioText(c.ruling1.ratio_bps)}` : ""}</span>
        </span>
        {v ? <Verdict v={v} provisional={c.status === "PROVISIONAL" || c.status === "CONTESTED"} /> : <span className="text-[12.5px] text-ink-3">open</span>}
      </Link>
    </li>
  );
}
