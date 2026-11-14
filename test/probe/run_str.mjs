// Studio probe: is a long storage string read twice in one write identical? (throwaway, test/probe/StrProbe.py)
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
const d = await deploy({ chain, wallet, read, code: readFileSync(new URL("./StrProbe.py", import.meta.url), "utf8"), args: [], label: "StrProbe" });
console.log("probe", d.address, d.ok);
const { send, view } = connect({ address: d.address, role: "probe" });
for (const [rid, n] of [[1, 50], [2, 150], [3, 250], [4, 400]]) console.log("put", rid, (await send("put", [rid, n])).returned);
for (const [a, b] of [[1, 2], [3, 4], [4, 3], [4, 4], [3, 3]]) { const o = await send("twice", [a, b]); console.log("twice", a, b, o.ok, await view("get_last", [])); }
