# Final check

`node tools/final_check.mjs` on 2026-10-17 00:07 UTC at HEAD `4ce5ee123c`
(contracts deployed from `e915d21e8a`).

**8/12 PASS.**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | source: on-chain code byte-identical to build files at the deploy commit | PASS | all deployments from one commit: e915d21e8a25e35c06baa614b5f234ccaf74b826 |
| 2 | source: build/ is current with contracts/ | PASS | tools/build.py --check |
| 3 | addresses: consistent across README, docs, site and tools | PASS | 5 contracts |
| 4 | links: every link in README and docs answers 200 | FAIL | 403 https://arbiscan.io/block/515495977; ERR https://moonscan.io/block/16796696; 403 https://arbiscan.io/address/0xf97f4df75117a78c1a5a0dbb814af92458539fb4; 403 https://arbiscan.io/address/0xda10009cbd5d07dd0cecc66161fc93d7c9000da1; 403 https://arbiscan.io/address/0xff970a61a04b1ca14834a43f5de4533eb |
| 5 | seeds: every canonical pair has a FINAL ruling | FAIL | 15 pairs, not final: [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15] |
| 6 | seeds: every real UNDER_BACKED from FEASIBILITY.md is seeded and ruled | FAIL | 0 UNDER_BACKED rulings; missing [] |
| 7 | demo: drained to 0, invariant holds | PASS | held 0, received 140000000000000000, claimed 140000000000000000 |
| 8 | docs truth: RULES.md numbers equal the deployed get_config | PASS | 10 statements |
| 9 | tests: offline suite passes | PASS | 402 tests OK |
| 10 | site: /api/verify reports every contract identical | PASS | 5 contracts |
| 11 | site: /api/backed answers from chain | FAIL | no ruling |
| 12 | site: SVG badge renders | PASS | 512 bytes |
