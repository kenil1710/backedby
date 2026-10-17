# Final check

`node tools/final_check.mjs` on 2026-10-17 04:56 UTC at HEAD `9c7c9e4b71`
(contracts deployed from `e915d21e8a`).

**12/12 PASS.**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | source: on-chain code byte-identical to build files at the deploy commit | PASS | all deployments from one commit: e915d21e8a25e35c06baa614b5f234ccaf74b826 |
| 2 | source: build/ is current with contracts/ | PASS | tools/build.py --check |
| 3 | addresses: consistent across README, docs, site and tools | PASS | 5 contracts |
| 4 | links: every link in README and docs answers 200 | PASS | 140 links |
| 5 | seeds: every canonical pair has a FINAL ruling | PASS | 15 pairs, not final: [] |
| 6 | seeds: every real UNDER_BACKED from FEASIBILITY.md is seeded and ruled | PASS | 6 UNDER_BACKED rulings; missing [] |
| 7 | demo: drained to 0, invariant holds | PASS | held 0, received 140000000000000000, claimed 140000000000000000 |
| 8 | docs truth: RULES.md numbers equal the deployed get_config | PASS | 10 statements |
| 9 | tests: offline suite passes | PASS | 402 tests OK |
| 10 | site: /api/verify reports every contract identical | PASS | 5 contracts |
| 11 | site: /api/backed answers from chain | PASS | pair 1 BACKED FINAL |
| 12 | site: SVG badge renders | PASS | 516 bytes |
