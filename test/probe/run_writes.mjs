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
const P = await deploy({ chain, wallet, read, code: readFileSync(new URL("./RuleProbe.py", import.meta.url), "utf8"), args: [], label: "RuleProbe" });
const p = connect({ address: P.address, role: "probe" });
await p.send("put_check", [4, JSON.stringify(req), JSON.stringify({ dests: pair.dests, vaults: pair.vaults, anchors: pair.anchors })]);
for (const n of [100, 400]) {
  const o = await p.send("writes", [4, n]);
  console.log(n, o.ok, o.ok ? await p.view("get_last", []) : String(o.revertReason).slice(0, 200), JSON.stringify(await p.view("check_stored", [4, n])));
}
