# BackedBy

**Is this bridged token actually backed?** BackedBy compares the tokens a bridge has locked in its vault on Ethereum
with the supply of the tokens it minted on the other chain, at pinned finalized blocks on both chains, and records the
answer on GenLayer: BACKED, UNDER_BACKED or INCONCLUSIVE.

Live: **https://backedby-ledger.vercel.app** · Rules: [docs/RULES.md](docs/RULES.md) · Seeds: [docs/SEEDS.md](docs/SEEDS.md)

## What and why

A bridged token is only worth what the bridge still holds. Nomad's Ethereum vault was drained in August 2022 and its
Moonbeam tokens kept circulating; today the vault holds about 0.2% of the madUSDC outstanding. Nobody has to trust a
dashboard for that number: both halves are public chain state. BackedBy makes reading them a GenLayer transaction, so
the number is agreed by independent validators, pinned to specific blocks, and usable by other contracts: an
operator can bond that a pair stays backed, anyone can challenge with a stake, and a lending market can ask
`CollateralGate.is_backed(pair)` before it accepts the token.

## How the rules work

1. **Pairs are authenticated by the bridge itself.** ChainReader reads the bridge's own mapping on both chains
   (Arbitrum's gateway routers, the OP Stack token's `remoteToken`/`bridge`, Polygon's Root/ChildChainManager, the DAI
   bridges, Nomad's TokenRegistry). Anything it cannot prove is refused. Anyone can add a destination token a pair is
   missing, with the same proof.
2. **One finalized block per chain, source last.** The Ethereum block must be at or after every destination block and
   at most 10 minutes later (5 for Polygon), so transfers in flight can only look over-backed, never under
   ([why](docs/RULES.md#why-this-order-makes-in-flight-transfers-look-over-backed-never-under)).
3. **Two RPCs per chain, or INCONCLUSIVE.** Every value is read from two RPCs run by different operators and must be
   identical; validators accept the leader's reading only if it matches their own. Any disagreement, error, missing
   block, decimals change or bridge remapping is INCONCLUSIVE and refunds every stake.
4. **The verdict is arithmetic.** Decimals are normalized exactly; BACKED if `locked >= supply * (1 - tolerance)`, with
   the tolerance frozen at registration. No model is involved anywhere.
5. **Bonds and challenges.** UNDER_BACKED slashes the bond (challenger gets the stake back plus half, the treasury the
   other half); BACKED moves the challenger's stake into the bond; INCONCLUSIVE refunds.
6. **PROVISIONAL, CONTESTABLE, FINAL.** Every ruling can be contested for 6 hours (90 s on the demo registry); a contest
   re-reads the same blocks. Every state has a deadline and a public exit.
7. **Patrol.** A GitHub Actions job ([.github/workflows/patrol.yml](.github/workflows/patrol.yml)) files monitoring
   checks on every canonical pair every 6 hours and finalizes expired windows.

## Addresses (GenLayer Studio Dev, chain 61997)

Every contract was deployed from commit `e915d21e8a25e35c06baa614b5f234ccaf74b826`.

| Contract | Address | Deployed file | sha256 | Constructor |
|---|---|---|---|---|
| ChainReader | [`0x73217767D2F71cdc9D22b19e65d7aA8926D328B9`](https://explorer-studio-dev.genlayer.com/address/0x73217767D2F71cdc9D22b19e65d7aA8926D328B9) | `build/ChainReader.py` | `5a141b225eb1b469` | `[]` |
| BackedByRegistry | [`0xB136AaB44b83e3408Ef1a421801271dba8Ff1DeD`](https://explorer-studio-dev.genlayer.com/address/0xB136AaB44b83e3408Ef1a421801271dba8Ff1DeD) | `build/BackedByRegistry.py` | `358403350b9e3749` | `["CANONICAL", "0x73217767D2F71cdc9D22b19e65d7aA8926D328B9"]` |
| BackedByRegistryDemo | [`0xCA8b9d4E3Fa93A7A012306Fa443D71E9e42A45b6`](https://explorer-studio-dev.genlayer.com/address/0xCA8b9d4E3Fa93A7A012306Fa443D71E9e42A45b6) | `build/BackedByRegistry.py` | `358403350b9e3749` | `["DEMO", "0x73217767D2F71cdc9D22b19e65d7aA8926D328B9"]` |
| CollateralGate | [`0x2B7A38AaDF934887b2f6A4b057D63e99259aA831`](https://explorer-studio-dev.genlayer.com/address/0x2B7A38AaDF934887b2f6A4b057D63e99259aA831) | `build/CollateralGate.py` | `e0b6ab99a08b23d6` | `["0xB136AaB44b83e3408Ef1a421801271dba8Ff1DeD", 86400, 50]` |
| CollateralGateDemo | [`0x6F049473c968ce668Aebd46239CDFcCf8554086d`](https://explorer-studio-dev.genlayer.com/address/0x6F049473c968ce668Aebd46239CDFcCf8554086d) | `build/CollateralGate.py` | `e0b6ab99a08b23d6` | `["0xCA8b9d4E3Fa93A7A012306Fa443D71E9e42A45b6", 1800, 50]` |

The canonical registry runs the 6 h contest window and holds the seeded pairs; the demo registry runs a 90 s window
and holds the [demo run](docs/demo-run.log), drained to 0.

## How to verify

- **Source.** `node tools/verify_source.mjs` reads each address's code from Studio Dev (`gen_getContractCode`) and
  compares it byte for byte with `build/` at the deploy commit and at HEAD. The site does the same live at
  [/verify](https://backedby-ledger.vercel.app/verify). `build/` is `contracts/` with the shared helpers inlined
  (`python3 tools/build.py`).
- **Numbers.** Every pair page links each read to a block explorer: the vault's balance at the pinned Ethereum block,
  the token's supply at the pinned destination block, and every bridge-mapping call that was re-read.
- **Tests.** `sh test/run_offline.sh`: the offline suite runs the deployed build files against mock chains (rules,
  every boundary, RPC disagreement, fake pairs, omitted destinations, double checks, griefing, withdrawals, fund
  conservation, stuck-state timeouts, the attack round in [docs/ATTACK_REPORT.md](docs/ATTACK_REPORT.md)).
- **Everything at once.** `node tools/final_check.mjs`, result in [docs/FINAL_CHECK.md](docs/FINAL_CHECK.md).
- **API.** `/api/backed?pair=<id>` returns the pair's standing as JSON, read from chain; `&format=svg` returns a badge:
  ![badge](https://backedby-ledger.vercel.app/api/backed?pair=9&format=svg)

## Scope

- Source chain is Ethereum; destinations are Arbitrum One, OP Mainnet, Base, Polygon PoS and Moonbeam, through six
  bridge kinds (Arbitrum's escrow gateways, the OP and Base Standard Bridges, the OP DAI bridge, Polygon PoS's ERC20
  predicate, Nomad). Other bridges need their own authentication rule in ChainReader.
- A pair's supply is the destination tokens' `totalSupply` (capped by the bridge's own per-token deposits on OP
  Stack chains). Tokens the same vault backs on chains BackedBy does not read are not counted; leaving them out only
  makes a pair look better backed than it is, never worse.
- "Locked" is the vault's balance of the source token. A rebasing source token or a destination token that can mint
  outside the bridge is measured as the chains report it, which is the point.
- Polygon USDT is UNDER_BACKED against the PoS bridge's predicate because its supply is now also minted through
  USDT0's LayerZero adapter; BackedBy says nothing about USDT0 itself.
- Moonbeam has not produced a block since 2026-08-10, so Nomad pairs can only be checked at that moment.
- Studio Dev records a claim's value transfer but does not deliver it; the registry's books (`get_ledger`) are what
  drain to 0.
- The read path depends on public RPC endpoints. When one is down or throttling, reads come back INCONCLUSIVE and
  are retried; they never become a verdict.

## Repository

`contracts/` source · `build/` deployed bytes · `test/` offline suite and on-chain scripts (deploy, seed, demo) ·
`tools/` feasibility, patrol, verification, final check · `frontend/` the site · `docs/` everything written down.
