# Final check

`node tools/final_check.mjs` on 2026-10-17 18:46 UTC at HEAD `820ab99888`
(contracts deployed from `047d3406d5`).

**12/14 PASS.**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | source: on-chain code byte-identical to build files at the deploy commit | PASS | all deployments from one commit: 047d3406d5c78f4cbb1913012bd5df249998fcb5 |
| 2 | source: build/ is current with contracts/ | PASS | tools/build.py --check |
| 3 | addresses: consistent across README, docs, site and tools | PASS | 5 contracts |
| 4 | links: every link in README and docs answers 200 | PASS | 67 links |
| 5 | seeds: the USDT0 adapter's pair lists every destination two RPCs can read | PASS | pair 13: 14 destinations, undefined undefined |
| 6 | seeds: every pair FEASIBILITY.md read as UNDER_BACKED is seeded with a FINAL ruling | FAIL | missing [polygon USDT, nomad USDC, nomad WETH, nomad WBTC, nomad USDT, nomad DAI] |
| 7 | demo: drained to 0 by eth_getBalance, ledger agrees, invariant holds | PASS | eth_getBalance 0 wei, ledger held 0, received 150000000000000000, claimed 150000000000000000 |
| 8 | balances: every registry's eth_getBalance equals what its ledger holds | PASS | BackedByRegistry eth_getBalance 0 / ledger 0; BackedByRegistryDemo eth_getBalance 0 / ledger 0 |
| 9 | payouts: every demo payout arrived (finalized, delivered, not skipped; registry balance down by the amount) | PASS | operator 70000000000000000 wei -> 0x00BB59efE7cD069Df92C711EF80908473A36b814 tx 0x4470cb24; challenger 55000000000000000 wei -> 0xfE86fC89b5a04D699198d03Afe4b0686aCF5C0d6 tx 0x73a2a898; treasury 25000000000000000 wei -> 0x8c47a9AD90Ab7aEF4e160d274bb6f0782fb3071E tx 0x89cea086 |
| 10 | docs truth: RULES.md numbers equal the deployed get_config | PASS | 10 statements |
| 11 | tests: offline suite passes | PASS | 479 tests (467 Python, 12 node) OK |
| 12 | site: /api/verify reports every contract identical | PASS | 5 contracts |
| 13 | site: /api/backed answers from chain | FAIL | no ruling |
| 14 | site: SVG badge renders | PASS | 512 bytes |
