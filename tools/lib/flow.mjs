// The on-chain steps every script uses (seeds, demo, patrol): authenticate,
// register, bond, challenge, monitor, read, rule, contest, finalize, expire.
// Each write goes through test/harness.mjs (fee estimate, settle-aware
// outcome); each result is confirmed from contract STATE, never from the
// return value alone.
import { readFileSync } from "node:fs";
import { connect, returnedJson, sleep } from "../../test/harness.mjs";
import { pinBlocks } from "./pin.mjs";

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

  return {
    regAddr, rv, cv, send,
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
  };
}
