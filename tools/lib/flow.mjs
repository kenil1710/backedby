// The on-chain steps every script uses (seeds, demo, patrol): authenticate,
// register, bond, challenge, monitor, read, rule, contest, finalize, expire.
// Each write goes through test/harness.mjs (fee estimate, settle-aware
// outcome); each result is confirmed from contract STATE, never from the
// return value alone.
import { readFileSync } from "node:fs";
import { connect, returnedJson, sleep } from "../../test/harness.mjs";
import { pinBlocks } from "./pin.mjs";
import { payoutFees, payoutDelivered, checkBalances } from "./payout.mjs";

const plain = (x) => JSON.parse(JSON.stringify(x, (k, v) => (typeof v === "bigint" ? v.toString() : v)));

/** Wait until a transaction is FINALIZED (payouts are applied then). */
export async function finalizedTx(read, hash, timeoutMs = 900_000) {
  const t0 = Date.now();
  for (;;) {
    try {
      const tx = plain(await read.getTransaction({ hash }));
      if (["FINALIZED", "CANCELED", "UNDETERMINED"].includes(tx.statusName)) return tx;
    } catch { /* RPC noise: poll again */ }
    if (Date.now() - t0 > timeoutMs) return null;
    await sleep(6000);
  }
}

export function deployments(set = "final") {
  return JSON.parse(readFileSync(new URL(set === "final" ? "../../deployments.json" : `../../deployments.${set}.json`, import.meta.url), "utf8"));
}

export function actor({ set = "final", role, registry = "BackedByRegistry", log = console.log }) {
  const dep = deployments(set).contracts;
  const R = connect({ address: dep[registry].address, role });
  const C = connect({ address: dep.ChainReader.address, role });
  const regAddr = dep[registry].address;
  const j = (x) => (typeof x === "string" ? JSON.parse(x) : x);
  const rv = async (fn, args = []) => j(await R.view(fn, args));
  const cv = async (fn, args = []) => j(await C.view(fn, args));

  async function send(which, fn, args, value = 0n) {
    const t0 = Date.now();
    const out = await (which === "reader" ? C : R).send(fn, args, BigInt(value));
    const ret = returnedJson(out);
    log(`  ${fn}(${JSON.stringify(args).slice(0, 140)})${value ? ` value=${value}` : ""} -> ${out.ok ? "ok" : "FAILED"} ${out.status} ${((Date.now() - t0) / 1000).toFixed(0)}s tx ${out.hash}` +
      (out.ok ? (ret ? ` ${JSON.stringify(ret).slice(0, 220)}` : "") : ` revert: ${String(out.revertReason).slice(0, 200)}`));
    return { ...out, ret };
  }

  /** Public RPCs answer Studio's shared egress with 429s in bursts. A transport
   *  failure (REFUSED: RPC_UNREADABLE, or a reading recorded INCONCLUSIVE ·
   *  RPC_UNREADABLE) is waited out and tried again; nothing else is retried. */
  async function patiently(label, attempt, isTransport, tries = 12) {
    let last;
    for (let i = 1; i <= tries; i++) {
      try { last = await attempt(); } catch (e) { last = { ok: false, revertReason: "RPC_UNREADABLE local: " + String(e.message).slice(0, 80), check: { status: "INCONCLUSIVE", reason: "RPC_UNREADABLE" } }; }
      if (!isTransport(last)) return last;
      const wait = Math.min(60 + 45 * i, 480);
      log(`  ... ${label}: RPC throttled from GenVM (attempt ${i}), retrying in ${wait}s`);
      await sleep(wait * 1000);
    }
    return last;
  }

  return {
    regAddr, rv, cv, send, patiently,
    async authenticateP(kind, l1, l2) {
      return patiently(`authenticate ${kind}`, () => this.authenticate(kind, l1, l2),
        (o) => !o.auth_id && /RPC_UNREADABLE|RPC_DISAGREE|UNSETTLED|submit failed/.test(String(o.revertReason)));
    },
    /** file (a function returning {check_id}) -> read -> rule, refiling while the read is transport-inconclusive */
    async fileReadRule(label, file) {
      return patiently(label, async () => {
        const f = await file();
        if (!f.check_id) return { check: null, filed: f };
        await this.read(f.check_id);
        const c = await this.rule(f.check_id);
        return { check: c, filed: f };
      }, (r) => r.check && r.check.status === "INCONCLUSIVE" && r.check.reason === "RPC_UNREADABLE");
    },
    async authenticate(kind, l1, l2) {
      const before = (await cv("get_config")).auths;
      const o = await send("reader", "authenticate", [kind, l1, l2]);
      if (!o.ok) return { ...o, auth_id: 0 };
      let id = o.ret?.auth_id ?? 0;
      if (!id) {
        const after = (await cv("get_config")).auths;
        id = after > before ? after : 0;
      }
      return { ...o, auth_id: id };
    },
    async register(ids, tol, label) {
      const before = (await rv("get_stats")).pairs;
      const o = await send("reg", "register_pair", [ids.join(","), tol, label]);
      const after = (await rv("get_stats")).pairs;
      return { ...o, pair_id: o.ok ? (o.ret?.pair_id ?? (after > before ? after : 0)) : 0 };
    },
    async pins(pid, margin = 90) {
      const p = await rv("get_pair", [pid]);
      const dests = [...new Set(p.dests.map((d) => d.chain))];
      const r = await pinBlocks("ethereum", dests, { margin });
      const blocks = {};
      for (const [c, b] of Object.entries(r.blocks)) blocks[c] = b.number;
      return { blocks, detail: r.blocks, gap: r.gap };
    },
    async newCheck(o) {
      const n = (await rv("get_stats")).checks;
      return o.ok ? (o.ret?.check_id ?? n) : 0;
    },
    async monitor(pid, blocks) {
      const o = await send("reg", "monitor", [pid, JSON.stringify(blocks)]);
      return { ...o, check_id: await this.newCheck(o) };
    },
    async challenge(bid, blocks, stake) {
      const o = await send("reg", "challenge", [bid, JSON.stringify(blocks)], stake);
      const ok = o.ok && o.ret?.ok !== false;
      return { ...o, ok, check_id: ok ? await this.newCheck(o) : 0 };
    },
    async bond(pid, amount) {
      const o = await send("reg", "bond", [pid], amount);
      const n = (await rv("get_stats")).bonds;
      return { ...o, bond_id: o.ok && o.ret?.ok !== false ? (o.ret?.bond_id ?? n) : 0 };
    },
    async read(cid, rnd = 1, tries = 3) {
      for (let i = 1; i <= tries; i++) {
        const o = await send("reader", "read_check", [regAddr, cid, rnd]);
        const r = await cv("get_reading", [regAddr, cid, rnd]);
        if (r.found) return { ...o, reading: r };
        if (/ALREADY_READ|NOT_THIS_ROUND|REQUEST_NOT_READABLE/.test(String(o.revertReason))) return { ...o, reading: r };
        if (i < tries) { log(`  ... read attempt ${i} did not record, retrying in 20s`); await sleep(20000); }
      }
      return { ok: false, reading: { found: false } };
    },
    async rule(cid) {
      await send("reg", "rule", [cid]);
      return rv("get_check", [cid]);
    },
    async finalize(cid) {
      await send("reg", "finalize", [cid]);
      return rv("get_check", [cid]);
    },
    async expire(cid) {
      await send("reg", "expire", [cid]);
      return rv("get_check", [cid]);
    },
    async contest(cid, stake) {
      const o = await send("reg", "contest", [cid], stake);
      return { ...o, check: await rv("get_check", [cid]) };
    },
    check: (cid) => rv("get_check", [cid]),
    /** claim() with a funded payout, then proof it arrived: the finalized
     *  transaction's value effect is delivered and not skipped, the registry's
     *  eth_getBalance fell by exactly the amount, and the payee's rose by the
     *  amount less what it paid for the claim. -> a record for docs/payouts.json */
    async claimVerified(label) {
      const payee = R.account.address;
      const owed = BigInt((await rv("get_claimable", [payee])).claimable);
      if (owed === 0n) return null;
      const bal = (a) => R.read.getBalance({ address: a });
      const cb = await bal(regAddr), pb = await bal(payee);
      const fees = await payoutFees(R.wallet, { address: regAddr, functionName: "claim", args: [], payee });
      const out = await R.send("claim", [], 0n, { fees });
      log(`  claim() by ${label} ${payee} owed ${owed} -> ${out.ok ? "ok" : "FAILED"} ${out.status} tx ${out.hash}`);
      const rec = { label, payee, amount: owed.toString(), tx: out.hash, registry: regAddr };
      if (!out.ok) return { ...rec, ok: false, why: "claim failed: " + String(out.revertReason).slice(0, 160) };
      const tx = await finalizedTx(R.read, out.hash);
      const d = payoutDelivered(tx, payee, owed);
      let why = d.why, payeeCheck = "";
      let ca = await bal(regAddr), pa = await bal(payee);
      if (d.ok) {
        // the payee's earlier transactions may still be settling their fee refunds: re-measure a few times
        for (let i = 0; i < 4; i++) {
          payeeCheck = checkBalances({ contractBefore: cb, contractAfter: ca, payeeBefore: pb, payeeAfter: pa, amount: owed, netFee: d.netFee });
          if (!payeeCheck) break;
          await sleep(20000);
          ca = await bal(regAddr); pa = await bal(payee);
        }
        if (cb - ca !== owed) why = `registry eth_getBalance moved by ${ca - cb}, expected -${owed}`;
      }
      const ok = d.ok && cb - ca === owed;
      const r = { ...rec, ok, why, status: tx?.statusName ?? "UNKNOWN", registry_before: cb.toString(), registry_after: ca.toString(),
        payee_before: pb.toString(), payee_after: pa.toString(), net_fee: d.netFee?.toString() ?? null,
        payee_delta_matches: d.ok && !payeeCheck, payee_note: payeeCheck };
      log(`   ${ok ? "DELIVERED" : "NOT DELIVERED"} ${owed} to ${payee}: registry ${cb} -> ${ca}, payee ${pb} -> ${pa}` +
        ` (net fee ${r.net_fee})${why ? " " + why : ""}${payeeCheck ? " payee: " + payeeCheck : ""}`);
      return r;
    },
  };
}
