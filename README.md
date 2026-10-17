# BackedBy

**Is this bridged token actually backed?** BackedBy compares the tokens a bridge has locked in its vault on Ethereum
with the supply of the tokens it minted on the other chain, at pinned finalized blocks on both chains, and records the
answer on GenLayer: BACKED, UNDER_BACKED or INCONCLUSIVE.

Live: **https://backedby-ledger.vercel.app** · Rules: [docs/RULES.md](docs/RULES.md) · Seeds: [docs/SEEDS.md](docs/SEEDS.md)

## What and why

A bridged token is only worth what its bridges still hold. Nomad's Ethereum vault was drained in August 2022 and its
Moonbeam tokens kept circulating; today the vault holds about 0.2% of the madUSDC outstanding. Nobody has to trust a
dashboard for that number: both halves are public chain state. BackedBy makes reading them a GenLayer transaction, so
the number is agreed by independent validators, pinned to specific blocks, and usable by other contracts: an
operator can bond that a pair stays backed, anyone can challenge with a stake, and a lending market can ask
`CollateralGate.is_backed(pair)` before it accepts the token.

## How the rules work

1. **Pairs are authenticated by the bridges themselves.** A pair is one source token, 1..n vaults holding it on
   Ethereum (summed) and 1..n destination tokens (summed). ChainReader proves every vault and destination from the
   bridge's own mapping on both chains (Arbitrum's gateway routers, the OP Stack token's `remoteToken`/`bridge`,
   Polygon's Root/ChildChainManager, the DAI bridges, Nomad's TokenRegistry, LayerZero OFT peers such as USDT0's).
   Anything it cannot prove is refused. Anyone can add a missing vault or destination with the same proof, so a token
   with two mint paths (Polygon's USDT: the PoS bridge and USDT0) is judged against both.
2. **One finalized block per chain, source last.** The Ethereum block must be at or after every destination block and
   at most 10 minutes later (5 for Polygon, 2 once a pair holds a fast LayerZero vault), so transfers in flight can
   only look over-backed, never under, except a fast bridge's, which RULES.md bounds
   ([why](docs/RULES.md#why-this-order-makes-in-flight-transfers-look-over-backed-never-under)).
3. **Two RPCs per chain, or INCONCLUSIVE.** Every value is read from two RPCs run by different operators and must be
   identical; validators accept the leader's reading only if it matches their own. Any disagreement, error, missing
   block, decimals change or bridge remapping is INCONCLUSIVE and refunds every stake.
4. **The verdict is arithmetic.** Decimals are normalized exactly; BACKED if `locked >= supply * (1 - tolerance)`, with
   the tolerance frozen at registration. On OP and Base a token counts as the larger of its supply and the bridge's
   own ledger, which can only err towards UNDER_BACKED. No model is involved anywhere.
5. **Bonds and challenges.** UNDER_BACKED slashes the bond (challenger gets the stake back plus half, the treasury the
   other half); BACKED moves the challenger's stake into the bond; INCONCLUSIVE refunds.
6. **PROVISIONAL, CONTESTABLE, FINAL.** Every ruling can be contested for 6 hours (90 s on the demo registry); a contest
   re-reads the same blocks. Every state has a deadline and a public exit.
7. **Patrol.** A GitHub Actions job ([.github/workflows/patrol.yml](.github/workflows/patrol.yml)) files monitoring
   checks on every canonical pair every 6 hours and finalizes expired windows.

## Addresses (GenLayer Studio Dev, chain 61997)

Every contract was deployed from commit `047d3406d5c78f4cbb1913012bd5df249998fcb5`.

| Contract | Address | Deployed file | sha256 | Constructor |
|---|---|---|---|---|
| ChainReader | [`0x7d0C1Ccc40A8ECB5a82a3879C78F503E7ECac35C`](https://explorer-studio-dev.genlayer.com/address/0x7d0C1Ccc40A8ECB5a82a3879C78F503E7ECac35C) | `build/ChainReader.py` | `a8d4f3ff0b62e485` | `[]` |
| BackedByRegistry | [`0x66BA2FF893f5FaAf21f000286A5e34BBDB9c8102`](https://explorer-studio-dev.genlayer.com/address/0x66BA2FF893f5FaAf21f000286A5e34BBDB9c8102) | `build/BackedByRegistry.py` | `14c42a676e00f96d` | `["CANONICAL", "0x7d0C1Ccc40A8ECB5a82a3879C78F503E7ECac35C"]` |
| BackedByRegistryDemo | [`0x0Cf85aC9650f7957D74224561DF6667a769AF20f`](https://explorer-studio-dev.genlayer.com/address/0x0Cf85aC9650f7957D74224561DF6667a769AF20f) | `build/BackedByRegistry.py` | `14c42a676e00f96d` | `["DEMO", "0x7d0C1Ccc40A8ECB5a82a3879C78F503E7ECac35C"]` |
| CollateralGate | [`0x78d4Bbfc42Ebc94A18Aee6557079215881bA3aD8`](https://explorer-studio-dev.genlayer.com/address/0x78d4Bbfc42Ebc94A18Aee6557079215881bA3aD8) | `build/CollateralGate.py` | `2f84b3fd462670ea` | `["0x66BA2FF893f5FaAf21f000286A5e34BBDB9c8102", 86400, 50]` |
| CollateralGateDemo | [`0x77F394DD1E2D7226621C37c7F6887D340B4D194F`](https://explorer-studio-dev.genlayer.com/address/0x77F394DD1E2D7226621C37c7F6887D340B4D194F) | `build/CollateralGate.py` | `2f84b3fd462670ea` | `["0x0Cf85aC9650f7957D74224561DF6667a769AF20f", 1800, 50]` |

The canonical registry runs the 6 h contest window and holds the seeded pairs; the demo registry runs a 90 s window
and holds the [demo run](docs/demo-run.log): every payout in it is proved on chain ([docs/payouts.json](docs/payouts.json))
and its `eth_getBalance` is 0.

Earlier deployments are retired; their records are kept unchanged: [docs/superseded/e915d21](docs/superseded/e915d21/README.md)
(one vault per pair) and [docs/superseded/6f9431f](docs/superseded/6f9431f/README.md) (internal transfers that Studio Dev
skipped, so payouts never arrived; USDT0 read on 3 of its chains).

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

- Source chain is Ethereum; destinations are Arbitrum One, OP Mainnet, Base, Polygon PoS and Moonbeam through six
  bridge kinds (Arbitrum's escrow gateways, the OP and Base Standard Bridges, the OP DAI bridge, Polygon PoS's ERC20
  predicate, Nomad), plus LayerZero OFTs on those chains and on Mantle, X Layer, Sei, Flare, Hedera, Unichain, Morph,
  Ink, Berachain, HyperEVM and Monad. Other bridges need their own authentication rule in ChainReader.
- A pair's supply is the destination tokens' `totalSupply` (on OP Stack chains, the bridge's own per-token deposits
  if larger). A vault belongs to one pair, which lists every destination it backs that two RPCs can read
  ([shared vaults](docs/SEEDS.md#shared-vaults)). USDT0's adapter has peers on six chains left out (Conflux, Rootstock,
  Plasma, Stable, MegaETH, Tempo: no second honest RPC or no finalized tag); their supply is not counted, which can
  only make the USDT pair look better backed, never worse.
- "Locked" is the vault's balance of the source token. A rebasing source token or a destination token that can mint
  outside the bridge is measured as the chains report it, which is the point.
- Moonbeam has not produced a block since 2026-08-10, so Nomad pairs can only be checked at that moment.
- Payouts are external value messages, delivered when the claim finalizes; every demo payout is proved by the
  finalized transaction and by `eth_getBalance` ([docs/payouts.json](docs/payouts.json), [docs/PAYOUT_PROBE.md](docs/PAYOUT_PROBE.md)).
- The read path depends on public RPC endpoints. When one is down or throttling, reads come back INCONCLUSIVE and
  are retried; they never become a verdict.

## Repository

`contracts/` source · `build/` deployed bytes · `test/` offline suite and on-chain scripts (deploy, seed, demo) ·
`tools/` feasibility, patrol, verification, final check · `frontend/` the site · `docs/` everything written down.
