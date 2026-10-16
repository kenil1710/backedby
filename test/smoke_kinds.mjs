// On the smoke deployment: one pair per bridge kind, end to end
// (authenticate -> register -> monitor at fresh pins -> read -> rule).
import { actor } from "../tools/lib/flow.mjs";
const a = actor({ set: "smoke", role: "probe", registry: "BackedByRegistryDemo" });
const ONLY = process.argv.find((x) => x.startsWith("--only="))?.slice(7);
const K = [
  ["arbitrum", "0x514910771af9ca656af840dff83e8264ecf986ca", "0xf97f4df75117a78c1a5a0dbb814af92458539fb4"],
  ["optimism", "0x514910771af9ca656af840dff83e8264ecf986ca", "0x350a791bfc2c21f9ed5d10980dad2e2638ffa7f6"],
  ["base", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca"],
  ["op_dai", "0x6b175474e89094c44da98b954eedeac495271d0f", "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1"],
  ["polygon", "0xdac17f958d2ee523a2206206994597c13d831ec7", "0xc2132d05d31c914a87c6611c10748aeb04b58e8f"],
  ["nomad", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0x8f552a71efe5eefc207bf75485b356a0b3f01ec9"],
];
for (const [kind, l1, l2] of K.filter((k) => !ONLY || ONLY.split(",").includes(k[0]))) {
  console.log(`\n== ${kind}`);
  const au = await a.authenticate(kind, l1, l2);
  if (!au.auth_id) continue;
  const r = await a.register([au.auth_id], 0, "smoke " + kind);
  if (!r.pair_id) continue;
  const pins = await a.pins(r.pair_id);
  console.log("pins", JSON.stringify(pins.blocks), "gap", pins.gap);
  const m = await a.monitor(r.pair_id, pins.blocks);
  const rd = await a.read(m.check_id);
  console.log("reading", rd.reading?.status, rd.reading?.reason, JSON.stringify(rd.reading?.reading?.anchors));
  const c = await a.rule(m.check_id);
  console.log("RESULT", kind, c.status, c.verdict1 || c.verdict, c.reason, "ratio_bps", c.ruling1?.ratio_bps);
}
