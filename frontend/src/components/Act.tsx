"use client";

/** One write button with its own progress line. Connects the wallet first if needed. */
import { useState } from "react";
import { send } from "@/lib/contract";
import { useWallet } from "./WalletProvider";
import { TxStatus, useTx } from "./tx";
import { Btn } from "./ui";
import type { CalldataEncodable } from "genlayer-js/types";

export function Act({ label, address, fn, args, value = 0n, confirm, onDone, kind = "primary", disabled, note }: {
  label: string; address: string; fn: string; args: CalldataEncodable[] | (() => Promise<CalldataEncodable[]>); value?: bigint;
  confirm?: () => Promise<boolean>; onDone?: () => void; kind?: "primary" | "quiet" | "danger"; disabled?: boolean; note?: string;
}) {
  const w = useWallet();
  const tx = useTx();
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setErr(null);
    if (!w.account) { await w.connect(); return; }
    await tx.run(async (onProgress) => {
      let a: CalldataEncodable[];
      try { a = typeof args === "function" ? await args() : args; } catch (e) { setErr(String((e as Error).message)); return; }
      const r = await send(w.account!, address, fn, a, value, { onProgress, confirm: confirm ? async () => confirm() : undefined });
      if (r.kind === "ok") { onDone?.(); void w.refreshBalance(); }
    });
  };
  return (
    <div>
      <Btn kind={kind} onClick={go} disabled={disabled || tx.busy}>{w.account ? label : `Connect wallet to ${label.toLowerCase()}`}</Btn>
      {note && <p className="mt-1.5 text-[12.5px] text-ink-3">{note}</p>}
      {err && <p className="mt-2 text-[13px] text-under">{err}</p>}
      <TxStatus progress={tx.progress} />
    </div>
  );
}
