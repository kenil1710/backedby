// The keeper, offline: tools/lib/keeper_core.mjs against a model of the
// registry and ChainReader that applies each transaction's effect when it
// settles, with knobs for every failure the network has shown.
//   node --test test/keeper.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { runKeeper, emptyState, PAGE, STALE_S, FAILED_RETRY_S, MAX_ATTEMPTS } from "../tools/lib/keeper_core.mjs";

const WINDOW = 90, READ_T = 300, MON = 30;

function world({ pairs = 1, unlisted = [] } = {}) {
  const W = {
    t: 1_800_000_000, n_tx: 0, txs: {}, pairs: [], checks: {}, readings: {}, auths: {}, n_auth: 0,
    down: false, pagesDown: false, endpointsDiffer: false, malformed: false, readerOutage: false,
    revertNext: 0, neverFinal: false, acceptedOnly: false, noEffect: false, submitted: [], pinsFail: false, blocks: 100,
    authRefuse: new Set(),
  };
  for (let i = 1; i <= pairs; i++) {
    W.pairs.push({ pair_id: i, label: "pair " + i, checks: [], open_check: 0, latest_check: 0, last_monitor_at: 0,
      vaults: [{ vault: "0xv" + i, family: "LZ", remotes: ["lz:30110"] }], dests: [{ chain: "arbitrum", token: "0xd" + i, remote: "lz:30110" }],
      unlisted: i === 1 ? unlisted : [] });
  }
  const view = (c) => (c ? JSON.parse(JSON.stringify({ found: true, ...c })) : { found: false });
  const pv = (p) => {
    const latest = p.latest_check ? W.checks[p.latest_check] : null;
    return JSON.parse(JSON.stringify({ found: true, ...p, open: p.open_check ? W.checks[p.open_check] : null,
      latest: latest ? { ...latest, ruling1: { ...latest.ruling1, coverage: { state: p.unlisted.length ? "GAP" : "COMPLETE", unlisted: p.unlisted.map((id) => ({ vault: "0xv1", id })) } } } : null }));
  };
  function effect(kind, args, hash) {
    const p = (id) => W.pairs[id - 1];
    if (kind === "MONITOR") {
      const pr = p(args[0]);
      if (pr.open_check) return "REVERT CHECK_IS_OPEN";
      const cid = Object.keys(W.checks).length + 1;
      W.checks[cid] = { check_id: cid, pair_id: pr.pair_id, status: "OPEN", round: 1, read_deadline: W.t + READ_T, contest_deadline: 0,
        contest_read_deadline: 0, verdict1: "", verdict: "", blocks: JSON.parse(args[1]), ruling1: null };
      pr.checks.push(cid); pr.open_check = cid; pr.last_monitor_at = W.t;
      return { ok: true, check_id: cid };
    }
    if (kind === "READ") {
      const [cid, rnd] = args;
      const c = W.checks[cid];
      const key = cid + "|" + rnd;
      if (W.t > (rnd === 1 ? c.read_deadline : c.contest_read_deadline)) return "REVERT READ_WINDOW_CLOSED";
      if (W.readings[key]?.found) return "REVERT ALREADY_READ";
      W.readings[key] ??= { found: false, pending: 0 };
      if (W.readerOutage) { W.readings[key].pending++; return { status: "PENDING" }; }
      W.readings[key].found = true;
      return { status: "OK" };
    }
    if (kind === "RULE") {
      const c = W.checks[args[0]];
      if (!W.readings[c.check_id + "|" + c.round]?.found) return "REVERT NOT_READ_YET";
      c.status = "PROVISIONAL"; c.verdict1 = "BACKED"; c.contest_deadline = W.t + WINDOW; c.ruling1 = { ratio_bps: 10010, reason: "LOCKED_COVERS_SUPPLY" };
      return { ok: true };
    }
    if (kind === "FINALIZE") {
      const c = W.checks[args[0]];
      if (c.status !== "PROVISIONAL" || W.t < c.contest_deadline) return "REVERT NOT_FINALIZABLE";
      c.status = "FINAL"; c.verdict = c.verdict1;
      const pr = p(c.pair_id); pr.open_check = 0; pr.latest_check = c.check_id;
      return { ok: true };
    }
    if (kind === "EXPIRE") {
      const c = W.checks[args[0]];
      if (W.t < c.read_deadline) return "REVERT READ_DEADLINE";
      c.status = "INCONCLUSIVE"; c.verdict = "INCONCLUSIVE"; p(c.pair_id).open_check = 0;
      return { ok: true };
    }
    if (kind === "AUTH") {
      if (W.authRefuse.has(args[2])) return "REVERT REFUSED: NOT_AUTHENTICATED: ADAPTER_PEER_IS_NOT_THE_DESTINATION_OFT";
      const id = ++W.n_auth;
      W.auths[id] = { found: true, auth_id: id, kind: args[0], source_token: args[1], dest_token: args[2] };
      return { auth_id: id };
    }
    if (kind === "ADD") {
      const pr = p(args[0]);
      const a = W.auths[args[1]];
      const remote = "lz:" + ({ oft_base: 30184, oft_hyperevm: 30367 }[a.kind] ?? 0);
      pr.vaults[0].remotes.push(remote);
      pr.unlisted = pr.unlisted.filter((x) => x !== remote);
      return { ok: true };
    }
    return "REVERT ?";
  }
  const reg = {
    now: () => W.t,
    endpoints: 2,
    config: { monitor_interval_s: MON },
    async page(e, off, lim) {
      if (W.pagesDown) throw new Error("fetch failed");
      const items = W.pairs.slice(off, off + lim).map(pv);
      if (W.malformed && off > 0) items.reverse();
      if (W.endpointsDiffer && e === 1 && items[0]) items[0].label = "other";
      return { total: W.pairs.length, pairs: items };
    },
    getPair: async (id) => (W.pairs[id - 1] ? pv(W.pairs[id - 1]) : { found: false }),
    getCheck: async (id) => view(W.checks[id]),
    getReading: async (cid, rnd) => W.readings[cid + "|" + rnd] ?? { found: false, pending: 0 },
    getAuth: async (id) => W.auths[id] ?? { found: false },
    async submit(kind, args) {
      if (W.down) throw new Error("fetch failed");
      const hash = "0x" + (++W.n_tx).toString(16).padStart(64, "0");
      W.txs[hash] = { kind, args, polls: 0, applied: null };
      W.submitted.push([kind, JSON.stringify(args)]);
      return hash;
    },
    async getTx(hash) {
      if (W.down) throw new Error("fetch failed");
      const tx = W.txs[hash];
      if (!tx) return null;
      tx.polls++;
      if (W.neverFinal) return { statusName: "PENDING", ok: false };
      if (tx.applied === null) {
        if (W.revertNext > 0) { W.revertNext--; tx.applied = "REVERT forced"; }
        else tx.applied = W.noEffect ? { ok: true } : effect(tx.kind, tx.args, hash);
      }
      const reverted = typeof tx.applied === "string";
      if (W.acceptedOnly) return { statusName: "ACCEPTED", ok: !reverted };
      return { statusName: "FINALIZED", ok: !reverted, reason: reverted ? tx.applied : "", returned: reverted ? null : tx.applied };
    },
  };
  const chain = {
    async pins(p) { if (W.pinsFail) throw new Error("one RPC down"); return { ethereum: W.blocks, arbitrum: W.blocks * 10 }; },
    async discover(p, id) {
      if (id === "lz:30500") return { unmatched: "eid 30500 is on a chain BackedBy has no two RPCs for" };
      if (id === "lz:30184") return { kind: "oft_base", l1: "0xusdt", l2: "0xbase-oft" };
      if (id === "lz:30367") return { kind: "oft_hyperevm", l1: "0xusdt", l2: "0xfake" };
      throw new Error("unknown");
    },
  };
  let saved = emptyState();
  const store = { saves: 0, async load() { return JSON.parse(JSON.stringify(saved)); }, async save(s) { saved = JSON.parse(JSON.stringify(s)); store.saves++; } };
  const k = (opts = {}) => runKeeper({ reg, chain, store, maxActions: 500, settleMs: 0, rounds: 4, ...opts });
  return { W, reg, chain, store, k, state: () => saved, setState: (s) => { saved = s; } };
}

const status = (w, key) => w.state().actions[key]?.status;

test("one run takes a pair from monitor to a PROVISIONAL ruling; a later run finalizes it", async () => {
  const w = world();
  const { run } = await w.k();
  assert.equal(w.W.checks[1].status, "PROVISIONAL");
  assert.equal(run.done, 3);
  assert.deepEqual(w.W.submitted.map((s) => s[0]), ["MONITOR", "READ", "RULE"]);
  w.W.t += WINDOW;
  await w.k();
  assert.equal(w.W.checks[1].status, "FINAL");
  assert.equal(status(w, "finalize:1"), "DONE");
});

test("more than 50 pairs: every page walked, the cursor persisted, every pair monitored", async () => {
  const w = world({ pairs: 130 });
  const { run } = await w.k({ rounds: 1 });
  assert.equal(run.pairs, 130);
  assert.equal(run.pages, Math.ceil(130 / PAGE));
  assert.equal(w.state().cursor, 130);
  assert.equal(w.W.submitted.filter((s) => s[0] === "MONITOR").length, 130);
});

test("pages are read from two endpoints and refused when they differ", async () => {
  const w = world({ pairs: 3 });
  w.W.endpointsDiffer = true;
  const { run, state } = await w.k();
  assert.equal(run.pages_failed, 1);
  assert.equal(w.W.submitted.length, 0);
  assert.ok(state.unprocessed.some((u) => /different pages/.test(u.why)));
});

test("a malformed page stops the walk and is recorded; earlier pages are still served", async () => {
  const w = world({ pairs: 60 });
  w.W.malformed = true;
  const { run, state } = await w.k({ rounds: 1 });
  assert.equal(run.pairs, 50);
  assert.ok(state.unprocessed.some((u) => u.key === "pairs:50"));
});

test("Studio outage: nothing is DONE, actions retry with backoff, and finish after it recovers", async () => {
  const w = world();
  w.W.down = true;
  const r1 = await w.k({ rounds: 1 });
  assert.equal(r1.run.done, 0);
  assert.equal(status(w, "monitor:1:0"), "RETRY");
  w.W.down = false;
  w.W.t += 60;
  await w.k();
  assert.equal(status(w, "monitor:1:0"), "DONE");
  assert.equal(w.W.checks[1].status, "PROVISIONAL");
});

test("a page outage lists nothing and plans nothing", async () => {
  const w = world({ pairs: 5 });
  w.W.pagesDown = true;
  const { run } = await w.k();
  assert.equal((run.pages_failed, w.W.submitted.length), 0);
  assert.equal(run.pages_failed, 1);
});

test("idempotent: a second run right after submits nothing new", async () => {
  const w = world({ pairs: 4 });
  await w.k();
  const n = w.W.submitted.length;
  await w.k();
  assert.equal(w.W.submitted.length, n);
});

test("an action someone else already did is DONE without a transaction", async () => {
  const w = world();
  await w.k({ rounds: 1, maxActions: 0 });
  assert.equal(status(w, "monitor:1:0"), "QUEUED");
  // a stranger files the same monitoring check
  w.W.pairs[0].checks.push(1); w.W.pairs[0].open_check = 1;
  w.W.checks[1] = { check_id: 1, pair_id: 1, status: "OPEN", round: 1, read_deadline: w.W.t + READ_T, verdict1: "", verdict: "", blocks: {} };
  const { run } = await w.k({ rounds: 1 });
  assert.equal(status(w, "monitor:1:0"), "DONE");
  assert.equal(w.state().actions["monitor:1:0"].done_by_other, true);
  assert.equal(run.already >= 1, true);
});

test("resume from a stored hash: a crash after submitting never submits twice", async () => {
  const w = world();
  w.W.neverFinal = true;
  await w.k({ rounds: 1 });
  assert.equal(status(w, "monitor:1:0"), "SUBMITTED");
  const n = w.W.submitted.length;
  w.W.neverFinal = false;
  const { run } = await w.k({ rounds: 1 });
  assert.equal(run.resumed, 1);
  assert.equal(w.W.submitted.filter((s) => s[0] === "MONITOR").length, n);
  assert.equal(status(w, "monitor:1:0"), "DONE");
});

test("FINALIZED is required: an ACCEPTED transaction whose effect shows is not DONE", async () => {
  const w = world();
  w.W.acceptedOnly = true;
  await w.k({ rounds: 1 });
  assert.notEqual(status(w, "monitor:1:0"), "DONE");
  w.W.acceptedOnly = false;
  await w.k({ rounds: 1 });
  assert.equal(status(w, "monitor:1:0"), "DONE");
});

test("success is required: a reverted transaction is retried", async () => {
  const w = world();
  w.W.revertNext = 1;
  await w.k({ rounds: 1 });
  const a = w.state().actions["monitor:1:0"];
  assert.equal(a.status, "RETRY");
  assert.match(a.last_error, /reverted/);
});

test("state is verified: a finalized success without its effect is FINAL_UNVERIFIED, never DONE", async () => {
  const w = world();
  w.W.noEffect = true;
  await w.k({ rounds: 1 });
  assert.equal(status(w, "monitor:1:0"), "FINAL_UNVERIFIED");
  assert.ok(w.state().unprocessed.some((u) => u.key === "monitor:1:0"));
});

test("a stale transaction (no final status for 6 h) is retried", async () => {
  const w = world();
  w.W.neverFinal = true;
  await w.k({ rounds: 1 });
  w.W.t += STALE_S + 1;
  w.W.neverFinal = false;
  w.W.txs = {};
  await w.k({ rounds: 1 });
  assert.equal(w.state().actions["monitor:1:0"].attempts, 1);
});

test("PENDING reads are retried inside the window, then the check is expired", async () => {
  const w = world();
  w.W.readerOutage = true;
  await w.k({ rounds: 1 });
  await w.k({ rounds: 1 });
  assert.equal(w.W.readings["1|1"].pending, 1);
  assert.equal(status(w, "read:1:1:0"), "DONE");
  await w.k({ rounds: 1 });
  assert.equal(w.W.readings["1|1"].pending, 2);
  w.W.t += READ_T + 1;
  await w.k({ rounds: 1 });
  assert.equal(w.W.checks[1].status, "INCONCLUSIVE");
  assert.equal(status(w, "expire:1:1"), "DONE");
});

test("discovery: an unlisted destination on a readable chain is authenticated and added", async () => {
  const w = world({ unlisted: ["lz:30184"] });
  await w.k();
  w.W.t += WINDOW;
  await w.k();
  assert.equal(status(w, "auth:1:lz:30184"), "DONE");
  assert.equal(status(w, "add:1:lz:30184"), "DONE");
  assert.ok(w.W.pairs[0].vaults[0].remotes.includes("lz:30184"));
});

test("discovery: an unlisted destination on an unreadable chain is recorded as unmatched, never dropped", async () => {
  const w = world({ unlisted: ["lz:30500"] });
  await w.k();
  w.W.t += WINDOW;
  const { state } = await w.k();
  assert.match(state.unmatched[1]["lz:30500"].why, /no two RPCs/);
  assert.ok(state.unprocessed.some((u) => u.key === "unmatched:1:lz:30500"));
});

test("discovery: a destination the bridge's config does not prove is unmatched with the reason, not retried", async () => {
  const w = world({ unlisted: ["lz:30367"] });
  w.W.authRefuse.add("0xfake");
  await w.k();
  w.W.t += WINDOW;
  await w.k();
  w.W.t += FAILED_RETRY_S + 1;
  const n = w.W.submitted.filter((s) => s[0] === "AUTH").length;
  const { state } = await w.k();
  assert.equal(w.W.submitted.filter((s) => s[0] === "AUTH").length, n);
  assert.match(state.unmatched[1]["lz:30367"].why, /NOT_AUTHENTICATED/);
});

test("backfill: a lost state file is rebuilt from contract state and every open check is advanced", async () => {
  const w = world({ pairs: 3 });
  await w.k();
  w.W.t += WINDOW;
  w.setState(emptyState());
  await w.k();
  for (const c of Object.values(w.W.checks)) assert.equal(c.status, "FINAL");
});

test("pins that two RPCs cannot give defer the monitor and say so", async () => {
  const w = world();
  w.W.pinsFail = true;
  const { run, state } = await w.k({ rounds: 1 });
  assert.equal(run.pins_failed, 1);
  assert.ok(state.unprocessed.some((u) => u.key === "pins:1"));
});

test("no new finalized block on any chain: no monitoring check is filed", async () => {
  const w = world();
  await w.k();
  w.W.t += WINDOW;
  await w.k();
  w.W.t += MON + 1;
  const n = w.W.submitted.length;
  const { state } = await w.k({ rounds: 1 });
  assert.equal(w.W.submitted.length, n);
  assert.match(state.pairs[1].waiting, /no chain has a new finalized block/);
});

test("the action limit leaves the rest queued and listed", async () => {
  const w = world({ pairs: 10 });
  const { state } = await w.k({ rounds: 1, maxActions: 3 });
  assert.equal(w.W.submitted.length, 3);
  assert.equal(state.unprocessed.filter((u) => /action limit/.test(u.why)).length, 7);
});

test("a failed action is queued again after the cool-down while state still calls for it", async () => {
  const w = world();
  w.W.down = true;
  for (let i = 0; i < MAX_ATTEMPTS + 1; i++) { w.W.t += 7 * 3600; await w.k({ rounds: 1 }); }
  assert.equal(w.state().actions["monitor:1:0"].requeued >= 1, true);
  w.W.down = false;
  w.W.t += FAILED_RETRY_S + 1;
  await w.k();
  assert.equal(status(w, "monitor:1:0"), "DONE");
});

test("every checkpoint is saved: one save per submitted action at least", async () => {
  const w = world({ pairs: 2 });
  await w.k();
  assert.ok(w.store.saves >= w.W.submitted.length);
});
