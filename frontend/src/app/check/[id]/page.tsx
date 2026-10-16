"use client";

import Link from "next/link";
import { use } from "react";
import useSWR from "swr";
import { getCheck, getConfig, getPair, getReading, registry } from "@/lib/contract";
import { ADDR } from "@/lib/deployments";
import { absoluteTime, durationText, formatGen, shortAddress } from "@/lib/format";
import type { Check } from "@/lib/types";
import { Readings } from "@/components/Readings";
import { Act } from "@/components/Act";
import { Loading, Panel, Problem, Verdict, ratioText, useNow } from "@/components/ui";

type Step = { name: string; at?: number; body: React.ReactNode; state: "done" | "now" | "todo" | "skip" };

function steps(c: Check, now: number): Step[] {
  const inc = c.status === "INCONCLUSIVE";
  const ruled = c.ruled_at > 0 && !(inc && !c.verdict1);
  const filed: Step = { name: "Filed", at: c.filed_at, state: "done",
    body: <>{c.purpose === "CHALLENGE" ? <>Challenge of bond <span className="num">{c.bond_id}</span>, stake <span className="num">{formatGen(c.stake, 3)}</span> GEN</> : "Monitoring check, no stake"}, by <span className="num">{shortAddress(c.filer)}</span>. Read by <span className="num">{absoluteTime(c.read_deadline)}</span> or it expires.</> };
  const prov: Step = { name: "Provisional", at: ruled ? c.ruled_at : undefined,
    state: ruled ? "done" : c.status === "OPEN" ? "now" : "skip",
    body: ruled ? <>Code ruled <b>{c.verdict1.replace("_", "-").toLowerCase()}</b> at <span className="num">{ratioText(c.ruling1?.ratio_bps)}</span> ({c.ruling1?.reason}).</> :
      c.status === "OPEN" ? "Waiting for ChainReader to read the pinned blocks and for anyone to rule." : "No ruling: the check closed first." };
  const window = c.contest_deadline;
  const contestable: Step = { name: "Contestable", at: window || undefined,
    state: !ruled ? "skip" : c.status === "PROVISIONAL" && now < window ? "now" : "done",
    body: !ruled ? "Never opened." : c.contester ? <>Contested by <span className="num">{shortAddress(c.contester)}</span> with <span className="num">{formatGen(c.contest_stake, 3)}</span> GEN at <span className="num">{absoluteTime(c.contested_at)}</span>; the same blocks are read again{c.ruling2 ? <>, re-read ruled <b>{c.ruling2.verdict.toLowerCase()}</b></> : ""}.</> :
      now < window ? <>Anyone can contest for <span className="num">{durationText(window - now)}</span> more.</> : <>The window closed at <span className="num">{absoluteTime(window)}</span> with no contest.</> };
  const fin: Step = { name: inc ? "Inconclusive" : "Final", at: c.final_at || undefined,
    state: c.status === "FINAL" || inc ? "done" : "todo",
    body: c.status === "FINAL" ? <>Final <b>{c.verdict.replace("_", "-").toLowerCase()}</b> ({c.how.toLowerCase().replaceAll("_", " ")}).</> :
      inc ? <>Closed inconclusive: {c.reason} ({c.how.toLowerCase().replaceAll("_", " ")}). Every stake refunded.</> : "Not yet." };
  return [filed, prov, contestable, fin];
}

export default function CheckPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const now = useNow();
  const { data: c, error, mutate } = useSWR(["check", id], () => getCheck(id), { refreshInterval: 15_000 });
  const { data: p } = useSWR(c?.found ? ["pair", c.pair_id] : null, () => getPair(c!.pair_id));
  const cfg = useSWR("config", () => getConfig()).data;
  const rnd = c?.status === "CONTESTED" ? 2 : 1;
  const { data: rd, mutate: mrd } = useSWR(c?.found ? ["reading", id, rnd] : null, () => getReading(id, rnd), { refreshInterval: 15_000 });
  if (error && !c) return <div className="pt-10"><Problem error={error} /></div>;
  if (!c) return <Loading what="Reading the check" />;
  if (c.found === false) return <p className="pt-10 text-ink-2">There is no check {id} on this registry.</p>;
  const refresh = () => { void mutate(); void mrd(); };
  const st = steps(c, now);
  const v = c.verdict || c.verdict1;
  return (
    <div className="pt-8">
      {p && <Link href={`/pair/${p.pair_id}`} className="text-[13px] text-ink-3 hover:text-ink-2">{p.label || `Pair ${p.pair_id}`}</Link>}
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <h1 className="wide text-[28px] font-semibold tracking-tight sm:text-[34px]">Check <span className="num">{c.check_id}</span></h1>
        {v ? <Verdict v={v} provisional={c.status === "PROVISIONAL" || c.status === "CONTESTED"} size="lg" /> : <span className="text-ink-3">open</span>}
      </div>

      <ol className="mt-6 grid gap-0 sm:grid-cols-4">
        {st.map((s, i) => (
          <li key={s.name} className="relative border-l-2 pb-5 pl-4 sm:border-l-0 sm:border-t-2 sm:pb-0 sm:pl-0 sm:pr-4 sm:pt-4"
            style={{ borderColor: s.state === "done" ? "var(--color-steel)" : s.state === "now" ? "var(--color-inconc)" : "var(--color-seam)" }}>
            <span className={`absolute -left-[7px] top-0 size-3 rounded-full sm:-top-[7px] sm:left-0 ${s.state === "done" ? "bg-steel" : s.state === "now" ? "bg-inconc live" : "bg-seam"}`} />
            <div className="flex items-baseline gap-2">
              <span className="num text-[12px] text-ink-3">{i + 1}</span>
              <span className={`text-[15px] font-semibold ${s.state === "skip" ? "text-ink-3 line-through" : ""}`}>{s.name}</span>
            </div>
            {s.at ? <div className="num text-[12.5px] text-ink-3">{absoluteTime(s.at)}</div> : null}
            <p className="mt-1 text-[13.5px] leading-snug text-ink-2">{s.body}</p>
          </li>
        ))}
      </ol>

      <Panel title="What anyone can do now" className="mt-6">
        <Actions c={c} now={now} hasReading={Boolean(rd?.found)} rnd={rnd} minStake={cfg ? BigInt(cfg.min_stake) : null} onDone={refresh} />
      </Panel>

      {c.payouts && (
        <Panel title="Money" className="mt-4">
          <ul className="grid gap-x-6 gap-y-1 text-[14px] sm:grid-cols-3">
            {Object.entries(c.payouts).filter(([, x]) => x !== "0").map(([k, x]) => (
              <li key={k} className="flex justify-between gap-3"><span className="text-ink-3">{k.replaceAll("_", " ")}</span><span className="num">{formatGen(x, 4)} GEN</span></li>
            ))}
            {Object.values(c.payouts).every((x) => x === "0") && <li className="text-ink-3">No GEN moved.</li>}
          </ul>
        </Panel>
      )}

      {p && <div className="mt-6"><Readings pair={p} check={c} round={c.ruling2 ? 2 : 1} /></div>}
    </div>
  );
}

function Actions({ c, now, hasReading, rnd, minStake, onDone }: { c: Check; now: number; hasReading: boolean; rnd: number; minStake: bigint | null; onDone: () => void }) {
  const reg = registry();
  if (c.status === "FINAL" || c.status === "INCONCLUSIVE") return <p className="text-[14px] text-ink-2">Nothing: this check is closed for good.</p>;
  if (c.status === "OPEN" || c.status === "CONTESTED") {
    const deadline = c.status === "OPEN" ? c.read_deadline : c.contest_read_deadline;
    if (!hasReading && now >= deadline) {
      return <Act label="Expire this check" address={reg} fn="expire" args={[c.check_id]} onDone={onDone}
        note={c.status === "OPEN" ? "No reading arrived in time: the check closes inconclusive and the stake is refunded." : "No re-read arrived in time: the first ruling stands and the contest stake is refunded."} />;
    }
    if (!hasReading) {
      return <Act label={rnd === 2 ? "Re-read the pinned blocks" : "Read the pinned blocks"} address={ADDR.reader} fn="read_check" args={[reg, c.check_id, rnd]} onDone={onDone}
        note={`Every validator reads both chains from two RPCs each at the pinned blocks. Deadline ${absoluteTime(deadline)}.`} />;
    }
    return <Act label="Rule on the reading" address={reg} fn="rule" args={[c.check_id]} onDone={onDone}
      note="The contract computes locked, supply and the verdict from the recorded reading." />;
  }
  if (now < c.contest_deadline) {
    return <Act label="Contest this ruling" kind="quiet" address={reg} fn="contest" args={[c.check_id]} value={minStake ?? 0n} onDone={onDone}
      note={`Stake ${minStake !== null ? formatGen(minStake, 3) : "-"} GEN. The same blocks are read again: the same verdict makes it final and your stake goes to the side it favours; a different one closes it inconclusive and refunds everyone.`} />;
  }
  return <Act label="Finalize" address={reg} fn="finalize" args={[c.check_id]} onDone={onDone} note="The window has passed with no contest. Finalizing moves the money." />;
}
