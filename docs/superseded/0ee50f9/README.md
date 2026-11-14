# Superseded: the first v2 deployment (contracts from 0ee50f9)

Kept as they were: the canonical seed run (stopped at 24 of 29 pairs), the demo run and its payouts. The demo found
H6 (docs/ATTACK_REPORT.md): on Studio's runner a long string field read through a stale struct reference comes back
corrupted, so `rule` could not run on the large USDT pair (demo check 4). Everything was fixed, redeployed from one
commit and re-seeded. The demo registry here was drained to `eth_getBalance` 0 (3/3 payouts proved on chain).

| Contract | Address |
|---|---|
| ChainReader | `0xC9007829E329c2170Db93AfA8a490Ad1f7393b5C` |
| BackedByRegistry | `0x40dDb09B6bB789562127A829c87Cf361D8012557` |
| BackedByRegistryDemo | `0xACf1d85bF09a50078ac422A3af69eAe8B10AB384` |
| CollateralGate | `0xf1CBE123DA97c9E6B0Db7BE945a816880870677C` |
| CollateralGateDemo | `0x9a75bB17C9b27Ab746c06B3bba47D86C2cb7DE8C` |
