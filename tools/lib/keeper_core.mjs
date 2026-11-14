// The keeper's logic, with the registry, the chains and the state store
// injected so the offline tests (test/keeper.test.mjs) drive it through
// outages, crashes, half-final transactions, malformed and disagreeing pages
// and hundreds of pairs.
//
// One run, for one registry:
//   1. RESUME every action whose transaction hash is stored and not finished:
//      poll that hash; never submit a second transaction for an action whose
//      last one is not terminal, unless it has had no final status for 6 h.
//   2. PAIRS: walk every page of get_pairs from the persisted cursor. A page
//      counts only when BOTH read endpoints returned it identically and its
//      pair ids are exactly offset+1.. in order; a failed page stops the walk
//      (the rest is listed next run) and is recorded.
//   3. PLAN per pair, from contract state only:
//        open check OPEN/CONTESTED: RULE if the round's reading exists, EXPIRE
//          past the round's read deadline, else READ (a PENDING read is retried
//          as a new action keyed by the pending count, inside the fixed window)
//        open check PROVISIONAL past its window: FINALIZE
//        no open check, monitor interval passed: MONITOR at freshly pinned
//          finalized blocks (two RPCs per chain), unless no chain has moved
//        latest ruling lists unlisted destinations (coverage GAP): DISCOVER
//          each one (the bridge's own config names the token), AUTH it, then
//          ADD it to the pair; destinations on chains BackedBy cannot read are
//          recorded as unmatched (the site shows them), never dropped.
//   4. ACT, oldest first, up to maxActions: re-verify first (done by anyone ->
//      DONE without a transaction), else submit and checkpoint the hash.
//   5. SETTLE: poll this run's transactions within settleMs.
//   Steps 2-5 repeat up to `rounds` times, so a pair goes monitor -> read ->
//   rule in one run when the network is quick.
// An action is DONE only when its transaction is FINALIZED, executed
// successfully, and a read of contract state shows its effect. Everything not
// finished is listed in state.unprocessed with the reason; nothing is skipped
// silently. FAILED actions are queued again FAILED_RETRY_S later while the
// state still calls for them.
export const VERSION = 2;
export const MAX_ATTEMPTS = 6;
export const PAGE = 50;
export const STALE_S = 6 * 3600;
export const FAILED_RETRY_S = 6 * 3600;
const TERMINAL_BAD = ["UNDETERMINED", "CANCELED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT"];
const LIVE = ["SUBMITTED", "ACCEPTED", "FINAL_UNVERIFIED"];
export const backoffS = (attempts) => Math.min(60 * 2 ** Math.max(attempts - 1, 0), 6 * 3600);

export function emptyState() {
  return { version: VERSION, cursor: 0, pairs: {}, actions: {}, unmatched: {}, runs: [], unprocessed: [], last_run: null };
}

/**
 * reg: { now(), endpoints: n, page(endpoint, offset, limit) -> {total, pairs}, getPair(pid), getCheck(cid),
 *        getReading(cid, rnd) -> {found, pending}, getAuth(id), config: {monitor_interval_s},
 *        submit(kind, args) -> hash, getTx(hash) -> {statusName, ok, reason, returned} | null, sleep?(ms) }
 * chain: { pins(pair) -> {chain: block} (throws when two RPCs do not answer), discover(pair, item) -> {kind, l1, l2} | {unmatched} }
 * store: { load() -> state, save(state, why) }
 */
export async function runKeeper({ reg, chain, store, log = () => {}, maxActions = 25, settleMs = 0, rounds = 3 }) {
  const state = (await store.load()) ?? emptyState();
  state.actions ??= {}; state.pairs ??= {}; state.unmatched ??= {};
  const run = { started_at: reg.now(), finished_at: null, resumed: 0, pairs: 0, pages: 0, pages_failed: 0, pins_failed: 0,
    queued: 0, requeued: 0, submitted: 0, done: 0, already: 0, pending: 0, retry: 0, failed: 0, unmatched: 0, errors: [] };
  const unprocessed = new Map();
  const note = (key, why) => unprocessed.set(key, { key, why });
  const save = (why) => store.save(state, why);
  const now = () => reg.now();

  // --- effects: what contract state shows when an action has happened ---------
  async function verify(a) {
    if (a.kind === "MONITOR") {
      const p = await reg.getPair(a.pair_id);
      if (!p?.found) return { gone: true };
      if ((p.checks?.length ?? 0) > a.before.n_checks) return { done: true, result: "check " + p.checks[p.checks.length - 1] };
      return { done: false, still: !p.open_check };
    }
    if (a.kind === "READ") {
      const c = await reg.getCheck(a.check_id);
      if (!c?.found) return { gone: true };
      const r = await reg.getReading(a.check_id, a.round);
      if (r?.found) return { done: true, result: "READ" };
      if ((r?.pending ?? 0) > a.before.pending) return { done: true, result: "PENDING" };
      const want = a.round === 1 ? "OPEN" : "CONTESTED";
      if (c.status !== want) return { done: true, result: "SUPERSEDED " + c.status };
      return { done: false, still: true };
    }
    if (a.kind === "RULE" || a.kind === "EXPIRE") {
      const c = await reg.getCheck(a.check_id);
      if (!c?.found) return { gone: true };
      if (c.status !== a.before.status || c.round !== a.before.round) return { done: true, result: `${c.status} ${c.verdict || c.verdict1 || ""}`.trim() };
      return { done: false, still: true };
    }
    if (a.kind === "FINALIZE") {
      const c = await reg.getCheck(a.check_id);
      if (!c?.found) return { gone: true };
      if (c.status !== "PROVISIONAL") return { done: true, result: `${c.status} ${c.verdict || ""}`.trim() };
      return { done: false, still: true };
    }
    if (a.kind === "AUTH") {
      if (!a.auth_id) return { done: false, still: true };
      const x = await reg.getAuth(a.auth_id);
      if (x?.found && x.kind === a.args[0] && x.source_token === a.args[1]) return { done: true, result: "auth " + a.auth_id };
      return { done: false, still: true };
    }
    if (a.kind === "ADD") {
      const p = await reg.getPair(a.pair_id);
      if (!p?.found) return { gone: true };
      const listed = (p.vaults ?? []).some((v) => (v.remotes ?? []).includes(a.remote)) || (p.dests ?? []).some((d) => d.remote === a.remote);
      return listed ? { done: true, result: "listed " + a.remote } : { done: false, still: true };
    }
    return { gone: true };
  }

  function queue(key, kind, fields) {
    const have = state.actions[key];
    if (have) return have;
    const a = { key, kind, status: "QUEUED", attempts: 0, first_seen_at: now(), tx: null, ...fields };
    state.actions[key] = a;
    run.queued++;
    return a;
  }

  async function conclude(a, tx) {
    let v;
    try { v = await verify(a); } catch (e) {
      a.last_error = "verifying read failed: " + String(e.message).slice(0, 120);
      run.pending++; note(a.key, `${a.tx} ${tx?.statusName ?? "?"}; verifying read failed, checked next run`);
      return;
    }
    if (a.kind === "AUTH" && tx?.statusName === "FINALIZED" && tx.ok && !a.auth_id) {
      a.auth_id = Number(tx.returned?.auth_id ?? 0) || 0;
      if (a.auth_id) v = await verify(a);
    }
    const final = tx?.statusName === "FINALIZED" && tx.ok;
    if (v.done && final) { a.status = "DONE"; a.verified_at = now(); a.result = v.result; run.done++; log(`DONE ${a.key} ${a.tx} -> ${a.result}`); return; }
    if (v.done && !LIVE.includes(a.status)) { a.status = "DONE"; a.done_by_other = true; a.result = v.result; run.done++; return; }
    if (v.done) {
      if (tx && tx.statusName !== "FINALIZED" && !TERMINAL_BAD.includes(tx.statusName) && !String(tx.statusName).startsWith("STALE")) {
        a.status = "ACCEPTED"; run.pending++; note(a.key, `effect visible but ${a.tx} is ${tx.statusName}; waiting for FINALIZED`); return;
      }
      a.status = "DONE"; a.verified_at = now(); a.result = v.result; a.done_by_other = !(final); run.done++;
      log(`DONE ${a.key} (state shows it; tx ${a.tx ?? "none"} ${tx?.statusName ?? ""})`); return;
    }
    if (final) { a.status = "FINAL_UNVERIFIED"; run.pending++; note(a.key, "finalized, waiting for contract state to show it"); return; }
    a.attempts++;
    a.last_error = `tx ${a.tx} ${tx?.statusName ?? "not found"}${tx && !tx.ok && tx.reason ? " (reverted: " + String(tx.reason).slice(0, 140) + ")" : ""}`;
    a.tx = null;
    if (a.kind === "AUTH" && /NOT_AUTHENTICATED/.test(String(tx?.reason ?? ""))) {
      a.status = "FAILED"; a.failed_at = now(); a.permanent = true; run.failed++;
      (state.unmatched[a.pair_id] ??= {})[a.remote] = { remote: a.remote, why: "bridge config does not prove it: " + String(tx.reason).slice(0, 120), at: now() };
      note(a.key, a.last_error); return;
    }
    if (a.attempts >= MAX_ATTEMPTS) { a.status = "FAILED"; a.failed_at = now(); run.failed++; note(a.key, `gave up after ${a.attempts} attempts: ${a.last_error}`); }
    else { a.status = "RETRY"; a.next_try_at = now() + backoffS(a.attempts); run.retry++; note(a.key, `retry ${a.attempts} after ${a.next_try_at}: ${a.last_error}`); }
  }

  // 0. FAILED actions come back after the cool-down while state still calls for them (act re-verifies first)
  for (const a of Object.values(state.actions)) {
    if (a.status !== "FAILED" || a.permanent) continue;
    if (now() - (a.failed_at ?? 0) < FAILED_RETRY_S) continue;
    a.status = "RETRY"; a.attempts = 0; a.next_try_at = now(); a.requeued = (a.requeued ?? 0) + 1; run.requeued++;
  }

  // 1. resume
  async function resume() {
    for (const a of Object.values(state.actions)) {
      if (!LIVE.includes(a.status)) continue;
      run.resumed++;
      if (a.status === "FINAL_UNVERIFIED") { await conclude(a, { statusName: "FINALIZED", ok: true, returned: a.returned }); await save("verify " + a.key); continue; }
      let tx = null;
      try { tx = await reg.getTx(a.tx); } catch (e) { run.pending++; note(a.key, "could not poll " + a.tx + ": " + String(e.message).slice(0, 80)); continue; }
      if (tx?.returned) a.returned = tx.returned;
      if (tx && (tx.statusName === "FINALIZED" || TERMINAL_BAD.includes(tx.statusName))) { await conclude(a, tx); await save("resolved " + a.key); continue; }
      if (now() - a.submitted_at > STALE_S) { await conclude(a, { statusName: "STALE_" + (tx?.statusName ?? "MISSING"), ok: false }); await save("stale " + a.key); continue; }
      a.status = tx?.statusName === "ACCEPTED" ? "ACCEPTED" : "SUBMITTED";
      run.pending++; note(a.key, `waiting for ${a.tx} (${tx?.statusName ?? "not visible yet"})`);
    }
  }
  await resume();

  // 2. pairs: every page, both endpoints, cursor persisted
  async function listPairs() {
    const pairs = [];
    let off = 0;
    let complete = true;
    for (;;) {
      let pages = [];
      try {
        for (let e = 0; e < (reg.endpoints ?? 1); e++) pages.push(await reg.page(e, off, PAGE));
      } catch (err) {
        run.pages_failed++; complete = false; run.errors.push("page " + off + ": " + String(err.message).slice(0, 100));
        note("pairs:" + off, "pair page at offset " + off + " unreadable; the rest is listed next run"); break;
      }
      const same = pages.every((p) => JSON.stringify(p) === JSON.stringify(pages[0]));
      const items = pages[0]?.pairs;
      if (!same) { run.pages_failed++; complete = false; note("pairs:" + off, "the read endpoints returned different pages at offset " + off); break; }
      if (!Array.isArray(items) || items.some((p, i) => p?.pair_id !== off + i + 1)) {
        run.pages_failed++; complete = false; note("pairs:" + off, "pair page at offset " + off + " malformed"); break;
      }
      run.pages++;
      pairs.push(...items);
      state.cursor = off + items.length;
      if (items.length < PAGE || off + items.length >= (pages[0].total ?? 0)) break;
      off += items.length;
    }
    // an open check's reading (or PENDING attempts) lives on ChainReader: read it for the plan
    for (const p of pairs) {
      const c = p.open;
      if (!p.open_check || !c || (c.status !== "OPEN" && c.status !== "CONTESTED")) continue;
      try { c.reading = await reg.getReading(c.check_id, c.status === "OPEN" ? 1 : 2); } catch (e) {
        c.reading = null; note(`reading:${c.check_id}`, "reading unreadable: " + String(e.message).slice(0, 80));
        p.open = null;
      }
    }
    state.pairs_listed_complete = complete;
    state.pairs_total = pairs.length;
    run.pairs = pairs.length;
    await save("pairs listed");
    return pairs;
  }

  function plan(pairs) {
    const t = now();
    for (const p of pairs) {
      const ps = (state.pairs[p.pair_id] ??= {});
      Object.assign(ps, { label: p.label, open_check: p.open_check, latest_check: p.latest_check, last_monitor_at: p.last_monitor_at });
      const c = p.open;
      if (p.open_check && c) {
        if (c.status === "OPEN" || c.status === "CONTESTED") {
          const rnd = c.status === "OPEN" ? 1 : 2;
          const deadline = rnd === 1 ? c.read_deadline : c.contest_read_deadline;
          const r = c.reading ?? null;
          if (r?.found) queue(`rule:${c.check_id}:${rnd}`, "RULE", { pair_id: p.pair_id, check_id: c.check_id, before: { status: c.status, round: c.round } });
          else if (t > deadline) queue(`expire:${c.check_id}:${rnd}`, "EXPIRE", { pair_id: p.pair_id, check_id: c.check_id, before: { status: c.status, round: c.round } });
          else {
            const pend = r?.pending ?? 0;
            queue(`read:${c.check_id}:${rnd}:${pend}`, "READ", { pair_id: p.pair_id, check_id: c.check_id, round: rnd, before: { pending: pend } });
            if (pend > 0) note(`pair:${p.pair_id}`, `check ${c.check_id} round ${rnd}: ${pend} PENDING reads; retried until ${deadline}`);
          }
        } else if (c.status === "PROVISIONAL") {
          if (t >= c.contest_deadline) queue(`finalize:${c.check_id}`, "FINALIZE", { pair_id: p.pair_id, check_id: c.check_id });
          else ps.waiting = `check ${c.check_id} contestable until ${c.contest_deadline}`;
        }
      } else if (!p.open_check && (!p.last_monitor_at || t >= p.last_monitor_at + (reg.config?.monitor_interval_s ?? 3600))) {
        ps.monitor_due = true;
      }
      // discovery from the latest ruling's coverage
      const un = p.latest?.ruling1?.coverage?.unlisted ?? [];
      for (const item of un) {
        const k = `${p.pair_id}:${item.id}`;
        if (state.actions["add:" + k]?.status === "DONE" || state.unmatched[p.pair_id]?.[item.id]) continue;
        ps.discover = [...new Set([...(ps.discover ?? []), item.id])];
      }
    }
  }

  async function monitorPlan(p, ps) {
    const key = `monitor:${p.pair_id}:${p.checks?.length ?? 0}`;
    if (state.actions[key]) return;
    let blocks;
    try { blocks = await chain.pins(p); } catch (e) {
      run.pins_failed++; note(`pins:${p.pair_id}`, "could not pin finalized blocks from two RPCs: " + String(e.message).slice(0, 80)); return;
    }
    const last = p.latest?.blocks;
    if (last && JSON.stringify(Object.entries(last).sort()) === JSON.stringify(Object.entries(blocks).sort())) {
      ps.waiting = "no chain has a new finalized block since the latest ruling"; return;
    }
    queue(key, "MONITOR", { pair_id: p.pair_id, args: [p.pair_id, JSON.stringify(blocks)], before: { n_checks: p.checks?.length ?? 0 } });
  }

  async function prepare(pairs) {
    for (const p of pairs) {
      const ps = state.pairs[p.pair_id];
      if (ps?.monitor_due) {
        delete ps.monitor_due;
        await monitorPlan(p, ps);
      }
      for (const id of ps?.discover ?? []) {
        const k = `${p.pair_id}:${id}`;
        const add = state.actions["add:" + k];
        if (add) continue;
        const au = state.actions["auth:" + k];
        if (au?.status === "DONE" && au.auth_id) {
          queue("add:" + k, "ADD", { pair_id: p.pair_id, remote: id, args: [p.pair_id, au.auth_id] });
          continue;
        }
        if (au) continue;
        let d;
        try { d = await chain.discover(p, id); } catch (e) { note("discover:" + k, "bridge config unreadable: " + String(e.message).slice(0, 80)); continue; }
        if (d?.unmatched) {
          (state.unmatched[p.pair_id] ??= {})[id] = { remote: id, why: d.unmatched, at: now(), ...(d.token ? { token: d.token } : {}) };
          run.unmatched++; continue;
        }
        queue("auth:" + k, "AUTH", { pair_id: p.pair_id, remote: id, args: [d.kind, d.l1, d.l2] });
      }
      if (ps) delete ps.discover;
    }
    await save("planned");
  }

  const ARGS = (a) => {
    if (a.kind === "MONITOR" || a.kind === "AUTH" || a.kind === "ADD") return a.args;
    if (a.kind === "READ") return [a.check_id, a.round];
    return [a.check_id];
  };
  let acted = 0;
  async function act() {
    const q = Object.values(state.actions).filter((a) => a.status === "QUEUED" || (a.status === "RETRY" && now() >= (a.next_try_at ?? 0)))
      .sort((x, y) => x.first_seen_at - y.first_seen_at || (x.key < y.key ? -1 : 1));
    for (const a of q) {
      if (acted >= maxActions) { note(a.key, "queued; this run reached its action limit"); continue; }
      let v;
      try { v = await verify(a); } catch (e) { note(a.key, "pre-read failed: " + String(e.message).slice(0, 80)); continue; }
      if (v.gone) { a.status = "FAILED"; a.permanent = true; a.last_error = "no such pair or check"; run.failed++; note(a.key, a.last_error); continue; }
      if (v.done) { a.status = "DONE"; a.result = v.result; a.done_by_other = !(a.tx_history?.length); a.verified_at = now(); run.already++; run.done++; await save("already " + a.key); continue; }
      acted++;
      try { a.tx = await reg.submit(a.kind, ARGS(a)); } catch (e) {
        a.attempts++; a.last_error = "submit failed: " + String(e.message).slice(0, 160);
        a.status = a.attempts >= MAX_ATTEMPTS ? "FAILED" : "RETRY"; a.next_try_at = now() + backoffS(a.attempts);
        if (a.status === "FAILED") { a.failed_at = now(); run.failed++; } else run.retry++;
        note(a.key, a.last_error); await save("submit failed " + a.key); continue;
      }
      a.status = "SUBMITTED"; a.submitted_at = now(); (a.tx_history ??= []).push(a.tx);
      run.submitted++;
      await save("submitted " + a.key);
    }
  }

  async function settle() {
    const t0 = Date.now();
    for (;;) {
      const open = Object.values(state.actions).filter((a) => ["SUBMITTED", "ACCEPTED"].includes(a.status) && a.tx);
      if (!open.length) break;
      for (const a of open) {
        let tx = null;
        try { tx = await reg.getTx(a.tx); } catch { continue; }
        if (tx?.returned) a.returned = tx.returned;
        if (tx && (tx.statusName === "FINALIZED" || TERMINAL_BAD.includes(tx.statusName))) { unprocessed.delete(a.key); await conclude(a, tx); await save("settled " + a.key); }
      }
      if (Date.now() - t0 >= settleMs || !reg.sleep) break;
      await reg.sleep(15_000);
    }
    for (const a of Object.values(state.actions)) if (["SUBMITTED", "ACCEPTED"].includes(a.status)) note(a.key, `submitted ${a.tx}; checked next run`);
  }

  for (let r = 0; r < rounds; r++) {
    const pairs = await listPairs();
    plan(pairs);
    await prepare(pairs);
    const before = run.submitted + run.already;
    await act();
    await settle();
    if (run.submitted + run.already === before) break;
  }

  for (const a of Object.values(state.actions)) if (a.status === "FAILED") note(a.key, "FAILED: " + (a.last_error ?? "") + (a.permanent ? "" : `; queued again after ${(a.failed_at ?? 0) + FAILED_RETRY_S}`));
  for (const [pid, m] of Object.entries(state.unmatched)) for (const u of Object.values(m)) note(`unmatched:${pid}:${u.remote}`, "unmatched destination: " + u.why);
  run.finished_at = now();
  state.unprocessed = [...unprocessed.values()];
  state.last_run = run;
  state.runs = [...(state.runs ?? []), { ...run, errors: run.errors.slice(0, 5) }].slice(-48);
  state.totals = totals(state);
  await save("run finished");
  return { run, state };
}

export function totals(state) {
  const t = { actions: 0, done: 0, queued: 0, pending: 0, retry: 0, failed: 0, by_kind: {} };
  for (const a of Object.values(state.actions)) {
    t.actions++;
    t.by_kind[a.kind] = (t.by_kind[a.kind] ?? 0) + 1;
    if (a.status === "DONE") t.done++;
    else if (a.status === "QUEUED") t.queued++;
    else if (a.status === "RETRY") t.retry++;
    else if (a.status === "FAILED") t.failed++;
    else t.pending++;
  }
  return t;
}
