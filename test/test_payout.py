"""Payouts: the one way GEN leaves the registry.

Studio Dev skips an internal emit_transfer (declared budget 0) and credits the
value back to the contract, so a registry that used it marked payouts claimed
that never arrived. Every payout now leaves through _send, an external value
message (gl.evm.Account(...).emit_call), posted in the same transaction that
marks it claimed. These tests pin that down.

    cd test && python3 -m unittest -q test_payout
"""
import ast
import unittest

import fixtures as F
import stub
import world
from fixtures import RG, GEN, OPERATOR, CHALLENGER, CONTESTER, STRANGER, DEPLOYER
from test_registry import Base, MIN_STAKE, MIN_BOND, UNBOND
from test_static import src

Reverted = world.Reverted


def calls_named(tree, attr):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr]


class Static(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(src("BackedByRegistry"))
        self.fns = {n.name: n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)}

    def test_no_internal_transfer_anywhere(self):
        for name in ("BackedByRegistry", "ChainReader", "CollateralGate"):
            self.assertEqual(calls_named(ast.parse(src(name)), "emit_transfer"), [], name)

    def test_one_send_and_it_is_external(self):
        sends = calls_named(self.tree, "emit_call")
        self.assertEqual(len(sends), 1)
        self.assertIn(sends[0], list(ast.walk(self.fns["_send"])))
        self.assertIn("gl.evm.Account", ast.unparse(sends[0].func))
        self.assertEqual(ast.unparse(sends[0].args[1]), "b''")

    def test_only_claim_calls_send(self):
        users = sorted(f for f, n in self.fns.items() if f != "_send" and calls_named(n, "_send"))
        self.assertEqual(users, ["claim"])

    def test_claim_marks_before_it_sends(self):
        body = [ast.unparse(s) for s in self.fns["claim"].body]
        send_at = [i for i, s in enumerate(body) if "self._send(" in s][0]
        for needle in ("self.claimable[who] = u256(0)", "self.claimed_total ="):
            self.assertLess([i for i, s in enumerate(body) if needle in s][0], send_at, needle)

    def test_no_other_value_exit(self):
        t = src("BackedByRegistry")
        for word in ("emit(", ".emit_transfer(", "contract.deploy("):
            self.assertNotIn(word, t)


class Paths(Base):
    """Every kind of money the registry owes reaches its owner through the
    same external send, for exactly the amount credited."""

    def setUp(self):
        super().setUp()
        self.real = stub._Account.emit_transfer

        def refuse(*_a, **_k):
            raise AssertionError("emit_transfer must never be called")
        stub._Account.emit_transfer = refuse
        self.sent = []
        orig = stub._EvmAccount.emit_call

        def record(acct, value, data):
            self.sent.append((str(acct.address), int(value), data))
            return orig(acct, value, data)
        stub._EvmAccount.emit_call = record
        self.orig = orig

    def tearDown(self):
        stub._Account.emit_transfer = self.real
        stub._EvmAccount.emit_call = self.orig

    def claim(self, who):
        owed = self.s.claimable(who)
        n = len(self.sent)
        r = self.s.call(self.s.reg, "claim", sender=who)
        self.assertEqual(r["claimed"], str(owed))
        self.assertEqual(self.sent[n:], [(who, owed, b"")])
        self.assertEqual(self.s.claimable(who), 0)
        return owed

    def test_bounty_and_treasury(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.claim(CHALLENGER), MIN_STAKE + GEN // 2)
        self.assertEqual(self.claim(DEPLOYER), GEN // 2)
        self.assertLedger()

    def test_stake_refund_on_inconclusive(self):
        pid, bid = self.bonded()
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.s.w.advance(int(self.s.cfg()["read_timeout_s"]) + 1)
        self.s.call(self.s.reg, "expire", cid, sender=STRANGER)
        self.assertEqual(self.claim(CHALLENGER), MIN_STAKE)
        self.assertLedger()

    def test_bond_withdrawal(self):
        pid = self.s.pair("arb_usdc")
        bid = self.s.bond(pid, MIN_BOND)["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND + 1)
        self.s.call(self.s.reg, "withdraw_bond", bid)
        self.assertEqual(self.claim(OPERATOR), MIN_BOND)
        self.assertLedger()

    def test_payable_refusal_refund(self):
        r = self.s.call(self.s.reg, "bond", 999, sender=STRANGER, value=123)
        self.assertFalse(r["ok"])
        self.assertEqual(self.claim(STRANGER), 123)
        self.assertLedger()

    def test_contest_refund(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.s.w.advance(RG.MODES["DEMO"][2] + 1)
        self.s.call(self.s.reg, "expire", cid, sender=STRANGER)
        self.assertGreater(self.s.claimable(CONTESTER), 0)
        self.claim(CONTESTER)
        self.assertLedger()

    def test_drained_registry_holds_exactly_zero(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        for who in (CHALLENGER, DEPLOYER, OPERATOR):
            if self.s.claimable(who):
                self.claim(who)
        l = self.assertLedger()
        self.assertEqual(int(l["on_chain_balance"]), 0)
        self.assertEqual(sum(v for _, v, _ in self.sent), int(l["claimed"]))


class Refusals(Base):
    def test_balance_below_claim_marks_nothing(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        owed = self.s.claimable(CHALLENGER)
        self.s.w.instances[self.s.reg].balance = owed - 1
        before = self.s.ledger()
        with self.assertRaises(Reverted) as e:
            self.s.call(self.s.reg, "claim", sender=CHALLENGER)
        self.assertIn("REGISTRY_BALANCE_BELOW_CLAIM", e.exception.msg)
        self.assertEqual(self.s.claimable(CHALLENGER), owed)
        self.assertEqual(self.s.ledger()["claimed"], before["claimed"])

    def test_send_that_cannot_be_posted_marks_nothing(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        owed = self.s.claimable(CHALLENGER)
        orig = stub._EvmAccount.emit_call

        def fail(*_a, **_k):
            raise stub._UserError("send refused by the host")
        stub._EvmAccount.emit_call = fail
        try:
            with self.assertRaises(Reverted):
                self.s.call(self.s.reg, "claim", sender=CHALLENGER)
        finally:
            stub._EvmAccount.emit_call = orig
        self.assertEqual(self.s.claimable(CHALLENGER), owed)
        self.assertEqual(int(self.s.ledger()["claimed"]), 0)
        self.assertLedger()

    def test_nothing_to_claim(self):
        self.refuses("claim", why="NOTHING_TO_CLAIM", sender=STRANGER)


if __name__ == "__main__":
    unittest.main()
