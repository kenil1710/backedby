"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { getBonds, getClaimable, getConfig, getPairs, registry } from "@/lib/contract";
import { absoluteTime, formatGen, parseGen, shortAddress } from "@/lib/format";
import { useWallet } from "@/components/WalletProvider";
import { Act } from "@/components/Act";
import { Loading, Panel, useNow } from "@/components/ui";

export default function BondPage() {
  return <Suspense fallback={<Loading />}><Bond /></Suspense>;
}

function Bond() {
  const q = useSearchParams();
  const w = useWallet();
  const now = useNow();
  const pairs = useSWR("pairs", () => getPairs()).data;
  const cfg = useSWR("config", () => getConfig()).data;
  const { data: bonds, mutate } = useSWR("bonds", () => getBonds(), { refreshInterval: 20_000 });
  const { data: cl, mutate: mcl } = useSWR(w.account ? ["claimable", w.account] : null, () => getClaimable(w.account!), { refreshInterval: 20_000 });
  const [pid, setPid] = useState<number>(Number(q.get("pair") ?? 0) || 0);
  const [amt, setAmt] = useState("");
  const min = cfg ? BigInt(cfg.min_bond) : 0n;
  const value = parseGen(amt || (cfg ? formatGen(cfg.min_bond, 4) : "0"));
  const mine = bonds?.bonds.filter((b) => w.account && b.operator === w.account.toLowerCase()) ?? [];
  return (
    <div className="pt-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">Bond a pair</h1>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        A bond says: this pair stays backed from now until I ask to unbond. Anyone can challenge it with a stake at blocks inside
        that span. If the final ruling is UNDER_BACKED the whole bond is slashed: half goes to the challenger with their stake back,
        half to the treasury. If it is BACKED, the challenger&apos;s stake is added to your bond.
      </p>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Panel title="New bond">
          <label className="block text-[13px] text-ink-3" htmlFor="pair">Pair</label>
          <select id="pair" value={pid} onChange={(e) => setPid(Number(e.target.value))}
            className="mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[14px]">
            <option value={0}>Choose a pair</option>
            {pairs?.pairs.map((p) => <option key={p.pair_id} value={p.pair_id}>{p.pair_id}. {p.label}</option>)}
          </select>
          <label className="mt-3 block text-[13px] text-ink-3" htmlFor="amt">Amount (GEN), minimum {cfg ? formatGen(cfg.min_bond, 3) : "-"}</label>
          <input id="amt" inputMode="decimal" value={amt} onChange={(e) => setAmt(e.target.value)} placeholder={cfg ? formatGen(cfg.min_bond, 3) : ""}
            className="num mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[14px]" />
          <div className="mt-4">
            <Act label="Bond" address={registry()} fn="bond" args={[pid]} value={value ?? 0n} disabled={!pid || value === null || value < min}
              onDone={() => void mutate()} note="A fee is estimated for the write and added by your wallet. A refused bond is credited back as claimable." />
          </div>
        </Panel>
        <Panel title="Your bonds and balance" aside={w.account ? shortAddress(w.account) : "connect a wallet"}>
          {!w.account && <p className="text-[14px] text-ink-3">Connect a wallet to see your bonds.</p>}
          {w.account && mine.length === 0 && <p className="text-[14px] text-ink-3">No bonds from this address.</p>}
          <ul>
            {mine.map((b) => (
              <li key={b.bond_id} className="border-b border-seam/60 py-3 last:border-0">
                <div className="flex flex-wrap justify-between gap-2 text-[14px]">
                  <span>Bond <span className="num">{b.bond_id}</span> on pair <span className="num">{b.pair_id}</span></span>
                  <span className="num">{formatGen(b.amount, 4)} GEN · {b.status.toLowerCase()}</span>
                </div>
                <div className="mt-2">
                  {b.status === "ACTIVE" && <Act kind="quiet" label="Request unbond" address={registry()} fn="request_unbond" args={[b.bond_id]} onDone={() => void mutate()}
                    note={cfg ? `Coverage stops now; withdraw after ${cfg.unbond_delay_s >= 3600 ? cfg.unbond_delay_s / 3600 + " h" : cfg.unbond_delay_s + " s"} if no check is open.` : undefined} />}
                  {b.status === "UNBONDING" && (now >= b.withdrawable_at
                    ? <Act kind="quiet" label="Withdraw bond" address={registry()} fn="withdraw_bond" args={[b.bond_id]} disabled={b.open_check > 0}
                        note={b.open_check > 0 ? `Check ${b.open_check} is open on it.` : "Credits the bond to your claimable balance."} onDone={() => { void mutate(); void mcl(); }} />
                    : <p className="text-[13px] text-ink-3">Withdrawable at <span className="num">{absoluteTime(b.withdrawable_at)}</span>.</p>)}
                </div>
              </li>
            ))}
          </ul>
          {cl && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-seam pt-3 text-[14px]">
              <span>Claimable <span className="num">{formatGen(cl.claimable, 4)}</span> GEN <span className="text-ink-3">(claimed <span className="num">{formatGen(cl.claimed, 4)}</span>)</span></span>
              <Act kind="quiet" label="Claim" address={registry()} fn="claim" args={[]} disabled={cl.claimable === "0"} onDone={() => void mcl()} />
            </div>
          )}
        </Panel>
      </div>
      {!bonds && <Loading what="Reading bonds" />}
    </div>
  );
}
