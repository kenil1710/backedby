// deployments.json -> frontend/src/lib/deployments.json (the site's only source of addresses)
import { readFileSync, writeFileSync } from "node:fs";
const set = (process.argv.find((a) => a.startsWith("--set=")) ?? "--set=final").slice(6);
const dep = JSON.parse(readFileSync(new URL(set === "final" ? "../deployments.json" : `../deployments.${set}.json`, import.meta.url), "utf8"));
const c = dep.contracts;
// a smoke set has only the demo registry; let it stand in for both (local builds only)
c.BackedByRegistry ??= c.BackedByRegistryDemo;
c.CollateralGate ??= c.CollateralGateDemo;
const out = {
  commit: c.ChainReader.commit,
  reader: c.ChainReader.address, registry: c.BackedByRegistry.address, registryDemo: c.BackedByRegistryDemo.address,
  gate: c.CollateralGate.address, gateDemo: c.CollateralGateDemo.address,
  contracts: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, { address: v.address, file: v.file, sha256: v.sha256, bytes: v.bytes, commit: v.commit, deploy_tx: v.deploy_tx, constructor_args: v.constructor_args }])),
};
writeFileSync(new URL("../frontend/src/lib/deployments.json", import.meta.url), JSON.stringify(out, null, 2) + "\n");
console.log("synced", Object.keys(out.contracts).join(", "));
