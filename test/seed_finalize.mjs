// Finalizes every canonical ruling whose 6 h window has passed (anyone may). Logs to docs/seed-run.log.
import { actor } from "../tools/lib/flow.mjs";
const a = actor({ role: "seeder", registry: "BackedByRegistry", log: console.log });
console.log(`\n=== finalize ${new Date().toISOString()}`);
for (let pass = 0; pass < 3; pass++) {
  const pairs = (await a.rv("get_pairs", [0, 50])).pairs;
  const todo = pairs.filter((p) => p.open && p.open.status === "PROVISIONAL" && Date.now() / 1000 >= p.open.contest_deadline);
  if (!todo.length) break;
  for (const p of todo) {
    const c = await a.finalize(p.open.check_id);
    console.log(`FINAL pair ${p.pair_id} ${p.label}: check ${c.check_id} ${c.status} ${c.verdict} ${c.how}`);
  }
}
