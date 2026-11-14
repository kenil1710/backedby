/**
 * Demo, part 2 (after test/demo_run.mjs; appended to docs/demo-run.log): CollateralGate's states on fresh
 * rulings. The demo gate's max age is 30 minutes, so each pair is checked, finalized after the 90 s window and
 * asked about at once: BACKED or BACKED_ALERT on complete pairs, COVERAGE_GAP on a vault backing unlisted
 * destinations, COVERAGE_OPEN on an OP Standard Bridge escrow, NOT_THIS_PAIR for another token, and an open
 * check left by an interrupted step driven to its end. Nothing here carries value.
 *   node test/demo_gate.mjs >> docs/demo-run.log
 */
import { actor, deployments } from "../tools/lib/flow.mjs";
import { connect, sleep } from "./harness.mjs";

const REG = "BackedByRegistryDemo";
const log = (m) => console.log(m);
const pt = actor({ role: "patrol", registry: REG, log });
const dep = deployments().contracts;
const gate = connect({ address: dep.CollateralGateDemo.address, role: "borrower" });
const step = (t) => log(`\n## ${t}  (${new Date().toISOString()})`);
const show = (c) => log(`   -> check ${c?.check_id}: ${c?.status} ${c?.verdict || c?.verdict1 || ""} ${c?.ruling1?.ratio_bps !== undefined ? "ratio_bps " + c.ruling1.ratio_bps : ""} ${c?.reason || ""} coverage ${c?.ruling1?.coverage?.state ?? "-"} alert ${c?.ruling1?.alert ?? "-"}`);
const waitUntil = async (t, why) => { const s = Math.max(0, t - Math.floor(Date.now() / 1000)) + 8; log(`   ... waiting ${s}s (${why})`); await sleep(s * 1000); };
const byLabel = async (prefix) => {
  for (let off = 0; ; off += 50) {
    const pg = await pt.rv("get_pairs", [off, 50]);
    const p = pg.pairs.find((x) => x.label.startsWith(prefix));
    if (p) return p;
    if (off + 50 >= pg.total) return null;
  }
};
const borrow = async (p, token, note) => {
  const o = await gate.send("borrow", [p.pair_id, p.source_token, p.dests[0].chain, token ?? p.dests[0].token, "1000", note]);
  log(`   borrow on pair ${p.pair_id} (${note}): tx ${o.hash} -> ${JSON.stringify(o.returned)}`);
};

log(`\n# Demo, part 2 ${new Date().toISOString()} on ${dep[REG].address}`);
step("18. A check left OPEN by an interrupted step is driven to its end by anyone: read (PENDING is retried inside its window), rule, or expire");
for (let id = 1; ; id++) {
  const c = await pt.check(id);
  if (!c?.status) break;
  if (c.status !== "OPEN" && c.status !== "CONTESTED") continue;
  const rnd = c.status === "OPEN" ? 1 : 2;
  const dl = rnd === 1 ? c.read_deadline : c.contest_read_deadline;
  const r = await pt.cv("get_reading", [pt.regAddr, id, rnd]);
  log(`   check ${id}: ${c.status}, reading ${r.found ? "recorded" : `not recorded (${r.pending ?? 0} PENDING attempts)`}, read window until ${new Date(dl * 1000).toISOString()}`);
  if (r.found) show(await pt.rule(id));
  else if (Date.now() / 1000 > dl) show(await pt.expire(id));
  else { await pt.read(id, rnd); show(await pt.rule(id)); }
  const k = await pt.check(id);
  if (k.status === "PROVISIONAL") { await waitUntil(k.contest_deadline, `window of check ${id}`); show(await pt.finalize(id)); }
}

step("19. Fresh rulings, finalized, and the gate asked at once (its max age is 30 minutes)");
const pairs = [];
for (const [prefix, why] of [["LINK on Arbitrum", "complete mapping"], ["USDC through Wormhole", "ledger"], ["GHO through CCIP", "CCIP pool with unlisted chains"],
  ["USDC.e on OP Mainnet", "OP Standard Bridge escrow"], ["USDT on Polygon", "PoS predicate and USDT0 adapter"]]) {
  const p = await byLabel(prefix);
  if (!p) { log(`   no pair ${prefix}`); continue; }
  const r = (await pt.fileReadRule(`monitor ${prefix}`, async () => pt.monitor(p.pair_id, (await pt.pins(p.pair_id, 0)).blocks))).check;
  log(`   ${prefix} (${why}):`);
  show(r);
  if (r?.status === "PROVISIONAL") pairs.push([p, r]);
}
for (const [p, r] of pairs) { await waitUntil(r.contest_deadline, `window of check ${r.check_id}`); show(await pt.finalize(r.check_id)); }
for (const [p] of pairs) await borrow(await pt.rv("get_pair", [p.pair_id]), null, p.label);
{
  const p = pairs[0]?.[0];
  if (p) await borrow(p, "0x7f5c764cbc14f9669b88837ca1490cca17c31607", `${p.label}, naming another token`);
}
log(`   attempts: ${JSON.stringify(await gate.view("get_attempts", [0, 8]))}`);
const held = await gate.read.getBalance({ address: dep[REG].address });
const L = await pt.rv("get_ledger");
log(`\nRESULT demo part 2: gate states shown above; registry eth_getBalance ${held}, ledger held_now ${L.held_now}, invariant ${L.invariant_holds}`);
