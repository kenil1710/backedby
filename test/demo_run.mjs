/**
 * Every path on the DEMO registry, on chain, with real chain data, then
 * drained to 0. Each step prints its transaction and the contract state it
 * produced; the run is appended to docs/demo-run.log.
 *
 *   STUDIO_RPC=https://backedby-ledger.vercel.app/api/rpc node test/demo_run.mjs >> docs/demo-run.log
 *
 * Paths: register (4 bridges), fake pair refused, add destination (and its
 * refusal), bond x2, challenge BACKED (+ contest upheld), challenge
 * UNDER_BACKED (slash + bounty), challenge INCONCLUSIVE (blocks before the
 * bond), monitoring INCONCLUSIVE (pins break the gap rule), timeout (unread
 * check expires), monitoring FINAL, CollateralGate allow and refuse,
 * unbond + withdraw, claims, ledger at 0.
 */
import { actor, deployments } from "../tools/lib/flow.mjs";
import { L1 } from "../tools/lib/bridges.mjs";
import { connect, sleep } from "./harness.mjs";

const REG = "BackedByRegistryDemo";
const log = (m) => console.log(m);
const as = (role) => actor({ role, registry: REG, log });
const seeder = as("seeder"), op = as("operator"), ch = as("challenger"), ct = as("contester"), pt = as("patrol");
const dep = deployments().contracts;
const gate = connect({ address: dep.CollateralGateDemo.address, role: "borrower" });
const cfg = await seeder.rv("get_config");
const MIN_BOND = BigInt(cfg.min_bond), MIN_STAKE = BigInt(cfg.min_stake);
const step = (t) => log(`\n## ${t}  (${new Date().toISOString()})`);
const show = (c) => log(`   -> check ${c.check_id}: ${c.status} ${c.verdict || c.verdict1 || ""} ${c.ruling1 ? "ratio_bps " + c.ruling1.ratio_bps : ""} ${c.reason || ""} ${c.how || ""}`);
const waitUntil = async (t, why) => { const s = Math.max(0, t - Math.floor(Date.now() / 1000)) + 8; log(`   ... waiting ${s}s (${why})`); await sleep(s * 1000); };

log(`\n# Demo run ${new Date().toISOString()} on ${dep[REG].address} (commit ${dep[REG].commit})`);
log(`config: window ${cfg.window_s}s, read timeout ${cfg.read_timeout_s}s, unbond delay ${cfg.unbond_delay_s}s, min bond ${cfg.min_bond}, min stake ${cfg.min_stake}`);

step("1. Register four real pairs (authenticated by each bridge's own mapping)");
const P = {};
for (const [key, kind, sym, l2, label] of [
  ["arb", "arbitrum", "LINK", "0xf97f4df75117a78c1a5a0dbb814af92458539fb4", "LINK on Arbitrum (demo)"],
  ["pol", "polygon", "USDT", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "USDT on Polygon (demo)"],
  ["nomad", "nomad", "USDC", "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9", "madUSDC on Moonbeam (demo)"],
  ["op", "optimism", "USDC", "0x7f5c764cbc14f9669b88837ca1490cca17c31607", "USDC.e on OP Mainnet (demo)"],
]) {
  const have = (await seeder.rv("get_pairs", [0, 50])).pairs.find((p) => p.label === label);
  if (have) { P[key] = have.pair_id; log(`   -> pair ${have.pair_id}: ${label} (registered in an earlier pass)`); continue; }
  let r = { pair_id: 0 };
  for (let i = 0; i < 4 && !r.pair_id; i++) {
    const au = await seeder.authenticate(kind, L1[sym], l2);
    if (au.auth_id) r = await seeder.register([au.auth_id], 0, label);
  }
  P[key] = r.pair_id;
  log(`   -> pair ${r.pair_id}: ${label}`);
}

step("2. A fake pair is refused: Circle's native USDC on OP passed off as the bridge's token");
await seeder.authenticate("optimism", L1.USDC, "0x0b2c639c533813f4aa9d7837caf62653d097ff85");

step("3. Anyone adds a destination the pair is missing (a second Standard Bridge USDC on OP), with the same proof");
const extra = "0x130c1dcc9fd997fa02f555dad54edaf553f2555a";
let ax = { auth_id: 0 };
for (let i = 0; i < 4 && !ax.auth_id; i++) ax = await ct.authenticate("optimism", L1.USDC, extra);
await ct.send("reg", "add_destination", [P.op, ax.auth_id]);
log(`   -> pair ${P.op} destinations: ${(await ct.rv("get_pair", [P.op])).dests.map((d) => d.token + "/" + d.decimals).join(", ")}`);
log("   adding the same destination again is refused:");
const ax2 = await ct.authenticate("optimism", L1.USDC, extra);
await ct.send("reg", "add_destination", [P.op, ax2.auth_id]);

step("4. The operator bonds two pairs");
const bA = await op.bond(P.arb, MIN_BOND);
const bB = await op.bond(P.pol, MIN_BOND);
log(`   -> bond ${bA.bond_id} on pair ${P.arb}, bond ${bB.bond_id} on pair ${P.pol}`);
const bondStart = Math.floor(Date.now() / 1000);

step("5. INCONCLUSIVE: a challenge pinned before the bond started is refunded");
{
  const pins = await ch.pins(P.arb, 90);          // these blocks are ~20 min old: before the bond
  const c = await ch.challenge(bA.bond_id, pins.blocks, MIN_STAKE);
  await pt.read(c.check_id);
  show(await pt.rule(c.check_id));
}

step("6. Waiting until finalized blocks exist after the bond started (Ethereum finality is ~15-20 min)");
for (;;) {
  const pins = await ch.pins(P.arb, 0);
  if (pins.detail.ethereum.timestamp >= bondStart + 30) break;
  log(`   ... finalized Ethereum block is at ${new Date(pins.detail.ethereum.timestamp * 1000).toISOString()}, bond started ${new Date(bondStart * 1000).toISOString()}`);
  await sleep(120_000);
}

step("7. Challenge -> BACKED, contested, re-read, upheld: the stakes go into the bond");
let cA;
{
  const pins = await ch.pins(P.arb, 0);
  const c = await ch.challenge(bA.bond_id, pins.blocks, MIN_STAKE);
  cA = c.check_id;
  await pt.read(cA);
  show(await pt.rule(cA));
  const k = await ct.contest(cA, MIN_STAKE);
  show(k.check);
  await pt.read(cA, 2);
  show(await pt.rule(cA));
  log(`   bond ${bA.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bA.bond_id]))}`);
}

step("8. Challenge -> UNDER_BACKED (Polygon USDT, live), window passes, finalize: bond slashed, bounty paid");
{
  const pins = await ch.pins(P.pol, 0);
  const c = await ch.challenge(bB.bond_id, pins.blocks, MIN_STAKE);
  await pt.read(c.check_id);
  const r = await pt.rule(c.check_id);
  show(r);
  await waitUntil(r.contest_deadline, "contest window");
  show(await pt.finalize(c.check_id));
  log(`   payouts ${JSON.stringify((await pt.check(c.check_id)).payouts)}`);
  log(`   bond ${bB.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bB.bond_id]))}`);
}

step("9. Monitoring INCONCLUSIVE: pins that break the 10-minute gap rule");
{
  const pins = await pt.pins(P.op, 0);
  const bad = { ...pins.blocks, optimism: pins.blocks.optimism - 400 };   // 800 s before the Ethereum block
  const c = await pt.monitor(P.op, bad);
  await pt.read(c.check_id);
  show(await pt.rule(c.check_id));
}

step("10. Timeout: a monitoring check nobody reads expires INCONCLUSIVE");
{
  const pins = await pt.pins(P.nomad, 0);
  const c = await pt.monitor(P.nomad, pins.blocks);
  const k = await pt.check(c.check_id);
  await waitUntil(k.read_deadline, "read deadline");
  show(await pt.expire(c.check_id));
}

step("11. Monitoring FINAL on three pairs (the gate needs final rulings)");
const finals = [];
for (const key of ["nomad", "op", "arb"]) {
  const pins = await pt.pins(P[key], key === "nomad" ? 0 : 30);
  const c = await pt.monitor(P[key], pins.blocks);
  await pt.read(c.check_id);
  const r = await pt.rule(c.check_id);
  show(r);
  finals.push([c.check_id, r.contest_deadline]);
}
for (const [cid, dl] of finals) { await waitUntil(dl, `window of check ${cid}`); show(await pt.finalize(cid)); }

step("12. CollateralGate: borrow allowed on a fresh BACKED pair, refused on the others");
for (const key of ["arb", "op", "pol", "nomad"]) {
  const o = await gate.send("borrow", [P[key], "1000", `demo ${key}`]);
  log(`   borrow on pair ${P[key]} (${key}): tx ${o.hash} -> ${JSON.stringify(o.returned)}`);
}
log(`   attempts: ${JSON.stringify(await gate.view("get_attempts", [0, 10]))}`);

step("13. Unbond and withdraw the surviving bond");
{
  await op.send("reg", "request_unbond", [bA.bond_id]);
  const b = await op.rv("get_bond", [bA.bond_id]);
  await waitUntil(b.withdrawable_at, "unbond delay");
  await op.send("reg", "withdraw_bond", [bA.bond_id]);
  log(`   bond ${bA.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bA.bond_id]))}`);
}

step("14. Everyone claims; the registry drains to 0");
const treasury = as("deployer");
for (const [name, a] of [["operator", op], ["challenger", ch], ["contester", ct], ["patrol", pt], ["seeder", seeder], ["treasury", treasury]]) {
  const addr = (await a.rv("get_claimable", [connectAddr(name)])).claimable;
  if (addr !== "0") await a.send("reg", "claim", []);
  log(`   ${name}: ${JSON.stringify(await a.rv("get_claimable", [connectAddr(name)]))}`);
}
const L = await pt.rv("get_ledger");
log(`   ledger: ${JSON.stringify(L)}`);
log(`\nRESULT demo: held_now ${L.held_now} (received ${L.received} = claimed ${L.claimed}), invariant ${L.invariant_holds}`);

function connectAddr(role) {
  return connect({ address: dep[REG].address, role: role === "treasury" ? "deployer" : role }).account.address.toLowerCase();
}
