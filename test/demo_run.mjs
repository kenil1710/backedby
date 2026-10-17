/**
 * Every path on the DEMO registry, on chain, with real chain data, then
 * drained to 0. Each step prints its transactions and the state they left;
 * the run is written to docs/demo-run.log.
 *
 *   STUDIO_RPC=https://backedby-ledger.vercel.app/api/rpc node test/demo_run.mjs >> docs/demo-run.log
 *
 * Public RPCs throttle Studio's shared egress in bursts, so every read that
 * comes back transport-inconclusive is refiled after a pause (flow.mjs).
 *
 * DEMO_FROM=10 resumes an interrupted run at step 10: pairs and bonds are
 * found on chain, and a check the run left PROVISIONAL is finalized first.
 */
import { actor, deployments } from "../tools/lib/flow.mjs";
import { L1, USDT0_DESTS } from "../tools/lib/bridges.mjs";
import { pinAt } from "../tools/lib/pin.mjs";
import { writeFileSync } from "node:fs";
import { connect, sleep } from "./harness.mjs";

const REG = "BackedByRegistryDemo";
const log = (m) => console.log(m);
const as = (role) => actor({ role, registry: REG, log });
// pairs are registered with the borrower key so the demo can run beside the canonical seed (which signs as seeder)
const seeder = as("borrower"), op = as("operator"), ch = as("challenger"), ct = as("contester"), pt = as("patrol");
const dep = deployments().contracts;
const gate = connect({ address: dep.CollateralGateDemo.address, role: "borrower" });
const cfg = await seeder.rv("get_config");
const MIN_BOND = BigInt(cfg.min_bond), MIN_STAKE = BigInt(cfg.min_stake);
const step = (t) => log(`\n## ${t}  (${new Date().toISOString()})`);
const show = (c) => log(`   -> check ${c?.check_id}: ${c?.status} ${c?.verdict || c?.verdict1 || ""} ${c?.ruling1 && c.ruling1.ratio_bps !== undefined ? "ratio_bps " + c.ruling1.ratio_bps : ""} ${c?.reason || ""} ${c?.how || ""}`);
const waitUntil = async (t, why) => { const s = Math.max(0, t - Math.floor(Date.now() / 1000)) + 8; log(`   ... waiting ${s}s (${why})`); await sleep(s * 1000); };
const refusal = (o) => log(`   -> ${o.ok && o.ret?.ok !== false ? "accepted (unexpected)" : "refused: " + (o.ret?.reason ?? o.revertReason)}`);
const USDT_POL = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f";
const USDT_ARB = "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9";
const RECENT_L1 = "0x59d1e836f7b7210a978b25a855085cc46fd090b5";   // bridged to OP Mainnet on 2026-09-01
const RECENT_OP = "0x16d375422a1d6b069c1958848746b97cc053c69e";   // created at OP block 156278236

log(`\n# Demo run ${new Date().toISOString()} on ${dep[REG].address} (commit ${dep[REG].commit})`);
log(`config: window ${cfg.window_s}s, read timeout ${cfg.read_timeout_s}s, unbond delay ${cfg.unbond_delay_s}s, min bond ${cfg.min_bond}, min stake ${cfg.min_stake}, fast gap ${cfg.fast_gap_s}s`);

step("1. Register five real pairs, each authenticated by its bridge's own mapping");
const P = {};
for (const [key, kind, sym, l2, label] of [
  ["arb", "arbitrum", "LINK", "0xf97f4df75117a78c1a5a0dbb814af92458539fb4", "LINK on Arbitrum (demo)"],
  ["pol", "polygon", "USDT", USDT_POL, "USDT on Polygon, PoS vault only (demo)"],
  ["nomad", "nomad", "USDC", "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9", "madUSDC on Moonbeam (demo)"],
  ["op", "optimism", "USDC", "0x7f5c764cbc14f9669b88837ca1490cca17c31607", "USDC.e on OP Mainnet (demo)"],
  ["recent", "optimism", null, RECENT_OP, "A token bridged to OP on 2026-09-01 (demo)"],
]) {
  const have = (await seeder.rv("get_pairs", [0, 50])).pairs.find((p) => p.label === label);
  if (have) { P[key] = have.pair_id; log(`   -> pair ${have.pair_id}: ${label} (registered earlier)`); continue; }
  let r = { pair_id: 0 };
  for (let i = 0; i < 3 && !r.pair_id; i++) {
    const au = await seeder.authenticateP(kind, sym ? L1[sym] : RECENT_L1, l2);
    if (au.auth_id) r = await seeder.register([au.auth_id], 0, label);
  }
  P[key] = r.pair_id;
  log(`   -> pair ${r.pair_id}: ${label}`);
}

const FROM = Number(process.env.DEMO_FROM || 0);
let bA, bB;
if (FROM > 2) {
  const bonds = [];
  for (let id = 1; ; id++) { const b = await op.rv("get_bond", [id]); if (!b.found) break; bonds.push(b); }
  bA = bonds.find((b) => b.pair_id === P.arb); bB = bonds.find((b) => b.pair_id === P.pol);
  log(`\n## Resuming at step ${FROM}: bond ${bA.bond_id} on pair ${P.arb}, bond ${bB.bond_id} on pair ${P.pol}  (${new Date().toISOString()})`);
  for (let id = 1; ; id++) {
    const c = await pt.check(id);
    if (!c?.status) break;
    if (c.status === "PROVISIONAL") { await waitUntil(c.contest_deadline, `window of check ${id}`); show(await pt.finalize(id)); }
  }
} else {
step("2. A fake pair is refused: Circle's native USDC on OP passed off as the bridge's token");
refusal(await seeder.patiently("fake pair", () => seeder.authenticate("optimism", L1.USDC, "0x0b2c639c533813f4aa9d7837caf62653d097ff85"),
  (o) => !/NOT_AUTHENTICATED/.test(String(o.revertReason)), 8));

step("3. Anyone adds a destination the pair is missing (a second Standard Bridge USDC on OP), with the same proof");
const extra = "0x130c1dcc9fd997fa02f555dad54edaf553f2555a";
const ax = await ct.authenticateP("optimism", L1.USDC, extra);
await ct.send("reg", "add_destination", [P.op, ax.auth_id]);
log(`   -> pair ${P.op} destinations: ${(await ct.rv("get_pair", [P.op])).dests.map((d) => d.token + "/" + d.decimals).join(", ")}`);
log("   adding the same destination again:");
refusal(await ct.send("reg", "add_destination", [P.op, (await ct.authenticateP("optimism", L1.USDC, extra)).auth_id]));

step("4. The operator bonds two pairs as registered");
bA = await op.bond(P.arb, MIN_BOND);
bB = await op.bond(P.pol, MIN_BOND);
log(`   -> bond ${bA.bond_id} on pair ${P.arb}, bond ${bB.bond_id} on pair ${P.pol} (one vault)`);
const bondStart = Math.floor(Date.now() / 1000);

step("5. INCONCLUSIVE: a challenge pinned before the bond started is refunded");
show((await pt.fileReadRule("challenge before bond", async () => ch.challenge(bA.bond_id, (await ch.pins(P.arb, 90)).blocks, MIN_STAKE))).check);

step("6. Waiting until finalized blocks exist after the bond started (Ethereum finality is ~15-20 min)");
for (;;) {
  const pins = await ch.pins(P.arb, 0);
  if (pins.detail.ethereum.timestamp >= bondStart + 30) break;
  log(`   ... finalized Ethereum block at ${new Date(pins.detail.ethereum.timestamp * 1000).toISOString()}, bond started ${new Date(bondStart * 1000).toISOString()}`);
  await sleep(120_000);
}

step("7. Challenge -> BACKED, contested, re-read, upheld: the stakes go into the bond");
{
  const r = await pt.fileReadRule("challenge (backed)", async () => ch.challenge(bA.bond_id, (await ch.pins(P.arb, 0)).blocks, MIN_STAKE));
  const cA = r.check.check_id;
  show(r.check);
  show((await ct.contest(cA, MIN_STAKE)).check);
  for (let i = 0; i < 6; i++) {
    const rd = await pt.read(cA, 2);
    if (rd.reading?.found) break;
    log("   ... re-read throttled, waiting 90s"); await sleep(90_000);
  }
  show(await pt.rule(cA));
  log(`   bond ${bA.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bA.bond_id]))}`);
}

step("8. Challenge -> UNDER_BACKED: the USDT pair as registered (PoS predicate only) holds 0.64%; window passes, bond slashed, bounty paid");
{
  const r = (await pt.fileReadRule("challenge (under)", async () => ch.challenge(bB.bond_id, (await ch.pins(P.pol, 0)).blocks, MIN_STAKE))).check;
  show(r);
  await waitUntil(r.contest_deadline, "contest window");
  show(await pt.finalize(r.check_id));
  log(`   payouts ${JSON.stringify((await pt.check(r.check_id)).payouts)}`);
  log(`   bond ${bB.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bB.bond_id]))}`);
}

step("9. The verdict above was about an incomplete pair: anyone adds the missing vault (USDT0's LayerZero adapter)");
{
  log("   an unauthenticated vault is refused (Polygon's USDC.e has no OFT):");
  refusal(await ct.patiently("not an OFT", () => ct.authenticate("oft_polygon", L1.USDC, "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"),
    (o) => !/NOT_AUTHENTICATED/.test(String(o.revertReason)), 8));
  const v = await ct.authenticateP("oft_polygon", L1.USDT, USDT_POL);
  log(`   adapter derived from the token: ${(await ct.cv("get_auth", [v.auth_id])).vault}`);
  await ct.send("reg", "add_vault", [P.pol, v.auth_id]);
  const pp = await ct.rv("get_pair", [P.pol]);
  log(`   -> pair ${P.pol} vaults: ${JSON.stringify(pp.vaults.map((x) => x.vault + " " + x.kind))}, max gap ${pp.max_gap_s}s`);
  log("   the same vault again:");
  refusal(await ct.send("reg", "add_vault", [P.pol, (await ct.authenticateP("oft_polygon", L1.USDT, USDT_POL)).auth_id]));
  log("   a vault proved only onto a token this pair does not have (USDT0 on Arbitrum):");
  refusal(await ct.send("reg", "add_vault", [P.pol, (await ct.authenticateP("oft_arbitrum", L1.USDT, USDT_ARB)).auth_id]));
  log("   the adapter backs USDT0 on every chain it has a peer on: anyone adds each destination two RPCs can read");
  for (const [kind, l2] of USDT0_DESTS) {
    const d = await ct.authenticateP(kind, L1.USDT, l2);
    if (d.auth_id) await ct.send("reg", "add_destination", [P.pol, d.auth_id]);
  }
  log(`   -> pair ${P.pol} destinations: ${(await ct.rv("get_pair", [P.pol])).dests.map((d) => d.chain).join(", ")}`);
  const r = (await pt.fileReadRule("monitor with both vaults", async () => pt.monitor(P.pol, (await pt.pins(P.pol, 0)).blocks))).check;
  show(r);
  log(`   locked per vault ${JSON.stringify((await pt.cv("get_reading", [pt.regAddr, r.check_id, 1])).reading?.locked_by_vault)}`);
  await waitUntil(r.contest_deadline, "contest window");
  show(await pt.finalize(r.check_id));
}
}

step("10. Monitoring INCONCLUSIVE: pins that break the 10-minute gap rule");
show((await pt.fileReadRule("monitor with bad pins", async () => {
  const pins = await pt.pins(P.op, 0);
  return pt.monitor(P.op, { ...pins.blocks, optimism: pins.blocks.optimism - 400 });   // 800 s before the Ethereum block
})).check);

step("11. Timeout: a monitoring check nobody reads expires INCONCLUSIVE");
{
  const c = await pt.monitor(P.nomad, (await pt.pins(P.nomad, 0)).blocks);
  await waitUntil((await pt.check(c.check_id)).read_deadline, "read deadline");
  show(await pt.expire(c.check_id));
}

step("12. INCONCLUSIVE about the pair: blocks pinned before the OP token existed, so its supply cannot be read");
{
  const at = await pinAt("ethereum", ["optimism"], 1788138777 - 600);
  const blocks = { ethereum: at.blocks.ethereum.number, optimism: at.blocks.optimism.number };
  log(`   pinned ${JSON.stringify(blocks)} (OP token created at block 156278236)`);
  show((await pt.fileReadRule("monitor before creation", async () => pt.monitor(P.recent, blocks))).check);
  log(`   latest ruling for pair ${P.recent}: ${JSON.stringify(await pt.rv("get_latest", [P.recent]))}`);
}

step("13. Monitoring FINAL on three more pairs (the gate needs final rulings)");
const finals = [];
for (const key of ["nomad", "op", "arb"]) {
  const r = (await pt.fileReadRule(`monitor ${key}`, async () => pt.monitor(P[key], (await pt.pins(P[key], key === "nomad" ? 0 : 30)).blocks))).check;
  show(r);
  if (r.status === "PROVISIONAL") finals.push([r.check_id, r.contest_deadline]);
}
for (const [cid, dl] of finals) { await waitUntil(dl, `window of check ${cid}`); show(await pt.finalize(cid)); }

step("14. CollateralGate: allowed on a fresh BACKED pair; refused on INCONCLUSIVE, UNDER_BACKED, a recent non-BACKED ruling, stale, and unknown pairs");
for (const key of ["arb", "recent", "nomad", "pol", "op"]) {
  const o = await gate.send("borrow", [P[key], "1000", `demo ${key}`]);
  log(`   borrow on pair ${P[key]} (${key}): tx ${o.hash} -> ${JSON.stringify(o.returned)}`);
}
{
  const o = await gate.send("borrow", [99, "1000", "demo no such pair"]);
  log(`   borrow on pair 99: tx ${o.hash} -> ${JSON.stringify(o.returned)}`);
}
log(`   attempts: ${JSON.stringify(await gate.view("get_attempts", [0, 10]))}`);

step("15. Unbond and withdraw the surviving bond");
{
  await op.send("reg", "request_unbond", [bA.bond_id]);
  await waitUntil((await op.rv("get_bond", [bA.bond_id])).withdrawable_at, "unbond delay");
  await op.send("reg", "withdraw_bond", [bA.bond_id]);
  log(`   bond ${bA.bond_id}: ${JSON.stringify(await op.rv("get_bond", [bA.bond_id]))}`);
}

step("16. Everyone claims; each payout is proved on chain; the registry drains to 0");
const payouts = [];
for (const role of ["operator", "challenger", "contester", "patrol", "borrower", "deployer"]) {
  const r = await as(role).claimVerified(role === "deployer" ? "treasury" : role);
  if (r) payouts.push(r);
}
const L = await pt.rv("get_ledger");
const held = await connect({ address: dep[REG].address, role: "patrol" }).read.getBalance({ address: dep[REG].address });
log(`   ledger: ${JSON.stringify(L)}`);
log(`   eth_getBalance(${dep[REG].address}) = ${held}`);
writeFileSync(new URL("../docs/payouts.json", import.meta.url), JSON.stringify({
  registry: dep[REG].address, commit: dep[REG].commit, at: new Date().toISOString(), eth_get_balance_after: held.toString(),
  ledger: L, payouts }, null, 1) + "\n");
log(`\nRESULT demo: eth_getBalance ${held}, ledger held_now ${L.held_now} (received ${L.received} = claimed ${L.claimed}), ` +
  `${payouts.filter((p) => p.ok).length}/${payouts.length} payouts delivered, invariant ${L.invariant_holds}`);
