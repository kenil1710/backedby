/**
 * The demo's last step on its own (test/demo_run.mjs step 17), for a run interrupted there: everyone claims, each
 * payout is proved on chain, and the demo registry must drain to 0.
 *   node test/demo_claims.mjs >> docs/demo-run.log
 */
import { writeFileSync } from "node:fs";
import { actor, deployments } from "../tools/lib/flow.mjs";
import { connect } from "./harness.mjs";

const REG = "BackedByRegistryDemo";
const log = (m) => console.log(m);
const as = (role) => actor({ role, registry: REG, log });
const dep = deployments().contracts;
log(`\n## 17. (resumed) Everyone claims; each payout is proved on chain; the registry drains to 0  (${new Date().toISOString()})`);
const payouts = [];
for (const role of ["operator", "challenger", "contester", "patrol", "borrower", "deployer"]) {
  const r = await as(role).claimVerified(role === "deployer" ? "treasury" : role);
  if (r) payouts.push(r);
}
const pt = as("patrol");
const L = await pt.rv("get_ledger");
const held = await connect({ address: dep[REG].address, role: "patrol" }).read.getBalance({ address: dep[REG].address });
log(`   ledger: ${JSON.stringify(L)}`);
log(`   eth_getBalance(${dep[REG].address}) = ${held}`);
writeFileSync(new URL("../docs/payouts.json", import.meta.url), JSON.stringify({
  registry: dep[REG].address, commit: dep[REG].commit, at: new Date().toISOString(), eth_get_balance_after: held.toString(),
  ledger: L, payouts }, null, 1) + "\n");
log(`\nRESULT demo: eth_getBalance ${held}, ledger held_now ${L.held_now} (received ${L.received} = claimed ${L.claimed}), ` +
  `${payouts.filter((p) => p.ok).length}/${payouts.length} payouts delivered, invariant ${L.invariant_holds}`);
