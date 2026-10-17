/**
 * Smoke on deployments.smoke.json: (1) a refused payable is claimed back and the
 * payout is proved on chain; (2) USDT on Polygon with both vaults and every
 * USDT0 destination is authenticated, registered and read in one check.
 *   node smoke_shared.mjs [--skip-pay]
 */
import { actor } from "../tools/lib/flow.mjs";
import { L1, USDT0_DESTS } from "../tools/lib/bridges.mjs";
const log = (m) => console.log(m);
const as = (role) => actor({ set: "smoke", role, registry: "BackedByRegistryDemo", log });
const op = as("operator"), sd = as("seeder"), pt = as("patrol");
if (!process.argv.includes("--skip-pay")) {
  log("\n## payout: a refused bond is credited back, then claimed");
  log(JSON.stringify((await op.send("reg", "bond", [999], 30_000_000_000_000_000n)).ret));
  log(JSON.stringify(await op.claimVerified("operator")));
}
log("\n## USDT on Polygon: both vaults, every USDT0 destination");
const pairs = (await sd.rv("get_pairs", [0, 50])).pairs;
let pid = pairs.find((p) => p.label === "USDT smoke")?.pair_id;
if (!pid) {
  const a = await sd.authenticateP("polygon", L1.USDT, "0xc2132d05d31c914a87c6611c10748aeb04b58e8f");
  pid = (await sd.register([a.auth_id], 0, "USDT smoke")).pair_id;
  const v = await sd.authenticateP("oft_polygon", L1.USDT, "0xc2132d05d31c914a87c6611c10748aeb04b58e8f");
  await sd.send("reg", "add_vault", [pid, v.auth_id]);
}
for (const [kind, l2] of USDT0_DESTS) {
  const p = await sd.rv("get_pair", [pid]);
  if (p.dests.some((d) => d.chain === kind.slice(4))) continue;
  const t0 = Date.now();
  const a = await sd.authenticateP(kind, L1.USDT, l2);
  log(`   ${kind}: auth ${a.auth_id} ${a.auth_id ? JSON.stringify(a.ret) : a.revertReason} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  if (a.auth_id) await sd.send("reg", "add_destination", [pid, a.auth_id]);
}
const p = await sd.rv("get_pair", [pid]);
log(`   pair ${pid}: ${p.vaults.length} vaults, ${p.dests.length} destinations: ${p.dests.map((d) => d.chain + ":" + d.token).join(", ")}`);
const t0 = Date.now();
const r = await pt.fileReadRule("monitor all", async () => { const pins = await pt.pins(pid, 90); log(`   pins ${JSON.stringify(pins.blocks)} gap ${pins.gap}`); return pt.monitor(pid, pins.blocks); });
const c = r.check;
log(`   check ${c?.check_id}: ${c?.status} ${c?.verdict1} ratio_bps ${c?.ruling1?.ratio_bps} ${c?.reason ?? ""} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
const rd = (await pt.cv("get_reading", [pt.regAddr, c.check_id, 1])).reading;
log(`   reading ${rd?.status} ${rd?.reason ?? ""} locked ${JSON.stringify(rd?.locked_by_vault)} supplies ${JSON.stringify(rd?.dests?.map((d) => d.chain + ":" + d.supply))}`);
