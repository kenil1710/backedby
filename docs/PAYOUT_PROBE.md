# Payouts on Studio Dev: what delivers

Measured on 2026-10-17 with throwaway probe contracts (`test/probe/PayProbe.py`, `test/probe/PayProbeEth.py`,
runner `py-genlayer:5jycge4q…`, the newest one Studio Dev serves). Each probe was funded, then sent 0.01 GEN to a
fresh account; the result is the recipient's and the contract's `eth_getBalance` before and after finalization.

| Form | Transaction | Recipient Δ | Contract Δ | What Studio recorded |
|---|---|---|---|---|
| `gl.chain.Account(to).emit_transfer(v)` (internal, on finalized) | [`0x4727ecad…`](https://explorer-studio-dev.genlayer.com/tx/0x4727ecad9763ad6c93ec925191948043343a98f2988dc6ef967d255f8a5f4636) | 0 | 0 | `skipped: true, declaredBudget: 0, skippedRefunded` |
| same, `on="decided"` | [`0xd5a177a2…`](https://explorer-studio-dev.genlayer.com/tx/0xd5a177a26592837d957fc3a12a61b1285fcf623a7fd891da4944d5eb68a5c804) | 0 | 0 | `skipped: true, declaredBudget: 0` |
| balance-funded (`use_balance=True, fee_params=…`) | [`0x086e12a3…`](https://explorer-studio-dev.genlayer.com/tx/0x086e12a3474a04d814f64159f5c4da113a109301981b64d1706dec489542469f) | 0 | 0 | `SystemError: 6: forbidden` (contracts lack the permission) |
| sender-funded with explicit `fee_params` | [`0x123ed2ad…`](https://explorer-studio-dev.genlayer.com/tx/0x123ed2adea6b4e7574b891b4fed595fced3779e55e39e8c587930c17d0cc7dd4) | 0 | 0 | `SystemError: 2: inval` |
| **`gl.evm.Account(to).emit_call(v, b"")` (external EthSend)** | [`0xc463d49e…`](https://explorer-studio-dev.genlayer.com/tx/0xc463d49e6977523df78e95b49fa4402a64d3ca5e501993d2acd770f8d418d783) | **+0.01 GEN** | **−0.01 GEN** | delivered, not skipped; one External allocation, budget 500,000 gas × 0.3 gwei |

Why the internal form fails: the caller's estimate does attach an Internal message allocation (0.12 GEN for the
first demo claim), but GenVM emits the message with `declaredBudget` 0, Studio stores that 0 on the pending
transaction, and at finalization a value effect with a zero declared budget is skipped and its value credited back
to the contract. The first registry's demo claims all went that way: its ledger said "claimed" while its balance
still held every wei (docs/superseded/6f9431f/).

The registry therefore pays with the external send, and the client attaches an External allocation for the payee
(`tools/lib/payout.mjs`, which refuses to submit a claim without one). Every demo payout is then checked on chain:
the finalized transaction's value effect is delivered and not skipped, and the registry's `eth_getBalance` fell by
exactly the amount (docs/payouts.json, `tools/final_check.mjs`).
