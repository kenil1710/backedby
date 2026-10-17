// Deploys test/probe/RpcProbe2.py (throwaway) and prints what GenVM sees from each RPC.
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
const code = readFileSync(new URL("./RpcProbe2.py", import.meta.url), "utf8");
const d = await deploy({ chain, wallet, read, code, args: [], label: "RpcProbe" });
console.log("probe at", d.address, d.ok);
const { send, view } = connect({ address: d.address, role: "probe" });
const o = await send("probe", [1]);
console.log(o.ok, o.status);
const r = JSON.parse(await view("get_last", []));
for (const [u, v] of Object.entries(r)) console.log(u.padEnd(46), v.map((x) => x.slice(0, 40)).join(" | "));
