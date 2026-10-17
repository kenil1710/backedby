// Smoke: USDT with two vaults on the smoke deployment.
import { actor } from "../tools/lib/flow.mjs";
import { L1 } from "../tools/lib/bridges.mjs";
const a = actor({ set: "smoke", role: "probe", registry: "BackedByRegistryDemo" });
const POL = "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", ARB = "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", OP = "0x01bff41798a0bcf287b996046ca68b395dbc1071";
const au = await a.authenticateP("polygon", L1.USDT, POL);
const r = await a.register([au.auth_id], 0, "USDT smoke");
const one = await a.fileReadRule("pos only", async () => a.monitor(r.pair_id, (await a.pins(r.pair_id, 0)).blocks));
console.log("RESULT pos-only", one.check.status, one.check.verdict1, one.check.ruling1?.ratio_bps, one.check.reason);
await new Promise((res) => setTimeout(res, Math.max(0, one.check.contest_deadline * 1000 - Date.now()) + 8000));
await a.finalize(one.check.check_id);
const v = await a.authenticateP("oft_polygon", L1.USDT, POL);
await a.send("reg", "add_vault", [r.pair_id, v.auth_id]);
for (const [k, t] of [["oft_arbitrum", ARB], ["oft_optimism", OP]]) { const x = await a.authenticateP(k, L1.USDT, t); await a.send("reg", "add_destination", [r.pair_id, x.auth_id]); }
console.log("pair", JSON.stringify(await a.rv("get_pair", [r.pair_id])).slice(0, 400));
const two = await a.fileReadRule("both vaults", async () => { const p = await a.pins(r.pair_id, 0); console.log("pins", JSON.stringify(p.blocks), "gap", p.gap); return a.monitor(r.pair_id, p.blocks); });
console.log("RESULT two vaults", two.check.status, two.check.verdict1, two.check.ruling1?.ratio_bps, two.check.reason, JSON.stringify(two.check.ruling1?.counted));
