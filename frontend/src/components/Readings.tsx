"use client";

/** Both sides of one reading: block, time, the value, and an explorer link for every read. */
import useSWR from "swr";
import { getReading } from "@/lib/contract";
import { CHAIN_NAME, KIND_NAME, symbolOf } from "@/lib/chains";
import { absoluteTime, chainUrl, formatUnits, holderUrl, shortAddress } from "@/lib/format";
import { selName } from "@/lib/selectors";
import type { Check, Pair } from "@/lib/types";
import { Ext, Panel } from "./ui";

export function Readings({ pair, check, round = 1 }: { pair: Pair; check: Check; round?: number }) {
  const { data } = useSWR(["reading", check.check_id, round], () => getReading(check.check_id, round), { refreshInterval: 20_000 });
  const r = data?.found ? data.reading : undefined;
  const src = r?.blocks?.ethereum;
  const ruling = round === 2 ? check.ruling2 : check.ruling1;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Locked on Ethereum" aside={`${check.vaults.length} vault${check.vaults.length > 1 ? "s" : ""}, summed`}>
        <dl>
          <Row k="Block">{src ? <Ext href={chainUrl("ethereum", "block", src.number)}><span className="num">{src.number}</span></Ext> : <span className="num">{check.blocks.ethereum}</span>}</Row>
          <Row k="Timestamp">{src ? <span className="num">{absoluteTime(src.timestamp)}</span> : "not read yet"}</Row>
          {check.vaults.map((v, i) => {
            const kind = pair.vaults?.find((x) => x.vault === v)?.kind;
            return (
              <Row key={v} k={<span>Vault <Ext href={chainUrl("ethereum", "address", v)}><span className="num">{shortAddress(v)}</span></Ext>{kind ? <span className="block text-[12px] text-ink-3">{KIND_NAME[kind] ?? kind}</span> : null}</span>}>
                {r?.status === "OK" ? <Ext href={holderUrl("ethereum", pair.source_token, v)}><span className="num">{formatUnits(r.locked_by_vault[i], r.source_decimals, 2)}</span></Ext> : "-"}
                <span className="text-ink-3"> {symbolOf(pair.source_token)}</span>
              </Row>
            );
          })}
          {r?.status === "OK" && check.vaults.length > 1 && (
            <Row k="Locked, total"><span className="num">{formatUnits(r.locked_by_vault.reduce((a, b) => (BigInt(a) + BigInt(b)).toString(), "0"), r.source_decimals, 2)}</span></Row>
          )}
          <Row k="Decimals"><span className="num">{r?.source_decimals ?? pair.source_decimals}</span> <span className="text-ink-3">(frozen {pair.source_decimals})</span></Row>
        </dl>
      </Panel>
      <Panel title={`Supply on ${[...new Set(check.dests.map((d) => CHAIN_NAME[d.chain] ?? d.chain))].join(", ")}`}>
        <dl>
          {Object.entries(check.blocks).filter(([c]) => c !== "ethereum").map(([c, n]) => (
            <Row key={c} k={`${CHAIN_NAME[c] ?? c} block`}>
              <Ext href={chainUrl(c, "block", n)}><span className="num">{n}</span></Ext>
              {r?.blocks?.[c] && <span className="num ml-2 text-ink-3">{absoluteTime(r.blocks[c].timestamp)}</span>}
            </Row>
          ))}
          {check.dests.map((d, i) => {
            const got = r?.dests?.[i];
            return (
              <Row key={d.token} k={<Ext href={chainUrl(d.chain, "address", d.token)}><span className="num">{shortAddress(d.token)}</span></Ext>}>
                {got ? <span className="num">{formatUnits(got.supply, got.decimals, 2)}</span> : "-"}
                {got?.deposits ? <span className="block text-[12.5px] text-ink-3">bridge ledger (deposits): <span className="num">{formatUnits(got.deposits, r!.source_decimals, 2)}</span>; counted, the larger: {ruling?.counted?.[i] ? formatUnits(ruling.counted[i], got.decimals, 2) : "-"}</span> : null}
              </Row>
            );
          })}
          {src && r?.blocks && (
            <Row k="Gap">
              <span className="num">{src.timestamp - Math.min(...Object.entries(r.blocks).filter(([c]) => c !== "ethereum").map(([, b]) => b.timestamp))} s</span>
              <span className="text-ink-3"> (max {check.max_gap_s} s; source at or after every destination)</span>
            </Row>
          )}
        </dl>
      </Panel>
      {r && r.anchors?.length > 0 && (
        <Panel title="Bridge mapping re-read at these blocks" className="md:col-span-2">
          <ul className="space-y-1.5 text-[13.5px]">
            {pair.anchors.map((a, i) => {
              const same = (r.anchors[i] ?? "").toLowerCase() === a[3].toLowerCase();
              return (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2">
                  <span className={same ? "text-backed" : "text-under"}>{same ? "unchanged" : "changed"}</span>
                  <span className="text-ink-3">{CHAIN_NAME[a[0]] ?? a[0]}</span>
                  <Ext href={chainUrl(a[0], "address", a[1])}><span className="num">{shortAddress(a[1])}</span></Ext>
                  <span className="num text-ink-2">{selName(a[2])}</span>
                  <span className="num text-ink-3">= {shortAddress("0x" + a[3].slice(26), 4)}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
      )}
      {data?.found && r?.status !== "OK" && (
        <p className="md:col-span-2 text-[14px] text-inconc">This reading is INCONCLUSIVE: {r?.reason}.</p>
      )}
    </div>
  );
}

function Row({ k, children }: { k: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] gap-3 border-b border-seam/60 py-2 text-[14px] last:border-0">
      <dt className="text-ink-3">{k}</dt><dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}
