// docs/SUBMISSION.md with character counts, plain ASCII enforced.
import { writeFileSync } from "node:fs";
const one = "BackedBy checks whether bridged tokens are actually backed: vault balance vs minted supply, read at pinned blocks on both chains, verdict by code.";
const desc = "BackedBy compares what a token's bridges hold in their Ethereum vaults with the supply minted on Arbitrum, OP, Base, Polygon or Moonbeam. Every vault and destination is proven by that bridge's own on-chain mapping; anyone can add a missing one. Each check pins one finalized block per chain. Validators independently read both chains at the pinned blocks, from two RPCs per chain, and must agree; any disagreement or error is INCONCLUSIVE and refunds every stake. Code computes every number and the verdict (BACKED if locked covers supply, else UNDER_BACKED); the model never decides, no model is called at all. Operators bond that a pair stays backed, anyone challenges with a stake, rulings are contestable for 6 h, and CollateralGate lets a lender refuse unbacked tokens. Seeded with 18 real pairs; it flags the 5 drained Nomad tokens.";
const review = "Open /verify: each contract's on-chain code is compared byte for byte with the build files at the deploy commit. Open any pair: every number links to the explorer at the pinned block. Run node tools/final_check.mjs: source, addresses, links, FINAL seeds, demo drained to 0, 440+ offline tests. docs/demo-run.log has every path on chain.";
for (const [n, t, max] of [["one-liner", one, 180], ["description", desc, 1000], ["review", review, 500]]) {
  if (!/^[\x20-\x7e]*$/.test(t)) throw new Error(n + " is not plain ASCII");
  if (t.length > max) throw new Error(`${n} is ${t.length} > ${max}`);
}
const md = `# Submission

Plain ASCII. Counts are characters, checked by \`node tools/submission.mjs\`.

## One-liner (${one.length} / 180)

${one}

## Description (${desc.length} / 1000)

${desc}

## Review verification (${review.length} / 500)

${review}

## Links

- Live: https://backedby-ledger.vercel.app
- Repository: https://github.com/kenil1710/backedby
- Rules: https://github.com/kenil1710/backedby/blob/main/docs/RULES.md
- Seeds: https://github.com/kenil1710/backedby/blob/main/docs/SEEDS.md
- Final check: https://github.com/kenil1710/backedby/blob/main/docs/FINAL_CHECK.md
`;
writeFileSync(new URL("../docs/SUBMISSION.md", import.meta.url), md);
console.log(one.length, desc.length, review.length);
