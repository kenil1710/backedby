# Superseded: deployment from 6f9431f

Records of the second deployment (contracts from commit `6f9431f`), kept as they were. Two things in it were wrong:

- **Payouts never arrived.** `claim()` paid with an internal `emit_transfer`. Studio Dev stored each one with a
  declared budget of 0, marked it skipped at finalization and credited the value back to the registry. The demo
  ledger therefore said "drained to 0" (`held_now` 0, `claimed` 0.14 GEN) while the demo registry's `eth_getBalance`
  still held all 0.14 GEN; the first demo claim,
  [`0x71e5cc09…`](https://explorer-studio-dev.genlayer.com/tx/0x71e5cc0942fedec01abdcf560fc1ca02bf89a91c451483ba66c81baf8c2d90df),
  records `skipped: true, declaredBudget: 0, skippedRefunded`. Probes and the fix: docs/PAYOUT_PROBE.md.
- **USDT0's adapter was judged against 3 of its chains.** The USDT pair counted USDT0 on Polygon, Arbitrum and OP
  Mainnet only, though the adapter backs it on every chain it has a LayerZero peer on; its 199.16% left that supply out.

Both were fixed and every contract was redeployed from one commit and re-seeded; the current records are in docs/.
These contracts are no longer referenced; their addresses appear only in this folder.
