/**
 * Typed access to the BackedBy contracts.
 *
 * READS: every number on the site comes from one of these views.
 *
 * WRITES ARE NOT DONE WHEN SENT, AND NOT EVEN WHEN ACCEPTED. `send` reports
 * each phase (signing -> submitted -> accepted -> finalized) and only reports
 * success after `confirm` has re-read the contract and found the effect. A
 * payable call the registry turned down is a SUCCESSFUL transaction returning
 * ok:false (the value is credited to the sender's claimable balance), so it is
 * shown as "rejected", never as success.
 */
import type { CalldataEncodable, TransactionHash } from "genlayer-js/types";
import { encodeExternalMessageFeeParams } from "genlayer-js";
import { NETWORK, getDeployment, getReadClient, getWalletClient } from "./genlayer";
import { ADDR } from "./deployments";
import { withDisplayLabel } from "./labels";
import type { Bond, Check, GateAnswer, Ledger, Pair, Reading, RegistryConfig, Stats, TxProgress, WriteResult } from "./types";

const READ_TIMEOUT_MS = 45_000;

async function withTimeout<T>(work: Promise<T>, label: string, ms = READ_TIMEOUT_MS): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const guard = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms / 1000}s`)), ms);
  });
  try {
    return await Promise.race([work, guard]);
  } finally {
    clearTimeout(timer!);
  }
}

/** genlayer-js returns calldata maps as Map; turn them into plain objects. */
export function plain(v: unknown): unknown {
  if (v instanceof Map) {
    const o: Record<string, unknown> = {};
    for (const [k, x] of v.entries()) o[String(k)] = plain(x);
    return o;
  }
  if (Array.isArray(v)) return v.map(plain);
  if (typeof v === "bigint") return Number(v) <= Number.MAX_SAFE_INTEGER ? Number(v) : v.toString();
  return v;
}

/** Reads go through the site's cached /api/view in the browser (one Studio read
 *  per 20 s per view, shared by every visitor), and straight to Studio elsewhere. */
let freshReads = 0;

async function readRaw(address: string, functionName: string, args: CalldataEncodable[]): Promise<unknown> {
  if (typeof window !== "undefined") {
    const q = new URLSearchParams({ a: address, f: functionName, args: JSON.stringify(args, (_k, v) => (typeof v === "bigint" ? v.toString() : v)) });
    // after a write, re-read the contract itself, never a cached copy
    if (freshReads > 0) q.set("fresh", String(Date.now()));
    const r = await fetch(`/api/view?${q}`);
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error ?? `view ${functionName} failed`);
    return j.value;
  }
  return getReadClient().readContract({ address: address as `0x${string}`, functionName, args });
}

export async function viewOf<T>(address: string, functionName: string, args: CalldataEncodable[] = []): Promise<T> {
  const raw = await withTimeout(readRaw(address, functionName, args), functionName);
  if (typeof raw === "string") {
    try { return JSON.parse(raw) as T; } catch { return raw as T; }
  }
  return plain(raw) as T;
}

export const registry = () => (getDeployment() === "demo" ? ADDR.registryDemo : ADDR.registry);
export const gate = () => (getDeployment() === "demo" ? ADDR.gateDemo : ADDR.gate);

const rv = <T,>(fn: string, args: CalldataEncodable[] = [], reg?: string) => viewOf<T>(reg ?? registry(), fn, args);

export const getConfig = (reg?: string) => rv<RegistryConfig>("get_config", [], reg);
export const getStats = (reg?: string) => rv<Stats>("get_stats", [], reg);
export const getLedger = (reg?: string) => rv<Ledger>("get_ledger", [], reg);
export const getPairs = async (reg?: string) => {
  const r = await rv<{ total: number; pairs: Pair[] }>("get_pairs", [0, 50], reg);
  return { ...r, pairs: r.pairs.map((p) => withDisplayLabel(p, reg ?? registry())) };
};
export const getPair = async (id: number, reg?: string) => withDisplayLabel(await rv<Pair>("get_pair", [id], reg), reg ?? registry());
export const getCheck = (id: number, reg?: string) => rv<Check>("get_check", [id], reg);
export const getChecks = (offset = 0, limit = 50, reg?: string) => rv<{ total: number; checks: Check[] }>("get_checks", [offset, limit], reg);
export const getBond = (id: number, reg?: string) => rv<Bond>("get_bond", [id], reg);
export const getBonds = (reg?: string) => rv<{ total: number; bonds: Bond[] }>("get_bonds", [0, 50], reg);
export const getClaimable = (who: string, reg?: string) => rv<{ address: string; claimable: string; claimed: string }>("get_claimable", [who], reg);
export const getReading = (checkId: number, round: number, reg?: string) =>
  viewOf<Reading>(ADDR.reader, "get_reading", [reg ?? registry(), checkId, round]);
export const getAuth = (id: number) => viewOf<Record<string, unknown>>(ADDR.reader, "get_auth", [id]);
export const getReaderConfig = () => viewOf<Record<string, unknown>>(ADDR.reader, "get_config");
export const isBacked = (pairId: number, now: number, g?: string) => viewOf<GateAnswer>(g ?? gate(), "is_backed", [pairId, now]);
export const getAttempts = (g?: string) =>
  viewOf<{ total: number; allowed: number; refused: number; attempts: { attempt_id: number; sender: string; pair_id: number; amount: string; allowed: boolean; reason: string; check_id: number; at: number; note: string }[] }>(g ?? gate(), "get_attempts", [0, 25]);
export const getGateConfig = (g?: string) => viewOf<{ registry: string; max_age_s: number; max_tolerance_bps: number }>(g ?? gate(), "get_config");

// ── Writes ─────────────────────────────────────────────────────────────────

const STATUS_NAMES = ["PENDING", "PROPOSING", "COMMITTING", "REVEALING", "ACCEPTED", "FINALIZED", "UNDETERMINED", "CANCELED"];

function statusName(tx: unknown): string {
  const t = tx as { status?: number | string; statusName?: string };
  if (typeof t?.status === "number") return STATUS_NAMES[t.status] ?? "";
  return String(t?.statusName ?? t?.status ?? "");
}

/** The SDK's `readable` rendering drops commas between map entries; put them back. */
export function repairReadable(text: string): string {
  let out = "";
  let inString = false;
  let escaped = false;
  for (const ch of text) {
    if (inString) {
      out += ch;
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      const prev = out.replace(/\s+$/, "").slice(-1);
      if (prev && !"{[,:".includes(prev)) out += ",";
      out += ch;
      inString = true;
      continue;
    }
    out += ch;
  }
  return out;
}

function returned(tx: unknown): { reverted: boolean; reason: string; body: Record<string, unknown> | null } {
  const receipt = (tx as { consensus_data?: { leader_receipt?: unknown[] } })?.consensus_data?.leader_receipt?.[0] as
    | { result?: { payload?: unknown; status?: string; raw?: string }; execution_result?: string } | undefined;
  const reverted = receipt?.execution_result === "ERROR" || receipt?.result?.status === "rollback" ||
    (tx as { txExecutionResultName?: string })?.txExecutionResultName === "FINISHED_WITH_ERROR";
  const payload = receipt?.result?.payload as { readable?: string } | string | undefined;
  if (reverted) return { reverted, reason: typeof payload === "string" && payload ? payload : "The contract refused this call", body: null };
  const text = typeof payload === "string" ? payload : typeof payload?.readable === "string" ? payload.readable : null;
  if (!text) return { reverted: false, reason: "", body: null };
  for (const candidate of [text, repairReadable(text)]) {
    try {
      let v: unknown = JSON.parse(candidate);
      if (typeof v === "string") v = JSON.parse(v);
      if (v && typeof v === "object") return { reverted: false, reason: "", body: v as Record<string, unknown> };
    } catch { /* next */ }
  }
  return { reverted: false, reason: "", body: null };
}

/** The contract's own refusal, from a failed fee simulation (a write that would revert). */
function contractRefusal(error: unknown): string | null {
  type Node = { cause?: unknown; data?: { receipt?: { result?: unknown } } };
  let node = error as Node | undefined;
  for (let depth = 0; node && depth < 6; depth++, node = node.cause as Node | undefined) {
    const result = node?.data?.receipt?.result;
    const encoded = typeof result === "string" ? result
      : typeof (result as { payload?: unknown })?.payload === "string" ? (result as { payload: string }).payload : null;
    if (!encoded) continue;
    try {
      const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
      let start = 0;
      while (start < bytes.length && bytes[start] < 0x20) start++;
      const text = new TextDecoder().decode(bytes.subarray(start)).trim();
      if (text) return text;
    } catch { /* not base64 */ }
  }
  return null;
}

let feePolicyEnabled: boolean | null = null;

/**
 * Studio Dev refuses a write that carries no fee. The fee is estimated per
 * call by simulating it. claim() pays with one external value message, so its
 * fees must carry an External allocation naming the claimant (the registry's
 * _send; docs/RULES.md#payouts): if the estimate has none, one is added
 * (500,000 gas at the locked price plus 20%), and a claim is never sent without it.
 */
const EXT_GAS = 500_000n;
type Alloc = { messageType: unknown; recipient: unknown; budget?: unknown };
const hasPayout = (fees: { messageAllocations?: Alloc[] } | undefined, who: string) =>
  Boolean(fees?.messageAllocations?.some((a) => Number(a.messageType) === 0 && String(a.recipient).toLowerCase() === who.toLowerCase()
    && BigInt(String(a.budget ?? 0)) > 0n));

async function feesFor(wallet: ReturnType<typeof getWalletClient>, account: `0x${string}`,
    address: `0x${string}`, functionName: string, args: CalldataEncodable[], value: bigint) {
  if (feePolicyEnabled === null) {
    try { feePolicyEnabled = Boolean((await wallet.getCurrentFeePolicy())?.enabled); } catch { feePolicyEnabled = true; }
  }
  if (!feePolicyEnabled) return undefined;
  let est: Awaited<ReturnType<typeof wallet.estimateTransactionFeesForWrite>> | null = null;
  try {
    est = await withTimeout(wallet.estimateTransactionFeesForWrite({ address, functionName, args, value }), "fee estimate", 30_000);
  } catch (e) {
    const refusal = contractRefusal(e);
    if (refusal) throw new Error(refusal);
  }
  if (functionName !== "claim") return est ?? withTimeout(wallet.estimateTransactionFees({}), "fee estimate", 30_000);
  if (est && hasPayout(est, account)) return est;
  const price = (BigInt(est?.policy?.receiptGasPrice ?? 250_000_000n) * 12n) / 10n;
  const messageAllocations = [{ messageType: 0, recipient: account, budget: EXT_GAS * price, onAcceptance: false,
    feeParams: encodeExternalMessageFeeParams({ gasLimit: EXT_GAS, maxGasPrice: price }) }];
  const fees = await withTimeout(wallet.estimateTransactionFees({ messageAllocations }), "fee estimate", 30_000);
  if (!hasPayout(fees, account)) throw new Error("The claim's payout could not be funded; nothing was sent.");
  return fees;
}

export interface SendOptions<T> {
  confirm?: (body: T | null) => Promise<boolean>;
  onProgress?: (p: TxProgress) => void;
}

export async function send<T>(account: `0x${string}`, address: string, functionName: string, args: CalldataEncodable[],
    value = 0n, opts: SendOptions<T> = {}): Promise<WriteResult<T>> {
  const report = (p: TxProgress) => opts.onProgress?.(p);
  const wallet = getWalletClient(account);
  const read = getReadClient();
  let hash: string;
  report({ phase: "signing", hash: null, message: "Waiting for your wallet to sign." });
  try {
    const fees = await feesFor(wallet, account, address as `0x${string}`, functionName, args, value);
    hash = await wallet.writeContract({ address: address as `0x${string}`, functionName, args, value, ...(fees ? { fees } : {}) });
  } catch (e) {
    const message = String((e as Error)?.message ?? e);
    const funding = /insufficient|exceeds balance|not enough/i.test(message)
      ? (NETWORK === "studiodev" ? "This wallet does not hold enough GEN for the value and the fee. Fund it from the Studio Dev faucet." : "Not enough GEN.")
      : null;
    const error = contractRefusal(e) ?? funding ?? message;
    report({ phase: "failed", hash: null, message: error });
    return { kind: "failed", hash: null, error };
  }
  report({ phase: "submitted", hash, message: "Submitted. Validators are processing it; each validator reads two RPCs per chain; this can take a few minutes." });
  const started = Date.now();
  let tx: unknown = null;
  for (;;) {
    await new Promise((r) => setTimeout(r, 4000));
    try { tx = await read.getTransaction({ hash: hash as TransactionHash }); } catch { /* keep polling */ }
    const name = statusName(tx);
    if (name === "ACCEPTED" || name === "FINALIZED") break;
    if (name === "UNDETERMINED") {
      const error = "The validators did not agree, so nothing was written. Anyone can send it again before the deadline.";
      report({ phase: "failed", hash, message: error });
      return { kind: "failed", hash, error };
    }
    if (name === "CANCELED") {
      report({ phase: "failed", hash, message: "The transaction was canceled." });
      return { kind: "failed", hash, error: "The transaction was canceled." };
    }
    if (Date.now() - started > 900_000) {
      const error = "Not accepted within 15 minutes. It may still land; check the explorer.";
      report({ phase: "failed", hash, message: error });
      return { kind: "failed", hash, error };
    }
  }
  const r = returned(tx);
  if (r.reverted) {
    report({ phase: "failed", hash, message: r.reason });
    return { kind: "failed", hash, error: r.reason };
  }
  if (r.body && r.body.ok === false) {
    const reason = String(r.body.reason ?? "The contract turned this down");
    report({ phase: "rejected", hash, message: reason });
    return { kind: "rejected", hash, reason };
  }
  if (opts.confirm) {
    report({ phase: "accepted", hash, message: "Accepted. Re-reading the contract to confirm." });
    let ok = false;
    for (let i = 0; i < 6 && !ok; i++) {
      freshReads++;
      try { ok = await opts.confirm(r.body as T | null); } catch { ok = false; } finally { freshReads--; }
      if (!ok) await new Promise((res) => setTimeout(res, 4000));
    }
    if (!ok) {
      const error = "Accepted, but the contract state does not show the change yet. Nothing is claimed until it does.";
      report({ phase: "failed", hash, message: error });
      return { kind: "failed", hash, error };
    }
  }
  report({ phase: "accepted", hash, message: "Accepted and confirmed in contract state. Waiting for finality." });
  void (async () => {
    for (let i = 0; i < 120; i++) {
      await new Promise((res) => setTimeout(res, 10_000));
      try {
        const t = await read.getTransaction({ hash: hash as TransactionHash });
        if (statusName(t) === "FINALIZED") {
          report({ phase: "finalized", hash, message: "Finalized." });
          return;
        }
      } catch { /* keep waiting */ }
    }
  })();
  return { kind: "ok", hash, data: (r.body ?? {}) as T };
}
