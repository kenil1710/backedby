import { actor } from "../tools/lib/flow.mjs";
const pt = actor({ set: "smoke", role: "patrol", registry: "BackedByRegistryDemo", log: console.log });
const pins = await pt.pins(1, 90);
const m = await pt.monitor(1, pins.blocks);
console.log("CHECK", m.check_id);
