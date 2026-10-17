import { createClient } from "genlayer-js";
import { studioDevnet } from "genlayer-js/chains";
const c = createClient({ chain: studioDevnet });
const tx = await c.getTransaction({ hash: process.argv[2] });
const lr = tx.consensus_data?.leader_receipt?.[0];
console.log(tx.statusName, tx.txExecutionResultName, JSON.stringify(lr?.result).slice(0,300), (lr?.genvm_result?.stderr||"").slice(-1500));
