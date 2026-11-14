/**
 * Creates test/.accounts.json (gitignored): throwaway Studio Dev signing keys.
 * Existing roles are preserved unless --force is passed. Keys never leave this
 * file; scripts load them and print addresses only.
 *
 *   deployer   deploys every contract (and is the registries' treasury)
 *   operator   bonds pairs (seeds and demo)
 *   challenger challenges bonds
 *   contester  contests rulings
 *   patrol     drives checks in the demo run (reads, rules, finalize)
 *   seeder     authenticates and registers the canonical pairs
 *   borrower   CollateralGate demo borrower
 *   probe      throwaway GenVM probes
 *   keeper     the keeper bot signer (tools/keeper.mjs; CI holds it as BACKEDBY_KEEPER_KEY)
 */
import { createAccount } from "genlayer-js";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const target = new URL("./.accounts.json", import.meta.url);
const force = process.argv.includes("--force");
const ROLES = ["deployer", "operator", "challenger", "contester", "patrol", "seeder", "borrower", "probe", "keeper"];
const existing = existsSync(target) && !force ? JSON.parse(readFileSync(target, "utf8")) : {};
const out = {};
for (const role of ROLES) {
  if (existing[role]?.key) { out[role] = existing[role]; continue; }
  const key = `0x${randomBytes(32).toString("hex")}`;
  out[role] = { key, address: createAccount(key).address };
}
writeFileSync(target, JSON.stringify(out, null, 2) + "\n", { mode: 0o600 });
for (const role of ROLES) console.log(`  ${role.padEnd(10)} ${out[role].address}`);
