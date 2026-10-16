// Probe on the smoke deployment: register pairs from existing auths, file a
// monitoring check at freshly pinned blocks, read it, rule it.
import { actor } from "../tools/lib/flow.mjs";
import { argOf } from "./harness.mjs";
const a = actor({ set: "smoke", role: "probe", registry: "BackedByRegistryDemo" });
const auth = JSON.parse(argOf("auths", "[]"));
for (const id of auth) {
  const r = await a.register([id], 0, "probe " + id);
  if (!r.pair_id) continue;
  const pins = await a.pins(r.pair_id);
  console.log("pins", pins.blocks, "gap", pins.gap);
  const m = await a.monitor(r.pair_id, pins.blocks);
  const rd = await a.read(m.check_id);
  console.log("reading", JSON.stringify(rd.reading).slice(0, 600));
  const c = await a.rule(m.check_id);
  console.log("check", c.status, c.verdict1 || c.verdict, c.reason, JSON.stringify(c.ruling1));
}
