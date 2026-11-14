"use client";

import Link from "next/link";
import { useState } from "react";
import { useKeeper } from "@/lib/keeper";
import { ADDR } from "@/lib/deployments";
import { remoteName } from "@/lib/remote";
import { Ext, Loading, Panel } from "@/components/ui";

const TONE: Record<string, string> = { DONE: "text-backed", FAILED: "text-under", RETRY: "text-inconc", QUEUED: "text-ink-2" };
const PAGE = 25;

export default function KeeperPage() {
  const k = useKeeper();
  const [page, setPage] = useState(0);
  if (!k) return <Loading what="Reading the keeper's last checkpoint" />;
  const s = k.status;
  return (
    <div className="pt-10 pb-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">Keeper</h1>
      <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-ink-2">
        A scheduled GitHub Actions job (hourly, and every 6 hours as a backstop) files monitoring checks, reads them (retrying a PENDING read
        inside its fixed window), rules, finalizes and expires them, and adds the destinations a vault&apos;s own bridge config names but its pair
        does not list. An action counts as done only when its transaction is FINALIZED, succeeded, and a read of contract state shows its effect.
        Every step is checkpointed on the <Ext href="https://github.com/kenil1710/backedby/tree/keeper-state">keeper-state</Ext> branch, so a
        run that dies resumes from its stored transaction hashes. Anyone can do every one of these actions by hand.
      </p>
      <p className="mt-3 text-[14px] text-ink-3">Last run {s.finished_at} ({s.trigger}){s.run_url && <> · <Ext href={s.run_url}>workflow run</Ext></>} · signer <span className="num">{s.keeper}</span></p>
      {Object.entries(s.contracts).filter(([, c]) => [ADDR.registry, ADDR.registryDemo].map((a) => a.toLowerCase()).includes(c.address.toLowerCase())).map(([name, c]) => {
        const acts = [...c.actions].reverse();
        const shown = acts.slice(page * PAGE, (page + 1) * PAGE);
        const un = Object.entries(c.unmatched ?? {}).flatMap(([pid, m]) => Object.values(m).map((u) => ({ pid, ...u })));
        return (
          <div key={name} className="mt-6 space-y-4">
            <Panel title={name} aside={<span className="num">{c.address}</span>}>
              <p className="text-[14px] text-ink-2">
                <span className="num">{c.totals.done}</span> done · <span className="num">{c.totals.pending}</span> waiting for finality ·{" "}
                <span className="num">{c.totals.retry}</span> retrying · <span className="num">{c.totals.queued}</span> queued ·{" "}
                <span className="num">{c.totals.failed}</span> failed · pages read {String(c.last_run.pages)} (failed {String(c.last_run.pages_failed)}) · pairs {String(c.last_run.pairs)}
              </p>
            </Panel>
            <Panel title="Destinations a vault backs that are not listed and cannot be added" aside={`${un.length}`}>
              {un.length === 0 && <p className="text-[14px] text-ink-3">None.</p>}
              <ul>{un.map((u) => (
                <li key={u.pid + u.remote} className="border-b border-seam/60 py-2 text-[13.5px] last:border-0">
                  <Link className="text-steel" href={`/pair/${u.pid}`}>Pair {u.pid}</Link>: {remoteName(u.remote)}
                  <div className="text-[12.5px] text-ink-3">{u.why}</div>
                </li>
              ))}</ul>
            </Panel>
            <Panel title="Not finished this run, with the reason" aside={`${c.unprocessed.length}`}>
              {c.unprocessed.length === 0 && <p className="text-[14px] text-ink-3">Nothing.</p>}
              <ul className="max-h-60 overflow-auto">{c.unprocessed.map((u) => <li key={u.key} className="py-1 text-[13px]"><span className="num">{u.key}</span> <span className="text-ink-3">{u.why}</span></li>)}</ul>
            </Panel>
            <Panel title="Actions" aside={<span>{acts.length} · page {page + 1}/{Math.max(1, Math.ceil(acts.length / PAGE))}{" "}
              <button className="text-steel disabled:opacity-40" disabled={page === 0} onClick={() => setPage(page - 1)}>prev</button>{" "}
              <button className="text-steel disabled:opacity-40" disabled={(page + 1) * PAGE >= acts.length} onClick={() => setPage(page + 1)}>next</button></span>}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] text-[13px]">
                  <thead><tr className="text-left text-ink-3"><th className="font-normal">Action</th><th className="font-normal">Status</th><th className="font-normal">Result</th><th className="font-normal">Tx</th></tr></thead>
                  <tbody>{shown.map((a) => (
                    <tr key={a.key} className="border-t border-seam/60"><td className="num py-1">{a.key}</td>
                      <td className={TONE[a.status] ?? "text-ink-2"}>{a.status.toLowerCase()}{a.attempts ? ` (${a.attempts})` : ""}</td>
                      <td className="text-ink-2">{a.result || a.last_error.slice(0, 80)}</td>
                      <td className="num">{a.tx ? <Ext href={`https://explorer-studio-dev.genlayer.com/tx/${a.tx}`}>{a.tx.slice(0, 10)}</Ext> : "-"}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </Panel>
          </div>
        );
      })}
      <Panel className="mt-6" title="Recent runs" aside={`${s.history.length}`}>
        <ul className="max-h-72 overflow-auto">{[...s.history].reverse().slice(0, 50).map((h) => (
          <li key={h.started_at} className="flex flex-wrap justify-between gap-2 border-b border-seam/60 py-1.5 text-[13px] last:border-0">
            <span className="num">{h.started_at}</span><span className="text-ink-3">{h.trigger}</span>
            <span className="text-ink-2">{Object.entries(h.runs).map(([n, r]) => `${n}: ${r.submitted} sent, ${r.done} done`).join(" · ")}</span>
            {h.run_url && <Ext href={h.run_url}>run</Ext>}
          </li>
        ))}</ul>
      </Panel>
    </div>
  );
}
