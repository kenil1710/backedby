"use client";

import useSWR from "swr";
import { COMMIT } from "@/lib/deployments";
import { explorerUrl } from "@/lib/genlayer";
import { shortAddress } from "@/lib/format";
import { Ext, Loading, Panel } from "@/components/ui";

type Row = { name: string; address: string; file: string; commit: string; source_url: string; chain_sha256?: string; file_sha256?: string; recorded_sha256?: string; bytes?: number; identical: boolean; error?: string };

export default function Verify() {
  const { data, error } = useSWR("verify", () => fetch("/api/verify").then((r) => r.json()) as Promise<{ checked_at: string; all_identical: boolean; contracts: Row[] }>);
  return (
    <div className="pt-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">Verify the source</h1>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        Every contract was deployed from one commit, <Ext href={`https://github.com/kenil1710/backedby/tree/${COMMIT}`}><span className="num">{COMMIT.slice(0, 10)}</span></Ext>.
        This page asks Studio Dev for the code it runs at each address, right now, and compares it byte for byte with the build file at
        that commit on GitHub. The same check runs from a terminal: <span className="num text-ink">node tools/verify_source.mjs</span>.
      </p>
      {error && <p className="mt-6 text-under">The check could not run: {String(error)}</p>}
      {!data && !error && <Loading what="Fetching the deployed code" />}
      {data && (
        <Panel className="mt-6" title={data.all_identical ? "Every contract is byte-identical to the commit" : "Mismatch or unreadable"}
          aside={<span className="num">checked {data.checked_at.slice(0, 19).replace("T", " ")} UTC</span>}>
          <ul>
            {data.contracts.map((r) => (
              <li key={r.name} className="border-b border-seam/60 py-3 last:border-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-[15px] font-medium">{r.name}</span>
                  <span className={r.identical ? "text-backed" : "text-under"}>{r.identical ? "identical" : r.error ? "unreadable" : "differs"}</span>
                </div>
                <div className="mt-1 grid gap-x-6 text-[12.5px] text-ink-3 sm:grid-cols-2">
                  <span>address <Ext href={explorerUrl("address", r.address)}><span className="num">{shortAddress(r.address, 6)}</span></Ext></span>
                  <span>file <Ext href={r.source_url}><span className="num">{r.file}</span></Ext>{r.bytes ? <span className="num">, {r.bytes} bytes</span> : null}</span>
                  {r.chain_sha256 && <span className="num break-all">on chain {r.chain_sha256}</span>}
                  {r.file_sha256 && <span className="num break-all">at commit {r.file_sha256}</span>}
                  {r.error && <span className="text-under">{r.error}</span>}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
