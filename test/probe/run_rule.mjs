// Studio probe reproducing BackedByRegistry.rule on demo check 4's real request (throwaway)
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
import { actor } from "../../tools/lib/flow.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
const reg = actor({ role: "patrol", registry: "BackedByRegistryDemo", log: () => {} });
const req = await reg.rv("get_check_request", [4]); for (const k of ["ok", "round", "check_id", "read_by"]) delete req[k];
const pair = await reg.rv("get_pair", [2]);
const reading = await reg.cv("get_reading", [reg.regAddr, 4, 1]);
const canon = (o) => JSON.stringify(o, Object.keys(o).sort ? undefined : undefined);
const code = readFileSync(new URL("./RuleProbe.py", import.meta.url), "utf8");
const P = await deploy({ chain, wallet, read, code, args: [], label: "RuleProbe" });
const Q = await deploy({ chain, wallet, read, code, args: [], label: "Peer" });
const p = connect({ address: P.address, role: "probe" }), q = connect({ address: Q.address, role: "probe" });
// python-canonical text is produced by the contract itself from this JSON
console.log("put_check", (await p.send("put_check", [4, JSON.stringify(req), JSON.stringify({ dests: pair.dests, vaults: pair.vaults, anchors: pair.anchors })])).returned);
console.log("put_big", (await q.send("put_big", [1, JSON.stringify(reading)])).returned);
for (const fix of [0, 0, 1]) { const o = await p.send("rule_like", [4, Q.address, fix]); console.log("rule_like fix", fix, o.ok, o.ok ? await p.view("get_last", []) : String(o.revertReason).slice(0, 200)); }
