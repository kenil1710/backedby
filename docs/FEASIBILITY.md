# Feasibility (Step 0)

Read on 2026-10-16 21:49 UTC with plain JSON-RPC (`node tools/feasibility.mjs`, raw data in
[`feasibility.json`](feasibility.json)). Nothing here came from an indexer or an API: every number is an `eth_call`
at one pinned finalized block per chain, sent to **two RPCs run by different operators**, and kept only when both
answered byte-for-byte the same.

**Result: 36 pairs authenticated and readable, 6 real UNDER_BACKED, 3 refused.**
Both RPCs agreed on every value of every authenticated pair: yes.

## RPCs (two per chain)

| Chain | RPC A | RPC B | Archive reads |
|---|---|---|---|
| ethereum | https://eth-pokt.nodies.app | https://rpc.mevblocker.io | both serve state 72 h+ back |
| arbitrum | https://arb-pokt.nodies.app | https://arbitrum.gateway.tenderly.co | both serve state 72 h+ back |
| optimism | https://mainnet.optimism.io | https://optimism.drpc.org | both serve state 72 h+ back |
| base | https://base-pokt.nodies.app | https://base.drpc.org | both serve state 72 h+ back |
| polygon | https://polygon.drpc.org | https://polygon.gateway.tenderly.co | both serve state 72 h+ back |
| moonbeam | https://moonbeam.drpc.org | https://moonbeam.api.onfinality.io/public | both serve state 72 h+ back |

Probed and rejected (no archive state, key required, batch refused, or down): mainnet.base.org (answers from a laptop but
not from GenVM validators on Studio Dev; replaced by base-pokt.nodies.app), publicnode (archive needs a token),
arb1.arbitrum.io (state pruned after ~6 h, too short for a 6 h contest window), arbitrum.drpc.org, 1rpc.io,
polygon-rpc.com, llamarpc, cloudflare-eth, blastapi (shut down), ankr (key), blockpi (key), omniatech (down),
moonbeam.unitedbloc / rpc.api.moonbeam.network (unreachable). dRPC's free tier caps a JSON-RPC batch at 3 calls;
ChainReader splits batches to that size.

## Pinned blocks

One block per chain, chosen by `tools/lib/pin.mjs` and re-checked by the same rules the contract applies: both
finalized, the Ethereum (locked) block at or after the destination block, gap at most 10 minutes.

| Destination | Ethereum block | Destination block | Gap |
|---|---|---|---|
| arbitrum | [26207828](https://etherscan.io/block/26207828) 2026-10-16T21:35:59Z | [515495977](https://arbitrum.blockscout.com/block/515495977) 2026-10-16T21:35:49Z | 10 s |
| optimism | [26207781](https://etherscan.io/block/26207781) 2026-10-16T21:26:35Z | [158293607](https://optimism.blockscout.com/block/158293607) 2026-10-16T21:26:31Z | 4 s |
| base | [26207794](https://etherscan.io/block/26207794) 2026-10-16T21:29:11Z | [52698397](https://basescan.org/block/52698397) 2026-10-16T21:29:01Z | 10 s |
| polygon | [26207830](https://etherscan.io/block/26207830) 2026-10-16T21:36:23Z | [95654159](https://polygon.blockscout.com/block/95654159) 2026-10-16T21:36:23Z | 0 s |
| moonbeam | [25724334](https://etherscan.io/block/25724334) 2026-08-10T11:35:59Z | [16796696](https://moonbeam.subscan.io/block/16796696) 2026-08-10T11:35:57Z | 2 s |

**Moonbeam has not produced a block since 2026-08-10T11:35:57Z.** Three unrelated RPCs (dRPC,
OnFinality, 1RPC) report the same head, `16796699`; its finalized block is
`16796696`. The rules still work: the Ethereum block is pinned to the first block after
Moonbeam's last finalized one (gap 2 s). A check on a Nomad pair is therefore always about that
moment, which is why CollateralGate (max age) refuses it as stale on top of UNDER_BACKED.

## Pairs

Ratio = locked / summed destination supply, both normalized to 18 decimals. Verdict at 0 bps tolerance.

| # | Bridge | Token | Vault (Ethereum) | Destination token | Dec (src/dst) | Locked | Supply | Ratio | Both RPCs agree | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | arbitrum | USDC | [0xcee2...180d](https://etherscan.io/address/0xcee284f754e854890e311e3280b767f80797180d) | [0xff97...5cc8](https://arbitrum.blockscout.com/address/0xff970a61a04b1ca14834a43f5de4533ebddb5cc8) (arbitrum) | 6/6 | 48,936,975.40 | 47,573,281.85 | 1.0287 | yes | **BACKED** |
| 2 | arbitrum | DAI | [0xa10c...9400](https://etherscan.io/address/0xa10c7ce4b876998858b1a9e12b10092229539400) | [0xda10...0da1](https://arbitrum.blockscout.com/address/0xda10009cbd5d07dd0cecc66161fc93d7c9000da1) (arbitrum) | 18/18 | 17,052,552.38 | 17,047,498.62 | 1.0003 | yes | **BACKED** |
| 3 | arbitrum | WBTC | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0x2f2a...5b0f](https://arbitrum.blockscout.com/address/0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f) (arbitrum) | 8/8 | 7,385.69 | 7,326.55 | 1.0081 | yes | **BACKED** |
| 4 | arbitrum | LINK | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0xf97f...9fb4](https://arbitrum.blockscout.com/address/0xf97f4df75117a78c1a5a0dbb814af92458539fb4) (arbitrum) | 18/18 | 1,880,809.89 | 1,872,424.20 | 1.0045 | yes | **BACKED** |
| 5 | arbitrum | UNI | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0xfa7f...f7f0](https://arbitrum.blockscout.com/address/0xfa7f8980b0f1e64a2062791cc3b0871572f1f7f0) (arbitrum) | 18/18 | 1,084,357.14 | 1,052,172.74 | 1.0306 | yes | **BACKED** |
| 6 | arbitrum | AAVE | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0xba5d...7196](https://arbitrum.blockscout.com/address/0xba5ddd1f9d7f570dc94a51479a000e3bce967196) (arbitrum) | 18/18 | 49,795.58 | 49,025.74 | 1.0157 | yes | **BACKED** |
| 7 | arbitrum | CRV | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0x11cd...4978](https://arbitrum.blockscout.com/address/0x11cdb42b0eb46d95f990bedd4695a6e3fa034978) (arbitrum) | 18/18 | 19,751,434.84 | 19,733,958.35 | 1.0009 | yes | **BACKED** |
| 8 | arbitrum | LDO | [0xa3a7...0eec](https://etherscan.io/address/0xa3a7b6f88361f48403514059f1f16c8e78d60eec) | [0x13ad...fa60](https://arbitrum.blockscout.com/address/0x13ad51ed4f1b7e9dc168d8a00cb3f4ddd85efa60) (arbitrum) | 18/18 | 1,596,736.36 | 1,592,291.03 | 1.0028 | yes | **BACKED** |
| 9 | arbitrum | wstETH | [0x0f25...8e5a](https://etherscan.io/address/0x0f25c1dc2a9922304f2eac71dca9b07e310e8e5a) | [0x5979...0529](https://arbitrum.blockscout.com/address/0x5979d7b546e38e414f7e9822514be443a4800529) (arbitrum) | 18/18 | 45,532.62 | 45,379.82 | 1.0034 | yes | **BACKED** |
| 10 | optimism | USDC | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x7f5c...1607](https://optimism.blockscout.com/address/0x7f5c764cbc14f9669b88837ca1490cca17c31607) (optimism) | 6/6 | 25,676,683.13 | 20,952,458.82 | 1.2255 | yes | **BACKED** |
| 11 | optimism | USDT | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x94b0...8e58](https://optimism.blockscout.com/address/0x94b008aa00579c1307b0ef2c499ad98a8ce58e58) (optimism) | 6/6 | 421,062,075.51 | 301,671,941.03 | 1.3958 | yes | **BACKED** |
| 12 | optimism | WBTC | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x68f1...2095](https://optimism.blockscout.com/address/0x68f180fcce6836688e9084f035309e29bf0a2095) (optimism) | 8/8 | 524.19 | 516.49 | 1.0149 | yes | **BACKED** |
| 13 | optimism | LINK | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x350a...a7f6](https://optimism.blockscout.com/address/0x350a791bfc2c21f9ed5d10980dad2e2638ffa7f6) (optimism) | 18/18 | 180,821.54 | 175,493.69 | 1.0304 | yes | **BACKED** |
| 14 | optimism | UNI | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x6fd9...6691](https://optimism.blockscout.com/address/0x6fd9d7ad17242c41f7131d257212c54a0e816691) (optimism) | 18/18 | 79,360.24 | 71,939.56 | 1.1032 | yes | **BACKED** |
| 15 | optimism | AAVE | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x76fb...9278](https://optimism.blockscout.com/address/0x76fb31fb4af56892a25e32cfc43de717950c9278) (optimism) | 18/18 | 4,825.73 | 4,736.29 | 1.0189 | yes | **BACKED** |
| 16 | optimism | CRV | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0x0994...fb53](https://optimism.blockscout.com/address/0x0994206dfe8de6ec6920ff4d779b0d950605fb53) (optimism) | 18/18 | 6,479,835.87 | 6,466,091.77 | 1.0021 | yes | **BACKED** |
| 17 | optimism | LDO | [0x99c9...4be1](https://etherscan.io/address/0x99c9fc46f92e8a1c0dec1b1747d010903e884be1) | [0xfdb7...735f](https://optimism.blockscout.com/address/0xfdb794692724153d1488ccdbe0c56c252596735f) (optimism) | 18/18 | 228,881.24 | 225,439.46 | 1.0153 | yes | **BACKED** |
| 18 | op_dai | DAI | [0x4671...6c65](https://etherscan.io/address/0x467194771dae2967aef3ecbedd3bf9a310c76c65) | [0xda10...0da1](https://optimism.blockscout.com/address/0xda10009cbd5d07dd0cecc66161fc93d7c9000da1) (optimism) | 18/18 | 19,888,231.68 | 13,572,283.08 | 1.4654 | yes | **BACKED** |
| 19 | base | USDC | [0x3154...2c35](https://etherscan.io/address/0x3154cf16ccdb4c6d922629664174b904d80f2c35) | [0xd9aa...b6ca](https://basescan.org/address/0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca) (base) | 6/6 | 6,545,555.14 | 5,472,277.73 | 1.1961 | yes | **BACKED** |
| 20 | base | DAI | [0x3154...2c35](https://etherscan.io/address/0x3154cf16ccdb4c6d922629664174b904d80f2c35) | [0x50c5...b0cb](https://basescan.org/address/0x50c5725949a6f0c72e6c4a641f24049a917db0cb) (base) | 18/18 | 1,920,416.49 | 1,916,112.25 | 1.0022 | yes | **BACKED** |
| 21 | base | cbETH | [0x3154...2c35](https://etherscan.io/address/0x3154cf16ccdb4c6d922629664174b904d80f2c35) | [0x2ae3...ec22](https://basescan.org/address/0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22) (base) | 18/18 | 90,444.46 | 90,277.93 | 1.0018 | yes | **BACKED** |
| 22 | base | rETH | [0x3154...2c35](https://etherscan.io/address/0x3154cf16ccdb4c6d922629664174b904d80f2c35) | [0xb6fe...624c](https://basescan.org/address/0xb6fe221fe9eef5aba221c348ba20a1bf5e73624c) (base) | 18/18 | 1,892.07 | 1,881.73 | 1.0055 | yes | **BACKED** |
| 23 | polygon | USDC | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0x2791...4174](https://polygon.blockscout.com/address/0x2791bca1f2de4661ed88a30c99a7a9449aa84174) (polygon) | 6/6 | 1,005,643,573.84 | 1,004,077,999.31 | 1.0016 | yes | **BACKED** |
| 24 | polygon | USDT | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0xc213...8e8f](https://polygon.blockscout.com/address/0xc2132d05d31c914a87c6611c10748aeb04b58e8f) (polygon) | 6/6 | 4,645,097.76 | 717,234,035.23 | 0.0065 | yes | **UNDER_BACKED** |
| 25 | polygon | DAI | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0x8f3c...a063](https://polygon.blockscout.com/address/0x8f3cf7ad23cd3cadbd9735aff958023239c6a063) (polygon) | 18/18 | 443,860,171.74 | 443,563,208.68 | 1.0007 | yes | **BACKED** |
| 26 | polygon | WBTC | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0x1bfd...bfd6](https://polygon.blockscout.com/address/0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6) (polygon) | 8/8 | 1,924.50 | 1,924.06 | 1.0002 | yes | **BACKED** |
| 27 | polygon | LINK | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0x53e0...ad39](https://polygon.blockscout.com/address/0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39) (polygon) | 18/18 | 1,131,964.92 | 1,130,772.19 | 1.0011 | yes | **BACKED** |
| 28 | polygon | AAVE | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0xd6df...c90b](https://polygon.blockscout.com/address/0xd6df932a45c0f255f85145f286ea0b292b21c90b) (polygon) | 18/18 | 69,747.28 | 59,361.75 | 1.1750 | yes | **BACKED** |
| 29 | polygon | UNI | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0xb33e...180f](https://polygon.blockscout.com/address/0xb33eaad8d922b1083446dc23f610c2567fb5180f) (polygon) | 18/18 | 251,116.30 | 250,740.64 | 1.0015 | yes | **BACKED** |
| 30 | polygon | CRV | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0x1723...10af](https://polygon.blockscout.com/address/0x172370d5cd63279efa6d502dab29171933a610af) (polygon) | 18/18 | 4,467,217.80 | 4,458,293.12 | 1.0020 | yes | **BACKED** |
| 31 | polygon | LDO | [0x40ec...bbdf](https://etherscan.io/address/0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf) | [0xc3c7...8756](https://polygon.blockscout.com/address/0xc3c7d422809852031b44ab29eec9f1eff2a58756) (polygon) | 18/18 | 1,401,925.72 | 1,390,180.51 | 1.0084 | yes | **BACKED** |
| 32 | nomad | USDC | [0x88a6...30a3](https://etherscan.io/address/0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3) | [0x8f55...1ec9](https://moonbeam.subscan.io/account/0x8f552a71efe5eefc207bf75485b356a0b3f01ec9) (moonbeam) | 6/6 | 3,720.84 | 2,114,959.15 | 0.0018 | yes | **UNDER_BACKED** |
| 33 | nomad | WETH | [0x88a6...30a3](https://etherscan.io/address/0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3) | [0x30d2...16a7](https://moonbeam.subscan.io/account/0x30d2a9f5fdf90ace8c17952cbb4ee48a55d916a7) (moonbeam) | 18/18 | 0.54 | 603.88 | 0.0009 | yes | **UNDER_BACKED** |
| 34 | nomad | WBTC | [0x88a6...30a3](https://etherscan.io/address/0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3) | [0x1dc7...95e0](https://moonbeam.subscan.io/account/0x1dc78acda13a8bc4408b207c9e48cdbc096d95e0) (moonbeam) | 8/8 | 0.00 | 7.56 | 0.0000 | yes | **UNDER_BACKED** |
| 35 | nomad | USDT | [0x88a6...30a3](https://etherscan.io/address/0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3) | [0x8e70...e594](https://moonbeam.subscan.io/account/0x8e70cd5b4ff3f62659049e74b6649c6603a0e594) (moonbeam) | 6/6 | 0.00 | 77,774.57 | 0.0000 | yes | **UNDER_BACKED** |
| 36 | nomad | DAI | [0x88a6...30a3](https://etherscan.io/address/0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3) | [0xc234...2413](https://moonbeam.subscan.io/account/0xc234a67a4f840e61ade794be47de455361b52413) (moonbeam) | 18/18 | 0.00 | 510,151.43 | 0.0000 | yes | **UNDER_BACKED** |

## Refused candidates (not authenticated by the bridge's own mapping)

| Bridge | Token | Destination | Why |
|---|---|---|---|
| arbitrum | USDT | - | router has no gateway for this token |
| base | LINK | - | remote token is not the source token |
| optimism | USDC | native USDC on OP, not a bridge token | remote token is not the source token |

- **Arbitrum USDT**: the L1 router no longer has a gateway for USDT (Arbitrum's USDT moved to USDT0, a LayerZero OFT);
  there is no canonical-bridge pair to check.
- **Base LINK**: `0x88Fb...6e196` does not report Ethereum LINK as its remote token; it is not a Standard Bridge token.
- **OP "USDC" 0x0b2c...ff85** (deliberate fake): Circle's native USDC, not minted by any bridge; passing it off as the
  destination of the Ethereum USDC vault is refused.

## How each pair is authenticated

| Bridge | On-chain proof (all read from both RPCs) | Vault |
|---|---|---|
| Arbitrum | L1GatewayRouter `getGateway(l1)` and `calculateL2TokenAddress(l1)`; L2GatewayRouter `calculateL2TokenAddress(l1)` must equal it | the gateway, or `gateway.l1Escrow()` when it has one (DAI) |
| Optimism / Base | the L2 token's `remoteToken()` (or legacy `l1Token()`) is the source token and its `bridge()` (or `l2Bridge()`) is the L2StandardBridge `0x4200...0010` | that chain's L1StandardBridge |
| Optimism DAI | L1DAITokenBridge `l1Token/l2Token/escrow`; L2DAITokenBridge `l1Token/l2Token/l1DAITokenBridge` | `L1DAITokenBridge.escrow()` |
| Polygon PoS | RootChainManager `rootToChildToken(l1)`; ChildChainManager `childToRootToken(child)` must point back | `typeToPredicate(tokenToType(l1))` (ERC20Predicate) |
| Nomad | Moonbeam BridgeRouter `tokenRegistry()`, TokenRegistry `getTokenId(rep) = (eth, l1)` and `getLocalAddress(eth, l1) = rep`; Moonbeam BridgeRouter `remotes(eth)`; Ethereum TokenRegistry `getTokenId(l1)` is local | `remotes(eth)`: the Ethereum BridgeRouter |

## What the UNDER_BACKED rows are

- **polygon USDT**: 4,645,097.76 locked against 717,234,035.23 outstanding (ratio 0.006476).
- **nomad USDC**: 3,720.84 locked against 2,114,959.15 outstanding (ratio 0.001759).
- **nomad WETH**: 0.54 locked against 603.88 outstanding (ratio 0.000895).
- **nomad WBTC**: 0.00 locked against 7.56 outstanding (ratio 0.000000).
- **nomad USDT**: 0.00 locked against 77,774.57 outstanding (ratio 0.000000).
- **nomad DAI**: 0.00 locked against 510,151.43 outstanding (ratio 0.000000).

The five Nomad rows are the August 2022 exploit: the Ethereum BridgeRouter was drained, and the Moonbeam
representations kept circulating with almost nothing behind them. Polygon USDT is not an exploit: its child token on
Polygon is now also minted by USDT0's LayerZero adapter, so most of its supply is no longer locked in the PoS
bridge's ERC20Predicate. By the rule BackedBy enforces (the canonical vault against the canonical token's supply) it is
UNDER_BACKED, and the contract will say so; the README explains why that is the honest reading.

## Decision

Feasible: 36 readable pairs (need 10+), 6 real UNDER_BACKED (need 1+). Continue with all six bridge
kinds; seed the canonical registry with a mix of BACKED pairs and every UNDER_BACKED one.
