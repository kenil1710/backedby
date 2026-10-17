// Deploys test/probe/PayProbe.py and measures each emit_transfer form by the recipient's balance.
import { readFileSync } from "node:fs";
import { createClient, createAccount } from "genlayer-js";
import { CHAINS, accounts, deploy, connect, sleep } from "../harness.mjs";
const chain = CHAINS.studiodev;
const acc = accounts();
const account = createAccount(acc.probe.key);
const wallet = createClient({ chain, account }); const read = createClient({ chain });
let addr = process.env.PROBE;
if (!addr) {
  const d = await deploy({ chain, wallet, read, code: readFileSync(new URL("./PayProbe.py", import.meta.url), "utf8"), args: [], label: "PayProbe" });
  addr = d.address; console.log("probe at", addr, d.ok);
  const { send } = connect({ address: addr, role: "probe" });
  console.log("fund", (await send("fund", [], 3n * 10n ** 18n)).status);
}
const { send } = connect({ address: addr, role: "probe" });
const bal = (a) => read.getBalance({ address: a });
const to = acc.borrower.address;
const AMT = 10n ** 16n;
for (const [fn, args] of [["pay_default", [to, AMT]], ["pay_decided", [to, AMT]], ["pay_balance", [to, AMT, 30000000000000000n]], ["pay_balance_decided", [to, AMT, 30000000000000000n]]].filter(([f]) => !process.env.ONLY || process.env.ONLY === f)) {
  const b0 = await bal(to), c0 = await bal(addr);
  const o = await send(fn, args);
  let b1 = b0, c1 = c0;
  for (let i = 0; i < 30; i++) { await sleep(8000); b1 = await bal(to); c1 = await bal(addr); if (b1 !== b0) break; }
  console.log(fn, o.status, o.hash, "recipient Δ", (b1 - b0).toString(), "contract Δ", (c1 - c0).toString(), o.revertReason?.slice(0, 200) ?? "");
}
