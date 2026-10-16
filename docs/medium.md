# Is that bridged token actually backed? I built something that checks, and it found six that aren't

If you hold USDC on Arbitrum that came over the official bridge, you are trusting one thing: that the gateway contract
on Ethereum still holds at least as much USDC as exists on Arbitrum. Usually it does. Sometimes it really, really does
not.

In August 2022 someone found a bug in Nomad's bridge and the Ethereum side was drained in an afternoon. The tokens
Nomad had minted on Moonbeam (madUSDC, madWETH, madWBTC and friends) did not disappear. They are still there. As of
this week, the Ethereum router holds about 3,720 USDC against roughly 2.1 million madUSDC outstanding. That is a
backing ratio of about 0.2%.

Nothing about that is secret. Both numbers are public chain state; you can read them yourself with two `eth_call`s.
What's missing is a way for other contracts to rely on the answer, and a way to put money behind it. That's what I
built: **BackedBy**, on GenLayer.

## The idea in one paragraph

A "pair" is a bridge vault on Ethereum plus the token that bridge minted on another chain. A check pins one finalized
block on each chain, reads the vault's balance and the token's supply there, and code compares them: BACKED if the
vault covers the supply, UNDER_BACKED if it doesn't. Operators can bond that a pair stays backed, anyone can challenge
them with a stake, and a lending market can ask a small contract (CollateralGate) whether the pair is backed right now
before accepting the token as collateral.

## Why GenLayer, when there is no AI in it

This is the part people ask about. GenLayer is known for contracts that call language models, and BackedBy calls none.
What I needed was the other half of GenLayer: validators that can each go out to the internet, fetch something, and
have to agree on it before anything is written.

So each validator reads both chains itself, at the same pinned blocks, from two public RPCs per chain run by different
companies (Pokt/Nodies and MEV Blocker on Ethereum, OP Labs and dRPC on Optimism, and so on). The two RPCs have to
return identical values. Then the validators have to return identical readings. If anything disagrees, errors, or is
missing, the answer is INCONCLUSIVE and every stake is refunded. Nobody gets slashed because an RPC had a bad minute.

And then the contract does the arithmetic. No model ever produces a number or a verdict. I wanted that to be boring
on purpose.

## The fiddly part: what counts as a pair

The first version accepted any token you pointed at. That is obviously wrong: I could deploy a token on Base, mint a
billion of it, call it "bridged USDC", and make Base's bridge look insolvent.

So a pair only exists if the bridge itself says so, read on chain:

- On Arbitrum, the gateway router has to map the Ethereum token to that exact Arbitrum token, on both sides.
- On OP Mainnet and Base, the token has to say its remote token is the Ethereum token and its bridge is the official
  L2 bridge.
- On Polygon, the RootChainManager and ChildChainManager have to point at each other.
- For Nomad, the TokenRegistry on Moonbeam has to map the token back to Ethereum, and the Moonbeam router has to name
  the Ethereum router as its remote.

Even that wasn't enough. When I ran an attack round against my own code, the first thing that fell over was OP Stack
tokens: anyone can deploy a contract that *answers* `remoteToken()` and `bridge()` correctly while minting whatever it
likes. The fix was to use the bridge's own bookkeeping: the Ethereum-side bridge records deposits per token pair and
will never release more than that, so a token's supply only counts up to its deposits. A fake can say whatever it
wants; the bridge won't pay out for it.

The second one that fell over was migrations. Bridges move their escrow sometimes. If an operator bonded a pair and the
bridge then moved its funds to a new gateway, a challenger could point at the old, empty vault and get them slashed. Now
every check re-reads the bridge's mapping at its own blocks, and if anything changed, the check is INCONCLUSIVE.

## Timing: why "source last"

The thing I spent the most time thinking about is which block to read on which chain. Bridges have transfers in
flight all the time. If you read the two chains at slightly different moments, could a perfectly healthy bridge look
under-backed?

It can, if you get the order wrong. So the rule is: the Ethereum block has to be at or after the destination block, and
at most ten minutes later. Deposits get locked on Ethereum before they are minted elsewhere, so one in flight only adds
to the locked side. Withdrawals get burned on the destination before they're released on Ethereum, and every bridge
here takes longer than ten minutes to release (Polygon's checkpoints were the closest; I measured 67 of them and the
fastest was 839 seconds). So in-flight transfers can only ever make a bridge look *over*-backed, never under. The
contract checks the order, the gap, and that both blocks are finalized.

## What it found

I seeded the registry with 18 real pairs across Arbitrum, OP Mainnet, Base, Polygon and Nomad. Most are fine:
Arbitrum's USDC gateway sits around 103%, the OP DAI bridge around 147%. Six are not:

- The five Nomad tokens on Moonbeam, between 0% and 0.2% backed. (Moonbeam itself hasn't produced a block since
  August 10th, so those checks are pinned to its last finalized block and the first Ethereum block after it.)
- USDT on Polygon, at well under 1% against the PoS bridge's vault. This one isn't a hack: Polygon's USDT is now also
  minted through USDT0's LayerZero adapter, so most of it was never locked in the PoS bridge. By the rule BackedBy
  enforces (the canonical vault against the canonical token), that bridge does not back it. I think that's worth
  knowing even if it isn't a scandal.

Every one of those rulings sat through a six-hour contest window before it became final, and every number on the site
links to a block explorer at the exact block it was read from.

## Things I'd tell you before you rely on it

It runs on GenLayer's Studio Dev network. It covers Ethereum to five chains through six bridge designs; anything else
needs its own authentication rule. It counts the supply on the chains it reads, so if a vault also backs tokens
somewhere it doesn't look, the pair looks better than it is, never worse. And it depends on public RPCs, which are
not always in a good mood; when they aren't, you get INCONCLUSIVE, not a wrong answer.

The code, the tests (400+ of them, plus the attack round), and a script that checks the deployed bytecode against the
commit byte for byte are all on GitHub: https://github.com/kenil1710/backedby. The live board is at
https://backedby-ledger.vercel.app.
