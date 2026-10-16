"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { getBonds, getConfig, getPairs, registry } from "@/lib/contract";
import { CHAIN_NAME } from "@/lib/chains";
import { absoluteTime, formatGen, shortAddress } from "@/lib/format";
import { Act } from "@/components/Act";
import { Btn, Loading, Panel } from "@/components/ui";

export default function ChallengePage() {
  return <Suspense fallback={<Loading />}><Challenge /></Suspense>;
}

function Challenge() {
  const q = useSearchParams();
  const bonds = useSWR("bonds", () => getBonds(), { refreshInterval: 20_000 }).data;
  const pairs = useSWR("pairs", () => getPairs()).data;
  const cfg = useSWR("config", () => getConfig()).data;
  const [bid, setBid] = useState<number>(Number(q.get("bond") ?? 0) || 0);
  const [blocks, setBlocks] = useState("");
  const [pinNote, setPinNote] = useState("");
  const live = bonds?.bonds.filter((b) => (b.status === "ACTIVE" || b.status === "UNBONDING") && b.amount !== "0") ?? [];
  const bond = bonds?.bonds.find((b) => b.bond_id === bid);
  const pair = pairs?.pairs.find((p) => p.pair_id === bond?.pair_id);
  const chains = pair ? [...new Set(pair.dests.map((d) => d.chain))] : [];
  const pin = async () => {
    setPinNote("Pinning fresh finalized blocks on both chains");
    const r = await fetch(`/api/pins?chains=${chains.join(",")}`).then((x) => x.json());
    if (r.error) { setPinNote("Could not pin: " + r.error); return; }
    setBlocks(JSON.stringify(r.blocks));
    setPinNote(`Ethereum block at ${absoluteTime(r.detail.ethereum.timestamp)}, gap ${r.gap_s} s. You can edit these.`);
  };
  return (
    <div className="pt-10">
      <h1 className="wide text-[30px] font-semibold tracking-tight">Challenge a bond</h1>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">
        Say the bonded pair was not backed at blocks you pin: one finalized block on Ethereum and one on each destination chain,
        the Ethereum block at or after the others, at most {cfg ? cfg.max_gap_s / 60 : 10} minutes apart, and after the bond started.
        Validators read both chains and the contract rules. You lose the stake only if the final ruling is BACKED.
      </p>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <Panel title="Your challenge">
          <label className="block text-[13px] text-ink-3" htmlFor="bond">Bond</label>
          <select id="bond" value={bid} onChange={(e) => { setBid(Number(e.target.value)); setBlocks(""); setPinNote(""); }}
            className="mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[14px]">
            <option value={0}>Choose a bond</option>
            {live.map((b) => <option key={b.bond_id} value={b.bond_id}>Bond {b.bond_id}: pair {b.pair_id}, {formatGen(b.amount, 3)} GEN by {shortAddress(b.operator)}</option>)}
          </select>
          {bond && pair && (
            <p className="mt-2 text-[13px] text-ink-3">
              {pair.label}. Covers blocks from <span className="num">{absoluteTime(bond.since)}</span>
              {bond.unbond_at ? <> to <span className="num">{absoluteTime(bond.unbond_at)}</span></> : " onward"}.
            </p>
          )}
          <div className="mt-3 flex items-center justify-between gap-2">
            <label className="text-[13px] text-ink-3" htmlFor="blocks">Pinned blocks ({["ethereum", ...chains].map((c) => CHAIN_NAME[c] ?? c).join(", ")})</label>
            <Btn kind="quiet" onClick={() => void pin()} disabled={!pair}>Pin fresh blocks</Btn>
          </div>
          <textarea id="blocks" rows={2} value={blocks} onChange={(e) => setBlocks(e.target.value)} placeholder='{"ethereum": 26200000, "arbitrum": 515000000}'
            className="num mt-1 w-full rounded border border-seam bg-ground px-3 py-2 text-[13px]" />
          {pinNote && <p className="mt-1 text-[12.5px] text-ink-3">{pinNote}</p>}
          <div className="mt-4">
            <Act label="Challenge" address={registry()} fn="challenge" args={[bid, blocks]} value={cfg ? BigInt(cfg.min_stake) : 0n}
              disabled={!bond || !blocks} note={cfg ? `Stake ${formatGen(cfg.min_stake, 3)} GEN plus the write fee. Then open the check to have it read and ruled.` : undefined} />
          </div>
        </Panel>
        <Panel title="What happens to the stake">
          <ul className="space-y-2 text-[14px] text-ink-2">
            <li><span className="text-under">Final UNDER_BACKED</span>: stake back, plus {cfg ? cfg.bounty_bps / 100 : 50}% of the slashed bond.</li>
            <li><span className="text-backed">Final BACKED</span>: the stake is added to the operator&apos;s bond.</li>
            <li><span className="text-inconc">INCONCLUSIVE</span>: stake refunded. That includes RPCs that disagree, a reading that never arrives, and pins that break the rules.</li>
            <li>Every ruling is contestable for {cfg ? (cfg.window_s >= 3600 ? `${cfg.window_s / 3600} h` : `${cfg.window_s} s`) : "the window"}; a contest re-reads the same blocks.</li>
          </ul>
        </Panel>
      </div>
      {!bonds && <Loading what="Reading bonds" />}
    </div>
  );
}
