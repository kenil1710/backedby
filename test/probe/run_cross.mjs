// Studio probe: a long storage string read before and after a cross-contract view in one write (throwaway)
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
const code = readFileSync(new URL("./StrProbe.py", import.meta.url), "utf8");
const A = await deploy({ chain, wallet, read, code, args: [], label: "A" });
const B = await deploy({ chain, wallet, read, code, args: [], label: "B" });
const a = connect({ address: A.address, role: "probe" }), b = connect({ address: B.address, role: "probe" });
await a.send("put", [1, 250]); await a.send("put", [2, 400]);
await b.send("put", [1, 50]); await b.send("put", [2, 100]); await b.send("put", [3, 250]);
for (const [rid, prid] of [[1, 1], [1, 2], [1, 3], [2, 3], [2, 1]]) { const o = await a.send("cross", [rid, B.address, prid]); console.log("cross", rid, prid, o.ok, o.ok ? await a.view("get_last", []) : o.revertReason); }
