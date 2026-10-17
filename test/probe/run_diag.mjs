// Re-runs one check's read in a debug ChainReader and prints every RPC batch's outcome per URL.
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
let addr = process.env.DIAG;
if (!addr) addr = (await deploy({ chain, wallet, read, code: readFileSync(new URL("./ChainReaderDiag.py", import.meta.url), "utf8"), args: [], label: "diag" })).address;
console.log("diag at", addr);
const { send, view } = connect({ address: addr, role: "probe" });
const o = await send("diag", [process.argv[2], Number(process.argv[3])]);
console.log(o.status, o.hash);
const r = JSON.parse(await view("get_last", []));
console.log(r.status, r.reason);
for (const l of r.log ?? []) console.log(l.join("  "));
