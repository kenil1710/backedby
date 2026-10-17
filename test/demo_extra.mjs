// Demo steps that public-RPC throttling cut short in demo_run.mjs, run again
// until the contract answers on the merits. Appended to docs/demo-run.log.
import { actor, deployments } from "../tools/lib/flow.mjs";
import { L1 } from "../tools/lib/bridges.mjs";
import { connect } from "./harness.mjs";
const log = (m) => console.log(m);
const a = actor({ role: "seeder", registry: "BackedByRegistryDemo", log });
log(`\n## 2 (again). A fake pair is refused on its merits: Circle's native USDC on OP passed off as the bridge's token  (${new Date().toISOString()})`);
const r = await a.patiently("fake pair", () => a.authenticate("optimism", L1.USDC, "0x0b2c639c533813f4aa9d7837caf62653d097ff85"),
  (o) => !/NOT_AUTHENTICATED/.test(String(o.revertReason)), 8);
log(`   -> ${r.ok ? "ACCEPTED (unexpected)" : "refused: " + r.revertReason}`);
log(`\n## 12 (more). CollateralGate refuses a pair that does not exist  (${new Date().toISOString()})`);
const g = connect({ address: deployments().contracts.CollateralGateDemo.address, role: "borrower" });
const o = await g.send("borrow", [99, "1000", "demo no such pair"]);
log(`   borrow on pair 99: tx ${o.hash} -> ${JSON.stringify(o.returned)}`);
const L = await a.rv("get_ledger");
log(`   ledger after: held_now ${L.held_now}, invariant ${L.invariant_holds}`);
