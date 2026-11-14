// A fresh throwaway key for the e2e run, SAVED to the gitignored test/.accounts.json BEFORE it is used,
// then funded from the Studio Dev faucet. Only the address is printed.
import { readFileSync, writeFileSync } from "node:fs";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { rpc } from "./wallet.js";
const path = new URL("../test/.accounts.json", import.meta.url);
const a = JSON.parse(readFileSync(path, "utf8"));
const key = generatePrivateKey();
const address = privateKeyToAccount(key).address;
(a.throwaway ??= []).push({ use: "e2e", key, address, created: new Date().toISOString() });
writeFileSync(path, JSON.stringify(a, null, 2) + "\n", { mode: 0o600 });
await rpc("sim_fundAccount", [address, 20 * 10 ** 18]);
console.log("e2e wallet", address);
