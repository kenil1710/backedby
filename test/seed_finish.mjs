// Completes canonical pairs whose check is missing or stuck: reads and rules an
// open check, or files a fresh one, waiting out RPC throttling.
import { actor } from "../tools/lib/flow.mjs";
const a = actor({ role: "seeder", registry: "BackedByRegistry", log: console.log });
const ids = process.argv.slice(2).map(Number);
for (const pid of ids) {
  console.log(`\n== pair ${pid}`);
  let p = await a.rv("get_pair", [pid]);
  if (p.open_check) {
    const c = await a.check(p.open_check);
    if (c.status === "OPEN") { await a.read(c.check_id); const k = await a.rule(c.check_id); console.log(`RESULT pair ${pid}: check ${k.check_id} ${k.status} ${k.verdict1 || k.verdict} ${k.reason}`); }
    p = await a.rv("get_pair", [pid]);
  }
  if (!p.open_check) {
    const r = await a.fileReadRule(`pair ${pid}`, async () => a.monitor(pid, (await a.pins(pid)).blocks));
    console.log(`RESULT pair ${pid}: check ${r.check?.check_id} ${r.check?.status} ${r.check?.verdict1 || r.check?.verdict} ratio_bps ${r.check?.ruling1?.ratio_bps} ${r.check?.reason}`);
  }
}
