// Written by tools/sync_addresses.mjs from deployments.json. Do not edit the JSON by hand.
import dep from "./deployments.json";
export const COMMIT: string = dep.commit;
export const ADDR = {
  reader: dep.reader, registry: dep.registry, registryDemo: dep.registryDemo, gate: dep.gate, gateDemo: dep.gateDemo,
};
export const CONTRACTS: Record<string, { address: string; file: string; sha256: string; bytes: number; commit: string; deploy_tx: string; constructor_args: unknown[] }> = dep.contracts;
