# BackedBy

**Is this bridged token actually backed?** BackedBy compares what a bridge holds in its vaults on Ethereum with the
supply of the tokens it minted on other chains, at pinned finalized blocks on every chain, and records the answer on
GenLayer: BACKED, UNDER_BACKED or INCONCLUSIVE. Code computes every number and every verdict; no model is called.

Live: **https://backedby-ledger.vercel.app** · Rules: [docs/RULES.md](docs/RULES.md) · Seeds: [docs/SEEDS.md](docs/SEEDS.md) ·
Milestone: [docs/MILESTONE.md](docs/MILESTONE.md) · Keeper: [/keeper](https://backedby-ledger.vercel.app/keeper)

## What and why

A bridged token is only worth what its bridge still holds. Nomad's Ethereum vault was drained in August 2022 and its
Moonbeam tokens still circulate; today the vault holds well under 1% of what is outstanding. Both halves of that number
are public chain state. BackedBy makes reading them a GenLayer transaction, so the number is agreed by independent
validators, pinned to specific blocks, kept as a history, and usable by other contracts: an operator can bond that a
pair stays backed, anyone can challenge with a stake, and a lending market asks
`CollateralGate.is_backed(pair, source_token, dest_chain, dest_token, now)` before it accepts the token.

## How the rules work

1. **Pairs are authenticated by the bridges themselves.** A pair is one source token, 1-8 vaults holding it on
   Ethereum (summed) and 1-16 destination tokens (summed). ChainReader proves every vault and destination from the
   bridge's own config on both chains: Arbitrum's gateway routers, the OP Stack token's `remoteToken`/`bridge`, the OP
   DAI bridges, Polygon's Root/ChildChainManager, Nomad's TokenRegistry, **LayerZero** OFT adapters (`token()` and
   `peers`), **Wormhole** Portal (`bridgeContracts`, `wrappedAsset`, the token's origin) and **Chainlink CCIP**
   token pools (TokenAdminRegistry, lock-release and burn-mint pools naming each other). Anything else is refused.
2. **Coverage: nothing a vault backs goes unnoticed.** Every check also reads, at its pinned Ethereum block, which
   destinations each vault's own bridge config names: every LayerZero eid 30101-31100 in one Multicall3 call, a CCIP
   pool's supported chains, Wormhole's ledger of what it owes everywhere. Unlisted ones are named in the ruling; the
   keeper adds the ones it can prove and records the rest, which the site shows.
3. **One finalized block per chain, source last**, within 10 minutes (5 for Polygon, 2 with a LayerZero vault), so
   transfers in flight can only look over-backed ([why](docs/RULES.md#why-this-order-makes-in-flight-transfers-look-over-backed-never-under)).
4. **Two RPCs per chain; transport faults are PENDING.** Every value is read from two RPCs run by different operators
   and must be identical. An outage or a disagreement stores nothing: the check stays open and anyone retries until
   a read window fixed at filing closes, then it expires and refunds. Validators read the registry's request
   themselves and accept a leader's PENDING only if their own read fails too.
5. **The verdict is arithmetic.** BACKED if `locked >= supply * (1 - tolerance)`, tolerance frozen at registration;
   within 10 bps of that line is ALERT. Every FINAL ruling becomes a point of the pair's history (charted on the site).
   Where Chainlink publishes Proof of Reserve for the token, it is read at the same block and shown next to the ratio,
   MATCH or DIFF with the delta and its explanation; over-backed pairs show where the surplus comes from.
6. **Bonds, challenges, contests.** UNDER_BACKED slashes the bond (challenger gets the stake back plus half);
   BACKED moves the stake into the bond; INCONCLUSIVE refunds. Rulings are contestable for 6 h (90 s on the demo
   registry) and every state has a deadline and a public exit. Payouts are external sends, each proved on chain.
7. **CollateralGate** is bound to one pair and its exact tokens (a copycat pair is never read) and answers in named
   states; only BACKED and BACKED_ALERT are favorable, never on missing, pending, stale or partial data.
8. **Keeper.** A GitHub Actions job ([keeper.yml](.github/workflows/keeper.yml)), hourly and every 6 hours, drives
   every check on both v2 registries with durable checkpoints on the `keeper-state` branch.

## Addresses (GenLayer Studio Dev, chain 61997)

Every v2 contract was deployed from commit `61a08f80d875fb868032effff3539b93a5450c39`.

| Contract | Address | Deployed file | sha256 | Constructor |
|---|---|---|---|---|
| ChainReader | [`0x3E9C72f34fB668fe92626757B85613203AF19713`](https://explorer-studio-dev.genlayer.com/address/0x3E9C72f34fB668fe92626757B85613203AF19713) | `build/ChainReader.py` | `d66ff61ab930ca55` | `[]` |
| BackedByRegistry | [`0x2162246f0412bBCb7F7Af9C37D0a2972Cf2813E2`](https://explorer-studio-dev.genlayer.com/address/0x2162246f0412bBCb7F7Af9C37D0a2972Cf2813E2) | `build/BackedByRegistry.py` | `82348269fbc3b5bc` | `["CANONICAL", "0x3E9C72f34fB668fe92626757B85613203AF19713"]` |
| BackedByRegistryDemo | [`0x3D957588dC1Ee60B1D50678f721aaCc5FceC1f1F`](https://explorer-studio-dev.genlayer.com/address/0x3D957588dC1Ee60B1D50678f721aaCc5FceC1f1F) | `build/BackedByRegistry.py` | `82348269fbc3b5bc` | `["DEMO", "0x3E9C72f34fB668fe92626757B85613203AF19713"]` |
| CollateralGate | [`0x3b8FD1A7334D7B92Fc1C0758FD3e0566627236f0`](https://explorer-studio-dev.genlayer.com/address/0x3b8FD1A7334D7B92Fc1C0758FD3e0566627236f0) | `build/CollateralGate.py` | `c216e4cabecfde88` | `["0x2162246f0412bBCb7F7Af9C37D0a2972Cf2813E2", 86400, 50]` |
| CollateralGateDemo | [`0xb42285b21Ddf38265041B06C494A6Ac04Fee689f`](https://explorer-studio-dev.genlayer.com/address/0xb42285b21Ddf38265041B06C494A6Ac04Fee689f) | `build/CollateralGate.py` | `c216e4cabecfde88` | `["0x3D957588dC1Ee60B1D50678f721aaCc5FceC1f1F", 1800, 50]` |

The canonical registry holds the seeded pairs; the demo registry holds the [demo run](docs/demo-run.log), every
payout of which is proved on chain ([docs/payouts.json](docs/payouts.json)). The accepted v1 deployment is unchanged and
proven byte-identical to its build at BASE ([docs/MILESTONE.md](docs/MILESTONE.md), [docs/superseded/047d340](docs/superseded/047d340/README.md)); the first v2
deployment, retired after the demo found H6, is in [docs/superseded/0ee50f9](docs/superseded/0ee50f9/README.md).

## How to verify

- **Source.** `node tools/verify_source.mjs` reads each address's code from Studio Dev (`gen_getContractCode`) and
  compares it byte for byte with `build/` at the deploy commit and at HEAD; the site does it live at
  [/verify](https://backedby-ledger.vercel.app/verify). `node tools/base_proof.mjs <BASE>` does the same for v1.
- **Numbers.** Every pair page links each read to a block explorer at the pinned block;
  `node tools/real_world.mjs` recomputes every ruling from a third RPC per chain ([docs/REAL_WORLD_CHECK.md](docs/REAL_WORLD_CHECK.md)).
- **Tests.** `sh test/run_offline.sh` (contract, rule, attack, meaning, payout and keeper suites against `build/`),
  `.venv-gl/bin/python -m pytest tests/direct` (GenLayer Direct Mode), `cd e2e && npx playwright test` (the live
  site); all of them, lint, the site build and deployed-source verification run in [CI](.github/workflows/ci.yml).
- **Everything at once.** `node tools/final_check.mjs` ([docs/FINAL_CHECK.md](docs/FINAL_CHECK.md)) and
  `node tools/audit.mjs` ([docs/AUDIT.md](docs/AUDIT.md)).
- **API.** `/api/backed?pair=<id>` returns the pair's standing and the gate's bound answer as JSON; `&format=svg` a badge:
  ![badge](https://backedby-ledger.vercel.app/api/backed?pair=1&format=svg)

## Scope

- Source chain is Ethereum. Destinations: Arbitrum One, OP Mainnet, Base, Polygon PoS and Moonbeam through the
  canonical bridges and Nomad; LayerZero OFTs on those and on Mantle, X Layer, Sei, Flare, Hedera, Unichain, Morph,
  Ink, Berachain, HyperEVM and Monad; Wormhole Portal on Polygon, Arbitrum, OP Mainnet and Base; Chainlink CCIP on
  twelve chains. A chain is read only where two public RPCs from different operators serve archive state and the
  finalized tag; destinations a vault backs elsewhere are named in its coverage, counted through Wormhole's ledger,
  and keep the gate from answering BACKED for that pair.
- OP and Base Standard Bridges and Nomad keep one escrow for every representation of a token, which cannot be
  enumerated on chain: their coverage is OPEN and the gate does not accept them. A destination counts as the larger of
  its supply and the bridge's own per-token ledger there.
- "Locked" is the vault's balance of the source token, as the chain reports it. Proof of Reserve and surplus
  explanations are shown next to the verdict and never change it.
- Moonbeam has not produced a block since 2026-08-10, so Nomad pairs are checked at that moment.

## Repository

`contracts/` source · `build/` deployed bytes · `test/` offline suites and on-chain scripts (deploy, seed, demo) ·
`tests/direct/` Direct Mode · `e2e/` Playwright · `tools/` feasibility, keeper, verification, real-world check,
final check, audit · `frontend/` the site · `docs/` everything written down.
