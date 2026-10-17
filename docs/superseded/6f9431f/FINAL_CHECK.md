# Final check

`node tools/final_check.mjs` on 2026-10-17 14:08 UTC at HEAD `4aeb05ecb0`
(contracts deployed from `6f9431f901`).

**11/11 PASS.**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | source: on-chain code byte-identical to build files at the deploy commit | PASS | all deployments from one commit: 6f9431f901d3b3006b25a93c42954b593abc2307 |
| 2 | source: build/ is current with contracts/ | PASS | tools/build.py --check |
| 3 | addresses: consistent across README, docs, site and tools | PASS | 5 contracts |
| 4 | links: every link in README and docs answers 200 | PASS | 160 links |
| 5 | seeds: every pair FEASIBILITY.md read as UNDER_BACKED is seeded with a FINAL ruling | PASS | polygon USDT: BACKED; nomad USDC: UNDER_BACKED; nomad WETH: UNDER_BACKED; nomad WBTC: UNDER_BACKED; nomad USDT: UNDER_BACKED; nomad DAI: UNDER_BACKED |
| 6 | demo: drained to 0, invariant holds | PASS | held 0, received 140000000000000000, claimed 140000000000000000 |
| 7 | docs truth: RULES.md numbers equal the deployed get_config | PASS | 10 statements |
| 8 | tests: offline suite passes | PASS | 442 tests OK |
| 9 | site: /api/verify reports every contract identical | PASS | 5 contracts |
| 10 | site: /api/backed answers from chain | PASS | pair 1 BACKED FINAL |
| 11 | site: SVG badge renders | PASS | 516 bytes |
