/**
 * The patrol bot (GitHub Actions, every 6 h; runnable by hand). On the
 * CANONICAL registry:
 *   1. every open check: read it, rule it, finalize it, or expire it -
 *      whichever its state and deadlines allow (its own or anyone's);
 *   2. every pair with no open check, whose monitoring interval has passed
 *      and whose chains have new finalized blocks: a monitoring check at fresh
 *      pins, read and ruled at once (final after the 6 h window, on a later run).
 *   node tools/patrol.mjs [--dry] [--registry=BackedByRegistry]
 * Writes a summary to docs/patrol-last.json (CI uploads it as an artifact).
 */
import { writeFileSync } from "node:fs";
import { actor } from "./lib/flow.mjs";
import { argOf, fundOnStudio, CHAINS, connect } from "../test/harness.mjs";

const dry = process.argv.includes("--dry");
const reg = argOf("registry", "BackedByRegistry");
const a = actor({ role: "patrol", registry: reg });
const me = connect({ address: a.regAddr, role: "patrol" }).account.address;
await fundOnStudio(CHAINS.studiodev, me, 50n * 10n ** 18n);
const now = () => Math.floor(Date.now() / 1000);
const cfg = await a.rv("get_config");
const out = { at: new Date().toISOString(), registry: a.regAddr, patrol: me, actions: [] };
const did = (pair, check, what, result) => { out.actions.push({ pair, check, what, result }); console.log(`pair ${pair} check ${check}: ${what} -> ${result}`); };

async function advance(c) {
  const id = c.check_id;
  if (c.status === "PROVISIONAL") {
    if (now() >= c.contest_deadline) { const k = dry ? c : await a.finalize(id); did(c.pair_id, id, "finalize", `${k.status} ${k.verdict}`); }
    else did(c.pair_id, id, "wait", `contestable until ${new Date(c.contest_deadline * 1000).toISOString()}`);
    return;
  }
  if (c.status !== "OPEN" && c.status !== "CONTESTED") return;
  const rnd = c.status === "OPEN" ? 1 : 2;
  const deadline = rnd === 1 ? c.read_deadline : c.contest_read_deadline;
  let r = await a.cv("get_reading", [a.regAddr, id, rnd]);
  if (!r.found && now() >= deadline) { const k = dry ? c : await a.expire(id); did(c.pair_id, id, "expire", `${k.status} ${k.how}`); return; }
  if (!r.found && !dry) { await a.read(id, rnd); r = await a.cv("get_reading", [a.regAddr, id, rnd]); }
  if (r.found && !dry) { const k = await a.rule(id); did(c.pair_id, id, `rule round ${rnd}`, `${k.status} ${k.verdict || k.verdict1} ${k.reason}`); }
}

const pairs = (await a.rv("get_pairs", [0, 50])).pairs;
for (const p of pairs) {
  if (p.open) await advance(await a.check(p.open.check_id));
}
for (const p of (await a.rv("get_pairs", [0, 50])).pairs) {
  if (p.open_check) { did(p.pair_id, p.open_check, "monitor", "skipped: a check is open"); continue; }
  if (p.last_monitor_at && now() < p.last_monitor_at + cfg.monitor_interval_s) { did(p.pair_id, 0, "monitor", "skipped: rate limit"); continue; }
  let pins;
  try { pins = await a.pins(p.pair_id, 90); } catch (e) { did(p.pair_id, 0, "monitor", `skipped: could not pin (${String(e.message).slice(0, 80)})`); continue; }
  if (p.latest && JSON.stringify(Object.entries(p.latest.blocks).sort()) === JSON.stringify(Object.entries(pins.blocks).sort())) {
    did(p.pair_id, p.latest_check, "monitor", "skipped: no new finalized blocks since the latest ruling (chain halted)");
    continue;
  }
  if (dry) { did(p.pair_id, 0, "monitor", `would file at ${JSON.stringify(pins.blocks)}`); continue; }
  const m = await a.monitor(p.pair_id, pins.blocks);
  if (!m.ok) { did(p.pair_id, 0, "monitor", `failed: ${m.revertReason}`); continue; }
  await advance(await a.check(m.check_id));
}
writeFileSync(new URL("../docs/patrol-last.json", import.meta.url), JSON.stringify(out, null, 2) + "\n");
console.log(`patrol done: ${out.actions.length} actions`);
