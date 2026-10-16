# Submission

Plain ASCII. Counts are characters, checked by `node tools/submission.mjs`.

## One-liner (146 / 180)

BackedBy checks whether bridged tokens are actually backed: vault balance vs minted supply, read at pinned blocks on both chains, verdict by code.

## Description (807 / 1000)

BackedBy compares what a bridge holds in its Ethereum vault with the supply it minted on Arbitrum, OP, Base, Polygon or Moonbeam. A pair exists only if the bridge's own on-chain mapping proves it. Each check pins one finalized block per chain. Validators independently read both chains at the pinned blocks, from two RPCs per chain, and must agree; any disagreement or error is INCONCLUSIVE and refunds every stake. Code computes every number and the verdict (BACKED if locked covers supply, else UNDER_BACKED); the model never decides, no model is called at all. Operators bond that a pair stays backed, anyone challenges with a stake, rulings are contestable for 6 h, and CollateralGate lets a lender refuse unbacked tokens. Seeded with 15 real pairs; it flags the 5 drained Nomad tokens and Polygon USDT.

## Review verification (336 / 500)

Open /verify: each contract's on-chain code is compared byte for byte with the build files at the deploy commit. Open any pair: every number links to the explorer at the pinned block. Run node tools/final_check.mjs: source, addresses, links, FINAL seeds, demo drained to 0, 400+ offline tests. docs/demo-run.log has every path on chain.

## Links

- Live: https://backedby-ledger.vercel.app
- Repository: https://github.com/kenil1710/backedby
- Rules: https://github.com/kenil1710/backedby/blob/main/docs/RULES.md
- Seeds: https://github.com/kenil1710/backedby/blob/main/docs/SEEDS.md
- Final check: https://github.com/kenil1710/backedby/blob/main/docs/FINAL_CHECK.md
