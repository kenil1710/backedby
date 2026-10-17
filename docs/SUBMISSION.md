# Submission

Plain ASCII. Counts are characters, checked by `node tools/submission.mjs`.

## One-liner (146 / 180)

BackedBy checks whether bridged tokens are actually backed: vault balance vs minted supply, read at pinned blocks on both chains, verdict by code.

## Description (850 / 1000)

BackedBy compares what a token's bridges hold in their Ethereum vaults with the supply minted on 16 chains (Arbitrum, OP, Base, Polygon, Moonbeam and 11 USDT0 chains). Every vault and destination is proven by that bridge's own on-chain mapping, and a vault is judged against every chain it backs. Each check pins one finalized block per chain; validators read both chains from two RPCs each and must agree, or it is INCONCLUSIVE and refunds every stake. Code computes every number and the verdict (BACKED if locked covers supply, else UNDER_BACKED); no model is called. Operators bond that a pair stays backed, anyone challenges with a stake, rulings are contestable for 6 h, and CollateralGate lets a lender refuse unbacked tokens. Payouts are real GEN transfers, each proved on chain. Seeded with 18 real pairs; it flags the 5 drained Nomad tokens.

## Review verification (392 / 500)

Open /verify: each contract's on-chain code is compared byte for byte with the build files at the deploy commit. Open any pair: every number links to the explorer at the pinned block. Run node tools/final_check.mjs: source, addresses, links, FINAL seeds, each demo payout re-read from chain, eth_getBalance of every registry (demo 0), offline tests. docs/demo-run.log has every path on chain.

## Links

- Live: https://backedby-ledger.vercel.app
- Repository: https://github.com/kenil1710/backedby
- Rules: https://github.com/kenil1710/backedby/blob/main/docs/RULES.md
- Seeds: https://github.com/kenil1710/backedby/blob/main/docs/SEEDS.md
- Final check: https://github.com/kenil1710/backedby/blob/main/docs/FINAL_CHECK.md
