"use client";

import { useState } from "react";
import useSWR from "swr";
import { gate, getAttempts, getGateConfig, getPairs, isBacked } from "@/lib/contract";
import { absoluteTime, shortAddress } from "@/lib/format";
import { Act } from "@/components/Act";
import { Loading, Panel, Verdict } from "@/components/ui";

export default function Collateral() {
  const pairs = useSWR("pairs", () => getPairs()).data;
  const gcfg = useSWR("gate-config", () => getGateConfig()).data;
  const now = Math.floor(Date.now() / 1000);
  const { data: answers } = useSWR(pairs ? ["gate", pairs.total] : null,
    () => Promise.all(pairs!.pairs.map(async (p) => ({ p, a: await isBacked(p.pair_id, now) }))), { refreshInterval: 60_000 });
  const { data: log, mutate } = useSWR("attempts", () => getAttempts(), { refreshInterval: 20_000 });
  const [pid, setPid] = useState(0);
  const [amt, setAmt] = useState("1000");
  return (
    <div className="pt-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">Collateral gate</h1>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        A lending market asks one question before it accepts a bridged token: is it backed right now? CollateralGate answers yes
        only if the pair&apos;s latest ruling is final and BACKED, its pinned Ethereum block is at most
        {gcfg ? ` ${gcfg.max_age_s >= 3600 ? gcfg.max_age_s / 3600 + " h" : gcfg.max_age_s / 60 + " min"}` : ""} old, no ruling in that time said
        anything else, and the pair&apos;s tolerance is at most {gcfg ? gcfg.max_tolerance_bps : "-"} bps. The demo borrow below asks it on chain
        and records the answer either way. Nothing is lent.
      </p>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="The gate's answer for every pair" aside={`contract ${shortAddress(gate())}`}>
          {!answers && <Loading what="Asking the gate" />}
          <ul>
            {answers?.map(({ p, a }) => (
              <li key={p.pair_id} className="grid grid-cols-[1fr_auto] gap-x-3 border-b border-seam/60 py-2.5 text-[14px] last:border-0">
                <span className="truncate">{p.pair_id}. {p.label}</span>
                <span className={a.backed ? "text-backed" : "text-under"}>{a.backed ? "would accept" : "refuses"}</span>
                <span className="col-span-2 text-[12.5px] text-ink-3">{a.reason.toLowerCase().replaceAll("_", " ")}{a.check_id ? `, check ${a.check_id}` : ""}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="space-y-4">
          <Panel title="Borrow against a bridged token">
            <label className="block text-[13px] text-ink-3" htmlFor="gp">Pair</label>
            <select id="gp" value={pid} onChange={(e) => setPid(Number(e.target.value))} className="mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[14px]">
              <option value={0}>Choose a pair</option>
              {pairs?.pairs.map((p) => <option key={p.pair_id} value={p.pair_id}>{p.pair_id}. {p.label}</option>)}
            </select>
            <label className="mt-3 block text-[13px] text-ink-3" htmlFor="ga">Amount (token units, demo only)</label>
            <input id="ga" value={amt} onChange={(e) => setAmt(e.target.value)} className="num mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[14px]" />
            <div className="mt-4"><Act label="Ask to borrow" address={gate()} fn="borrow" args={[pid, amt, "site demo"]} disabled={!pid} onDone={() => void mutate()} /></div>
          </Panel>
          <Panel title="Every borrow the gate was asked for" aside={log ? `${log.allowed} allowed, ${log.refused} refused` : ""}>
            <ul>
              {log?.attempts.map((x) => (
                <li key={x.attempt_id} className="flex flex-wrap items-center justify-between gap-2 border-b border-seam/60 py-2 text-[13.5px] last:border-0">
                  <span><span className="num text-ink-3">#{x.attempt_id}</span> pair <span className="num">{x.pair_id}</span> by <span className="num">{shortAddress(x.sender)}</span></span>
                  <Verdict v={x.allowed ? "BACKED" : x.reason === "UNDER_BACKED" ? "UNDER_BACKED" : "INCONCLUSIVE"} />
                  <span className="w-full text-[12.5px] text-ink-3">{x.allowed ? "allowed" : `refused: ${x.reason.toLowerCase().replaceAll("_", " ")}`} · <span className="num">{absoluteTime(x.at)}</span></span>
                </li>
              ))}
              {log && log.total === 0 && <li className="text-[14px] text-ink-3">No attempts yet.</li>}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
