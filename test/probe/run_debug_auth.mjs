import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect } from "../harness.mjs";
const chain = CHAINS.studiodev;
const account = createAccount(accounts().probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
const d = await deploy({ chain, wallet, read, code: readFileSync(new URL("./ChainReaderDebug.py", import.meta.url), "utf8"), args: [], label: "dbg" });
const { send } = connect({ address: d.address, role: "probe" });
for (const a of [["optimism","0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48","0x7f5c764cbc14f9669b88837ca1490cca17c31607"],["base","0xbe9895146f7af43049ca1c1ae358b0541ea49704","0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22"]]) {
  const o = await send("authenticate", a);
  console.log(a[0], o.ok, String(o.revertReason));
}
