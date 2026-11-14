// H6 on Studio: the USDT pair with the PoS predicate, USDT0's adapter and every USDT0 destination two RPCs read
// (a ~19 KB request), through monitor -> read -> rule -> finalize, on the smoke deployment.
import { actor } from "../tools/lib/flow.mjs";
import { L1, USDT0_DESTS } from "../tools/lib/bridges.mjs";
import { sleep } from "./harness.mjs";
const a = actor({ set: "smoke", role: "probe", registry: "BackedByRegistryDemo" });
const USDT_POL = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f";
const first = await a.authenticateP("polygon", L1.USDT, USDT_POL);
const r = await a.register([first.auth_id], 0, "smoke USDT, 2 vaults, every USDT0 destination");
const v = await a.authenticateP("oft_polygon", L1.USDT, USDT_POL);
await a.send("reg", "add_vault", [r.pair_id, v.auth_id]);
for (const [k, l2] of USDT0_DESTS) {
  const d = await a.authenticateP(k, L1.USDT, l2);
  if (d.auth_id) await a.send("reg", "add_destination", [r.pair_id, d.auth_id]);
}
const p = await a.rv("get_pair", [r.pair_id]);
console.log("PAIR", r.pair_id, "dests", p.dests.length, "vaults", p.vaults.length);
const c = (await a.fileReadRule("big", async () => a.monitor(r.pair_id, (await a.pins(r.pair_id, 0)).blocks))).check;
console.log("RULED", c?.check_id, c?.status, c?.verdict1, c?.ruling1?.ratio_bps, c?.ruling1?.coverage?.state, JSON.stringify(a.regAddr));
console.log("REQUEST BYTES", JSON.stringify(await a.rv("get_check_request", [c.check_id])).length);
if (c?.status === "PROVISIONAL") {
  await sleep((c.contest_deadline - Math.floor(Date.now() / 1000) + 10) * 1000);
  const f = await a.finalize(c.check_id);
  console.log("FINAL", f.status, f.verdict, "history", (await a.rv("get_history", [r.pair_id, 0, 5])).total);
}
