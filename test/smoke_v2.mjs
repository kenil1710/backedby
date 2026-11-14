// v2 smoke on Studio Dev (deployments.smoke.json): one pair per new template
// through authenticate -> register -> monitor -> read -> rule, in real GenVM.
//   node test/smoke_v2.mjs [wh|ccip|lz|por]
import { actor } from "../tools/lib/flow.mjs";
import { L1 } from "../tools/lib/bridges.mjs";
const a = actor({ set: "smoke", role: "probe", registry: "BackedByRegistryDemo" });
const which = process.argv[2] ?? "wh";
const P = {
  wh: [["wh_arbitrum", L1.USDC, "0xc96f2715e2a242d50d1b0bc923dbe1740b8ecf18"], ["wh_polygon", L1.USDC, "0x4318cb63a2b8edf2de971e2f17f77097e499459d"]],
  ccip: [["ccip_base", "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f", "0x6bb7a212910682dcfdbd5bcbb3e28fb4e8da10ee"]],
  lz: [["oft_arbitrum", L1.USDT, "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"]],
  por: [["arbitrum", L1.WBTC, "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f"]],
}[which];
const ids = [];
for (const [k, l1, l2] of P) {
  const au = await a.authenticateP(k, l1, l2);
  console.log(`AUTH ${k} -> ${au.auth_id} ${au.ok ? "" : au.revertReason}`);
  if (!au.auth_id) process.exit(1);
  ids.push(au.auth_id);
}
const r = await a.register(ids, 0, "smoke " + which);
console.log("PAIR", r.pair_id);
const out = await a.fileReadRule("smoke " + which, async () => { const pins = await a.pins(r.pair_id); return a.monitor(r.pair_id, pins.blocks); });
const c = out.check;
console.log("CHECK", JSON.stringify({ id: c?.check_id, status: c?.status, verdict: c?.verdict1 || c?.verdict, reason: c?.reason, ratio: c?.ruling1?.ratio_bps,
  coverage: c?.ruling1?.coverage, ledgers: c?.ruling1?.ledgers, por: c?.ruling1?.por, alert: c?.ruling1?.alert }, null, 1));
