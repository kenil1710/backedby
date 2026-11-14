# Rules

Every rule here is code in `contracts/` (built into `build/` and deployed byte for byte). The numbers are the
contracts' own constants, readable live through each contract's `get_config` and on the site at `/docs`.
No model is asked anything at any step.

## 1. Pairs exist only if the bridge says so

A **pair** is: a source chain (always Ethereum), a source token, **1 to 8 vaults** there whose balances of the source
token are summed ("locked"), and **1 to 16 destination tokens** whose supplies are summed. Vaults and destinations are
symmetric: a token with a second mint path (Polygon's USDT is minted both by the PoS bridge and by USDT0's LayerZero
adapter) is only judged fairly when every vault that backs it is counted, so anyone can add a missing vault, exactly
as anyone can add a missing destination. `ChainReader.authenticate(kind, source_token, dest_token)` reads the bridge's own mapping on
both chains, from both RPCs of each, at the latest finalized blocks, and records the pair only if the mapping proves
it. Otherwise the call is refused.

| Bridge (`kind`) | What must hold on chain | Vault |
|---|---|---|
| `arbitrum` | L1GatewayRouter `getGateway(l1)` is one of the four **escrow** gateways (standard L1ERC20Gateway, L1DaiGateway, L1USDCGateway, Lido wstETH gateway); `calculateL2TokenAddress(l1)` on the L1 router **and** on the L2 router is the destination token | the gateway, or `gateway.l1Escrow()` |
| `optimism`, `base` | the destination's `remoteToken()` (legacy `l1Token()`) is the source token and its `bridge()` (legacy `l2Bridge()`) is the L2StandardBridge `0x4200…0010` | that chain's L1StandardBridge |
| `op_dai` | L1DAITokenBridge `l1Token/l2Token/escrow`; L2DAITokenBridge `l1Token/l2Token/l1DAITokenBridge` point at each other | `L1DAITokenBridge.escrow()` |
| `polygon` | RootChainManager `rootToChildToken(l1)` is the destination, `tokenToType(l1)` is `keccak256("ERC20")`, ChildChainManager `childToRootToken(child)` is the source | `typeToPredicate(ERC20)` |
| `nomad` | the Moonbeam BridgeRouter's `tokenRegistry()` maps the representation to (Ethereum domain, source token) both ways, its `remotes(Ethereum)` is the Ethereum BridgeRouter, and the Ethereum TokenRegistry says the source token is local | the Ethereum BridgeRouter |
| `wh_polygon`, `wh_arbitrum`, `wh_optimism`, `wh_base` (Wormhole Portal) | Ethereum's token bridge `0x3ee1…a585` `bridgeContracts(<wormhole chain>)` is that chain's token bridge; that bridge's `wrappedAsset(2, l1)` is the destination token, `isWrappedAsset(dest)` is true and `bridgeContracts(2)` is Ethereum's bridge; the token's `chainId()` is 2 and `nativeContract()` is the source token | Ethereum's token bridge; its own ledger `outstandingBridged(l1)` is counted (section 4) |
| `ccip_<chain>` (Chainlink CCIP, 12 chains) | Ethereum's TokenAdminRegistry `getPool(l1)` is a pool whose `typeAndVersion()` starts `LockReleaseTokenPool `, whose `getToken()` is the source token, whose `getRemoteToken(<selector>)` is the destination and whose `isRemotePool(<selector>, <dest pool>)` is true; the destination chain's registry `getPool(dest)` is a `BurnMintTokenPool` / `BurnFromMintTokenPool` / `BurnWithFromMintTokenPool` whose `getToken()` is the destination, whose `getRemoteToken(Ethereum)` is the source token and whose `isRemotePool(Ethereum, <source pool>)` is true | the lock-release pool |
| `oft_<chain>` (LayerZero OFT, e.g. USDT0, weETH, WBTC, rsETH; 15 chains) | the destination token's `oftContract()` (or the token itself, for a native OFT) is an OFT whose `peers(Ethereum)` is the Ethereum adapter, whose `token()` is the destination token, and whose `endpoint()` is the LayerZero EndpointV2; the adapter's `token()` is the source token, its `endpoint()` is EndpointV2 and its `peers(<this chain>)` is that OFT | the adapter, **derived** from the destination token, never supplied |

- **Registration** (`register_pair(auth_ids, tolerance_bps, label)`): every authentication must be at most 1 hour old,
  and all of one vault and one source token. The **tolerance** (0 to 1000 bps) and every token's **decimals** are
  frozen in the pair's terms. Tolerance is part of the pair's identity: one vault and token can have several pairs
  that differ only in tolerance, so nobody can squat a pair with lax terms.
- **Missing destinations** (`add_destination(pair, auth_id)`): anyone can add a destination proved through one of the
  pair's vaults, so an operator cannot hide supply by leaving one out.
- **Missing vaults** (`add_vault(pair, auth_id)`): anyone can add a vault whose authentication proves it backs one of
  the pair's destination tokens (same source token, same decimals). Refused: an unauthenticated vault, a vault already
  in the pair, a vault already in another pair of the same tolerance, a vault that maps to a token the pair does not
  have, and a ninth vault. A fake adapter cannot get in: the adapter is derived from the destination token's own
  `oftContract()` and that OFT's `peers(Ethereum)`, so an attacker's adapter only ever authenticates against the
  attacker's own token, which is not a destination of the pair.
- **Snapshots.** A check uses the vaults, destinations, anchors and max gap the pair had **when it was filed**.
- **Anchors.** Each authentication also records its mapping calls and the exact words they returned. Every check
  re-reads every anchor at its own pinned blocks; if any changed (the bridge moved its escrow or remapped the token),
  the check is `INCONCLUSIVE · MAPPING_CHANGED` and nobody is slashed.
- **OP Stack ledger.** For `optimism` and `base` destinations the L1StandardBridge keeps its own per-token ledger,
  `deposits(l1, l2)`: it goes up when a deposit is locked on Ethereum and down when a withdrawal is paid out there, and
  the bridge refuses to pay out more than it holds for that pair. Such a destination counts as
  **`max(totalSupply, deposits)`** at the pinned blocks. See "Why max" below.

### Why `max(totalSupply, deposits)` and not `min`

The first version counted `min(totalSupply, deposits)`, to stop a lookalike token (one that answers `remoteToken()`
and `bridge()` correctly but mints outside the bridge) from inflating supply. That could **hide** under-backing: a
withdrawal burned on L2 lowers `totalSupply` at once, but stays in `deposits` until it is paid on Ethereum days later.
With 100 locked, 60 in supply and 50 burned-but-unpaid, the vault owes 110 and holds 100, yet `min` counted 60 and
said BACKED. It was changed.

`counted = max(totalSupply, deposits)` cannot hide under-backing:

- What the vault can be made to pay for a token is at most `deposits` (pending withdrawals plus everything still
  redeemable), and `counted >= deposits`.
- What holders of the token hold is `totalSupply`, and `counted >= totalSupply`.
- So `locked >= sum(counted)` implies the vault covers both its ledger and every unit in circulation. The rule can
  only err towards UNDER_BACKED, never towards BACKED.

It is also exact in flight: a deposit raises the vault balance and `deposits` in the same Ethereum transaction, and a
paid withdrawal lowers both in the same transaction, so neither direction moves the ratio. Measured on every OP and
Base pair in docs/FEASIBILITY.md, the vault balance equals or exceeds `deposits` to the wei (OP WBTC, AAVE, CRV and LDO
match exactly). A lookalike token that mints outside the bridge is now counted in full: its holders can submit
withdrawals the vault can never pay, so UNDER_BACKED is the true verdict for any pair that includes it. An operator
bonding an OP or Base pair accepts that anyone can deploy such a token and add it.

## 2. One finalized block per chain, source last

A check pins one block on Ethereum and one on each destination chain (`{"ethereum": n, "<chain>": m}`, exactly those
chains). The code requires:

1. every pinned block is at or below the **finalized** block of **both** RPCs of its chain (as each validator sees it);
2. the Ethereum (locked) block's timestamp is **at or after** every destination block's timestamp;
3. the Ethereum timestamp minus the **oldest** destination timestamp is **at most 600 s** (300 s for Polygon, **120 s**
   for any pair holding a LayerZero OFT vault or destination).

A filing that breaks 1-3 is INCONCLUSIVE with the stake refunded. For a challenge, the Ethereum block must also be
inside the bond's coverage (at or after the bond started, at or before an unbond request).

### Why this order makes in-flight transfers look over-backed, never under

Write `S` for the Ethereum block time and `D` for a destination block time, with `D <= S <= D + gap`.

- **Deposits** lock on Ethereum at time `l` and mint on the destination at `m`, and every bridge mints only after the
  lock: `l < m`. A deposit counted in supply was minted by `D`, so `l < m <= D <= S`: it is also counted as locked.
  A deposit locked but not yet minted (`l <= S`, `m > D`) is counted as locked and not as supply. Either way the
  locked side is never short.
- **Withdrawals** burn on the destination at `b` and release on Ethereum at `r`, always `b < r`. If burned by `D`, the
  tokens are out of supply; if released after `S` they are still locked: over-backed. The one way to look
  under-backed would be `D < b < r <= S`: burned after the destination block yet released before the source block,
  inside one gap. That needs `r - b <= gap`. Every supported bridge's fastest release is far longer than the gap:
  Arbitrum, OP Mainnet and Base wait out a challenge period measured in days; Nomad's optimistic window was 30 minutes
  (and the bridge is halted); and Polygon PoS can release a burn only after a checkpoint containing it reaches Ethereum.
  `tools/measure_exit_latency.mjs` measured that last delay over 67 consecutive checkpoints: **minimum 839 s**, median
  995 s. 839 s is above 600 s, and Polygon's gap is held to 300 s anyway.
- **Donations** to the vault only raise the locked side.

### Fast bridges (LayerZero OFT)

An OFT adapter locks on Ethereum when a transfer is sent and the OFT mints on the destination when it is delivered,
so deposits behave as above. Withdrawals do not: the OFT burns on the destination at send time `b` and the adapter
releases on Ethereum at delivery `r`, and delivery is fast. `tools/measure_oft_latency.mjs` matched USDT0 transfers
by LayerZero guid (docs/oft-latency.json): Polygon to Ethereum took **96 to 126 s** (6 transfers), Arbitrum to
Ethereum **1010 to 1414 s** (15). So for a pair with an OFT vault:

- the max gap is **120 s** (`FAST_GAP_S`), frozen into the pair's terms the moment an OFT vault or destination is
  added, and snapshotted into every check;
- the only in-flight amount that can make such a pair look under-backed is value burned on the destination after
  `D` and released by the adapter at or before `S`, i.e. sent in the first `gap - fastest_delivery` seconds after `D`:
  at most **120 - 96 = 24 s** of outbound OFT volume from that chain (zero from Arbitrum, whose fastest delivery is
  longer than the gap);
- that amount moves the ratio by `volume_24s / supply`. A pair whose tolerance is at least that share cannot be pushed
  under it by in-flight messages; a pair registered at 0 bps can be, by at most that amount, only when its true ratio
  is already within that share of 100%. The canonical USDT pair sits near 200%, so it cannot flip, and the patrol pins
  blocks seconds apart (gap 0 to 12 s), where no OFT transfer can complete in between.

So with `S >= D` and `S - D <= gap`, transfers in flight through escrow bridges can only make a pair look
**over**-backed, and through a fast bridge by at most the volume above. The opposite
order (destination after source) would count fresh mints without their locks and could show a backed bridge as
under-backed; it is refused.

A depositor can still use the over-backing on purpose (bridge a large amount and file a monitoring check that
instant): see rule 7, where the gate refuses a pair with any non-BACKED ruling inside its max age.

## 1a. Coverage: nothing a vault backs goes unnoticed

Every check records, at its pinned Ethereum block, which destinations each vault's **own bridge config** says it
backs, and compares them with the pair's list. Each vault has a family, fixed by its kind:

| Family | Kinds | How the bridge's own config is enumerated | Coverage |
|---|---|---|---|
| MAPPING | `arbitrum`, `polygon`, `op_dai` | the bridge maps the source token to exactly one destination token | COMPLETE |
| LEDGER | `wh_*` | Wormhole's `outstandingBridged(l1)` is what the bridge owes on **every** chain; it is counted as supply when larger than the listed tokens | COMPLETE |
| LZ | `oft_*` | `peers(eid)` of the adapter for **every eid from 30101 to 31100**, in one Multicall3 `aggregate3` call at the pinned block, from the two scan RPCs (rpc.mevblocker.io, eth-mainnet.public.blastapi.io), identical; in the same call Ethereum's LayerZero endpoint must support **no eid from 31101 to 31300**, and no `peers` entry may revert | COMPLETE, GAP or UNREAD |
| CCIP | `ccip_*` | the pool's `getSupportedChains()` at the pinned block, from both Ethereum RPCs | COMPLETE, GAP or UNREAD |
| OPEN | `optimism`, `base`, `nomad` | none on chain: one escrow holds every representation of the token | OPEN |

- **COMPLETE**: every destination the bridge names is listed. **GAP**: the ruling names each unlisted one (`lz:<eid>`,
  `ccip:<selector>`). **UNREAD**: a scan failed, disagreed, or could not be trusted (above). **OPEN**: not enumerable.
  The pair's coverage is the first of GAP, UNREAD, OPEN present, else COMPLETE.
- Coverage **never changes the arithmetic**: the verdict is the ratio of what is listed. It decides what the gate may
  say (only COMPLETE is favorable) and what the keeper adds.
- Validators accept a leader's scan or PoR entry that is an **error** (it can only make the answer less favorable),
  and a leader's entry with data only if it equals their own read; every field that decides the verdict must be identical.

## 3. Two RPCs per chain; transport faults are PENDING

Every value (block header, every vault's balance, supply, decimals, deposits, every anchor) is read from **both** RPCs of its
chain; only the fields used are compared, and they must be identical. Validators then accept the leader's reading
only if it is identical to their own.

| Chain | RPC A | RPC B |
|---|---|---|
| Ethereum | eth-pokt.nodies.app | rpc.mevblocker.io |
| Arbitrum One | arb-pokt.nodies.app | arbitrum-one.public.blastapi.io |
| OP Mainnet | mainnet.optimism.io | op-pokt.nodies.app |
| Base | base-pokt.nodies.app | base.drpc.org |
| Polygon PoS | polygon.drpc.org | rpc-mainnet.matic.quiknode.pro |
| Moonbeam | moonbeam.drpc.org | moonbeam.api.onfinality.io/public |
| Mantle | rpc.mantle.xyz | mantle.drpc.org |
| X Layer | xlayerrpc.okx.com | xlayer.drpc.org |
| Sei | evm-rpc.sei-apis.com | sei.api.pocket.network |
| Flare | rpc.ankr.com/flare | flare.public-rpc.com |
| Hedera | mainnet.hashio.io/api | hedera.linkpool.pro |
| Unichain | mainnet.unichain.org | unichain.drpc.org |
| Morph | rpc.morphl2.io | rpc-quicknode.morphl2.io |
| Ink | rpc-gel.inkonchain.com | rpc-qnd.inkonchain.com |
| Berachain | rpc.berachain.com | berachain-rpc.publicnode.com |
| HyperEVM | rpc.hyperliquid.xyz/evm | hyperliquid-json-rpc.stakely.io |
| Monad | rpc.monad.xyz | monad-mainnet-rpc.spidernode.net |

**Transport faults are PENDING, never a ruling.** An RPC that is down, throttled or answers junk, or a chain's two RPCs
answering differently (`RPC_UNREADABLE`, `RPC_DISAGREE`), makes `read_check` return `PENDING`: nothing is stored for the
check except an attempt counter, the check stays OPEN (or CONTESTED), and **anyone** calls `read_check` again. The read
window is fixed when the round opens: `read_by` is the filing time plus 2 h / 300 s (the contest time plus the same for
a re-read); `read_check` refuses after it (`READ_WINDOW_CLOSED_AT_...`), so retries, junk calls and calls about other
checks never extend it; `expire` then ends the round (section 6). Validators read the request (blocks, vaults, tokens,
anchors, scans) from the registry's state before the non-deterministic step, never a block or range a leader names,
and agree with a leader's PENDING only when their own read is PENDING too.

A missing block, a call that reverts or returns nothing (`CALL_FAILED`), a decimals value different from the frozen
one, or a changed anchor makes the check **INCONCLUSIVE**: every stake is refunded, nobody is slashed. An INCONCLUSIVE
that is about the pair's data (`CALL_FAILED`, `MALFORMED_ANSWER`, `DECIMALS_MISMATCH`, `MAPPING_CHANGED`,
`CONTEST_DISAGREES`) becomes the pair's latest ruling; one that is about the filing (pins, timeouts) does not.

## 4. The verdict is arithmetic

Both sides are scaled to the larger of all decimals involved, exactly, in integers:
`locked_norm = (sum over vaults of balance_v) * 10^(D - source_decimals)`,
`supply_norm = sum(counted_i * 10^(D - decimals_i))`, with `counted_i = totalSupply_i`, or
`max(totalSupply_i, deposits_i)` for an OP/Base destination. For a Wormhole vault the destinations through it count
together as `max(their sum, outstandingBridged(l1))` (the ledger is kept in 8 decimals for tokens with more and is
scaled back), so supply on chains the pair does not list is counted.

- **BACKED** if `locked_norm * 10000 >= supply_norm * (10000 - tolerance_bps)`
- **UNDER_BACKED** otherwise.

The ratio shown everywhere is `floor(locked_norm * 10000 / supply_norm)` in bps (`-1` when supply is 0).

- **Alert.** A BACKED ruling whose ratio is below `10000 - tolerance_bps + 10` (within **10 bps** of the line) is
  `ALERT`; BACKED above it is `OK`; UNDER_BACKED is `BREACH`.
- **History.** Every FINAL ruling is appended to the pair's time series (`get_history(pair, offset, limit)`, at most
  100 points a page): check, pinned time and blocks, verdict, ratio, locked and supply, alert, coverage, PoR.
- **Proof of Reserve.** For a source token with a Chainlink PoR feed on Ethereum (WBTC: WBTC PoR; wstETH: stETH PoR
  against stETH's supply; weETH: eETH PoR against eETH's supply) the check reads `latestRoundData()`, the feed's
  decimals and the covered token's supply at the pinned block from both RPCs. `por_ratio = reserves / supply`;
  **MATCH** if BackedBy's ratio is within **50 bps** of it, else **DIFF** with the delta and an explanation
  (`BRIDGE_VAULT_SURPLUS_EXCEEDS_CUSTODY_SURPLUS`, `BRIDGE_VAULT_BELOW_CUSTODY_RATIO`, plus
  `CUSTODY_RESERVES_BELOW_SUPPLY` when reserves are below supply); **STALE** if the answer is more than **48 h** older
  than the pinned block; **UNREAD** if the feed could not be read. It never changes the verdict. PoR measures custody
  of the token's whole supply; BackedBy measures one bridge's vault against what it minted, so a DIFF is expected
  whenever the vault holds a surplus; the site shows that surplus's sources (`tools/explain_surplus.mjs`).

## 5. Bonds and challenges

- `bond(pair)` (payable, minimum 1 GEN canonical, 0.05 GEN demo): "this pair stays BACKED from now until I request to
  unbond". `top_up` adds to an active bond.
- `challenge(bond, blocks)` (payable, minimum stake 0.1 GEN canonical, 0.01 GEN demo), by anyone but the operator.
- **Final UNDER_BACKED**: the whole bond is slashed; the challenger is credited the stake plus **50%** of the slash,
  the treasury (the deploying address) the other 50% (Sentinel's split; the bounty is floored, so the parts always sum
  to the slash).
- **Final BACKED**: the challenger's stake is added to the operator's bond.
- **INCONCLUSIVE**: the stake is refunded.
- **One open check per pair.** A challenge replaces an open monitoring check (closed INCONCLUSIVE · SUPERSEDED, any
  contest stake on it refunded); nothing replaces an open challenge.
- **Counters** move only in the transitions that complete; every `raise` comes before the first write. Payable methods
  never raise: a refusal is a successful call that credits the value back as claimable and returns `{"ok": false}`.

## 6. PROVISIONAL, CONTESTABLE, FINAL

1. **OPEN**: filed. Anyone calls `ChainReader.read_check(registry, check, 1)`, then `rule(check)`.
2. **PROVISIONAL**: `rule` computed the verdict. It is **contestable** for the window: **6 h** canonical, **90 s** demo.
3. `contest(check)` (payable, minimum stake) re-reads **the same pinned blocks** (`read_check(..., 2)`, then `rule`):
   the same verdict makes it **FINAL** and the contest stake goes to the side the ruling favoured (the bond for
   BACKED, the challenger for UNDER_BACKED, the treasury on a monitoring check); a different verdict makes it
   **INCONCLUSIVE** and refunds everyone.
4. With no contest, anyone calls `finalize(check)` once the window has passed: **FINAL**.

Every non-terminal state has a deadline and a permissionless exit, so every check reaches FINAL or INCONCLUSIVE:

| State | Exit | Deadline (canonical / demo) | Result |
|---|---|---|---|
| OPEN, reading recorded | `rule` | none needed | PROVISIONAL or INCONCLUSIVE |
| OPEN, nothing read | `expire` | 2 h / 300 s after filing | INCONCLUSIVE · TIMEOUT_UNREAD, stake refunded |
| PROVISIONAL | `finalize` | the window | FINAL |
| CONTESTED, re-read recorded | `rule` | none needed | FINAL or INCONCLUSIVE |
| CONTESTED, nothing re-read | `expire` | 2 h / 300 s after the contest | first ruling FINAL, contest stake refunded |

A re-read that fails on transport is PENDING (section 3) and is not recorded, so an outage cannot overturn a ruling;
the timeout above ends it.

## 7. Withdrawals, monitoring and the gate

- `request_unbond(bond)` ends the bond's coverage at that moment; `withdraw_bond(bond)` after **24 h** (demo 120 s) and
  only while no check on the bond is open credits the bond to the operator. Ledger, checked by tests and by
  `get_ledger`: `received = bonds + open stakes + claimable + claimed`.

### Payouts

Every bounty, refund (stake, contest stake, refused payable), bond withdrawal and treasury share is first credited to
its owner, and `claim()` is the one way GEN leaves: it zeroes the credit, adds it to `claimed`, and in the same
transaction posts one external value message to the claimant (`gl.evm.Account(claimant).emit_call(amount, b"")`),
applied when the transaction finalizes. If the registry's balance is short of the credit the claim is refused and
nothing is marked. The internal `emit_transfer` is not used: on Studio Dev it is stored with a declared budget of 0,
skipped at finalization and credited back to the contract (docs/PAYOUT_PROBE.md). The client attaches one External
message allocation naming the claimant (500,000 gas at the locked price plus headroom) and refuses to submit a claim
without it (`tools/lib/payout.mjs`). A payout counts as made only when the finalized transaction shows the value
effect delivered and not skipped and the registry's `eth_getBalance` fell by the amount; `tools/final_check.mjs`
re-reads every demo payout that way, and calls the demo registry drained only when `eth_getBalance` is 0.
- `monitor(pair, blocks)`: no stake, only when no check is open on the pair, and at most one **ruled** monitoring
  check per pair per **1 h** (demo 30 s). Filings whose pins break the rules do not use up the interval.
- **Keeper**: `tools/keeper.mjs` runs hourly and every 6 h in GitHub Actions on both v2 registries. It walks every
  page of pairs (read from two endpoints, identical, cursor persisted), files a monitoring check for each pair whose
  chains have moved, reads (retrying PENDING reads inside the window), rules, finalizes and expires checks, and adds
  each unlisted destination the vault's bridge config names on a chain BackedBy reads (authenticate, then
  `add_destination`); the rest are recorded as unmatched with the reason. An action is done only when its transaction
  is FINALIZED, succeeded, and contract state shows its effect; every step is checkpointed on the `keeper-state`
  branch and a run resumes from its stored transaction hashes. Anyone can do every action by hand.
- **CollateralGate** `is_backed(pair, source_token, dest_chain, dest_token, now)` is bound to one pair and its exact
  tokens: anything else is `NOT_THIS_PAIR`, so a copycat pair (the same tokens under another tolerance, a look-alike
  token) is never read for the caller. It answers **BACKED** only if the pair's latest ruling is **FINAL** and
  **BACKED**, its pinned Ethereum block is at most `max_age` old (24 h canonical, 30 min demo), **no ruling within
  `max_age` was anything but BACKED**, coverage is **COMPLETE**, and the pair's tolerance is at most
  `max_tolerance_bps` (50); **BACKED_ALERT** when the ratio is within the alert margin. Every other state refuses:
  UNDER_BACKED, INCONCLUSIVE, STALE, PENDING (never ruled, a check open), NEVER_CHECKED, RECENT_NOT_BACKED,
  COVERAGE_GAP, COVERAGE_UNREAD, COVERAGE_OPEN, TOLERANCE_TOO_WIDE, NO_SUCH_PAIR, REGISTRY_UNREADABLE, NO_CLOCK,
  RULING_FROM_THE_FUTURE. `borrow(pair, source_token, dest_chain, dest_token, amount, note)` asks it with the
  transaction's own clock and records the answer either way.

## Clock

Bond coverage and every deadline use the transaction's timestamp (`gl.message.raw["datetime"]`); block timestamps
come from the chains. Clock skew between the two is seconds.
