"""BackedByRegistry end to end on the offline world: pairs, destinations,
bonds, challenges, monitoring, rulings, contests, finalize, timeouts,
withdrawals, claims, the ledger and the gate.

    cd test && python3 -m unittest -q test_registry
"""
import json
import random
import unittest

import fixtures as F
import stub
import world
from fixtures import CR, RG, Setup, USDC, WBTC, DAI, GEN, OPERATOR, CHALLENGER, CONTESTER, STRANGER, PATROL, DEPLOYER

Reverted = world.Reverted
MIN_STAKE = RG.MODES["DEMO"][5]
MIN_BOND = RG.MODES["DEMO"][6]
WINDOW = RG.MODES["DEMO"][0]
READ_TO = RG.MODES["DEMO"][1]
CONTEST_TO = RG.MODES["DEMO"][2]
UNBOND = RG.MODES["DEMO"][3]
MON = RG.MODES["DEMO"][4]


class Base(unittest.TestCase):
    mode = "DEMO"

    def setUp(self):
        stub.FORGE["payload"] = None
        stub.FORGE["mutate"] = None
        self.s = Setup(mode=self.mode)

    def stats(self):
        return self.s.view(self.s.reg, "get_stats")

    def assertLedger(self):
        l = self.s.ledger()
        self.assertTrue(l["invariant_holds"], l)
        self.assertTrue(l["bonds_recomputed_match"], l)
        self.assertTrue(l["open_recomputed_match"], l)
        self.assertEqual(int(l["on_chain_balance"]), int(l["held_now"]), l)
        return l

    def refuses(self, fn, *a, why="", sender=OPERATOR):
        before = self.stats()
        with self.assertRaises(Reverted) as e:
            self.s.call(self.s.reg, fn, *a, sender=sender)
        self.assertIn(why, e.exception.msg)
        self.assertEqual(self.stats(), before, "a refused call moved a counter")
        return e.exception.msg

    def refunded(self, out, why):
        self.assertFalse(out["ok"], out)
        self.assertIn(why, out["reason"])
        return out

    # a bonded pair, time moved past the bond start, fresh blocks mined
    def bonded(self, name="arb_usdc", amount=GEN, tol=0):
        pid = self.s.pair(name, tol=tol)
        bid = self.s.bond(pid, amount)["bond_id"]
        self.s.after_bond()
        return pid, bid

    def challenged(self, name="arb_usdc", short=False, amount=GEN, stake=MIN_STAKE):
        pid, bid = self.bonded(name, amount)
        if short:
            self.make_short(name)
        cid = self.s.challenge(bid, self.s.blocks(pid), stake=stake)["check_id"]
        return pid, bid, cid

    def make_short(self, name="arb_usdc", from_block=0):
        if name == "arb_usdc":
            self.s.net.balance("ethereum", USDC, F.ARB_GW, 10, from_block)
        elif name == "op_usdc":
            self.s.net.balance("ethereum", USDC, CR.OP_L1_BRIDGE, 10, from_block)
        elif name == "pol_usdc":
            self.s.net.balance("ethereum", USDC, F.POL_PRED, 10, from_block)

    def provisional(self, cid):
        self.s.read(cid)
        return self.s.rule(cid)


class Register(Base):
    def test_register_fields(self):
        pid = self.s.pair("arb_usdc", tol=25, label="Arbitrum USDC.e")
        p = self.s.view(self.s.reg, "get_pair", pid)
        self.assertEqual((p["kind"], p["vault"], p["source_token"], p["tolerance_bps"], p["max_gap_s"], p["label"]),
                         ("arbitrum", F.ARB_GW, USDC, 25, 600, "Arbitrum USDC.e"))
        self.assertEqual(p["dests"][0]["token"], F.ARB_USDC)
        self.assertEqual(p["dests"][0]["decimals"], 6)
        self.assertEqual(p["registered_by"], OPERATOR)

    def test_polygon_gap_frozen_300(self):
        p = self.s.view(self.s.reg, "get_pair", self.s.pair("pol_usdc"))
        self.assertEqual(p["max_gap_s"], 300)

    def test_every_kind_registers(self):
        for name in Setup.PAIRS:
            self.s.pair(name)
        self.assertEqual(self.stats()["pairs"], len(Setup.PAIRS))

    def test_tolerance_bounds(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        self.refuses("register_pair", str(a), -1, "x", why="TOLERANCE_OUT_OF_RANGE")
        self.refuses("register_pair", str(a), 1001, "x", why="TOLERANCE_OUT_OF_RANGE")
        self.assertTrue(self.s.call(self.s.reg, "register_pair", str(a), 1000, "x")["ok"])

    def test_auth_not_found(self):
        self.refuses("register_pair", "7", 0, "x", why="AUTH_7_NOT_FOUND")

    def test_auth_too_old(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        self.s.w.advance(3601)
        self.refuses("register_pair", str(a), 0, "x", why="TOO_OLD_REAUTHENTICATE")

    def test_auth_exactly_max_age_ok(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        self.s.w.advance(3600)
        self.assertTrue(self.s.call(self.s.reg, "register_pair", str(a), 0, "x")["ok"])

    def test_bad_ids(self):
        self.refuses("register_pair", "", 0, "x", why="POSITIVE_INTEGERS")
        self.refuses("register_pair", "a,b", 0, "x", why="POSITIVE_INTEGERS")
        self.refuses("register_pair", "0", 0, "x", why="POSITIVE_INTEGERS")
        self.refuses("register_pair", "1,1", 0, "x", why="DUPLICATE_AUTH_ID")
        self.refuses("register_pair", ",".join(str(i) for i in range(1, 11)), 0, "x", why="DESTINATIONS")

    def test_mixed_pairs_refused(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        b = self.s.auth("arbitrum", WBTC, F.ARB_WBTC)["auth_id"]
        self.refuses("register_pair", "%d,%d" % (a, b), 0, "x", why="AUTHS_ARE_NOT_ONE_PAIR")

    def test_same_dest_twice_refused(self):
        a = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        b = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        self.refuses("register_pair", "%d,%d" % (a, b), 0, "x", why="DUPLICATE_DESTINATION")

    def test_pair_exists(self):
        self.s.pair("arb_usdc")
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        self.refuses("register_pair", str(a), 0, "x", why="PAIR_EXISTS_AS_1_ADD_A_DESTINATION_INSTEAD")

    def test_multi_dest(self):
        a = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        b = self.s.auth("optimism", USDC, F.OP_USDC2)["auth_id"]
        r = self.s.call(self.s.reg, "register_pair", "%d,%d" % (a, b), 0, "OP USDC")
        self.assertEqual(r["destinations"], 2)

    def test_label_cleaned(self):
        pid = self.s.pair("arb_usdc", label="<b>hi</b>‮")
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["label"], "bhi/b")

    def test_same_token_different_vaults_are_different_pairs(self):
        self.s.pair("arb_usdc")
        self.s.pair("op_usdc")
        self.s.pair("base_usdc")
        self.s.pair("pol_usdc")
        self.s.pair("nomad_usdc")
        self.assertEqual(self.stats()["pairs"], 5)

    def test_no_such_pair_view(self):
        self.assertEqual(self.s.view(self.s.reg, "get_pair", 3), {"found": False})


class Destinations(Base):
    def test_add_ok(self):
        pid = self.s.pair("op_usdc")
        b = self.s.auth("optimism", USDC, F.OP_USDC2, sender=STRANGER)["auth_id"]
        r = self.s.call(self.s.reg, "add_destination", pid, b, sender=STRANGER)
        self.assertEqual(r["destinations"], 2)
        p = self.s.view(self.s.reg, "get_pair", pid)
        self.assertEqual(p["dests"][1]["added_by"], STRANGER)

    def test_add_wrong_pair(self):
        pid = self.s.pair("op_usdc")
        b = self.s.auth("base", USDC, F.BASE_USDC)["auth_id"]
        self.refuses("add_destination", pid, b, why="AUTH_IS_FOR_ANOTHER_PAIR")

    def test_add_existing(self):
        pid = self.s.pair("op_usdc")
        b = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        self.refuses("add_destination", pid, b, why="DESTINATION_ALREADY_IN_PAIR_1")

    def test_add_stale_auth(self):
        pid = self.s.pair("op_usdc")
        b = self.s.auth("optimism", USDC, F.OP_USDC2)["auth_id"]
        self.s.w.advance(3601)
        self.refuses("add_destination", pid, b, why="TOO_OLD")

    def test_add_no_pair(self):
        self.refuses("add_destination", 9, 1, why="NO_SUCH_PAIR")

    def test_add_limit(self):
        pid = self.s.pair("op_usdc")
        for i in range(RG.MAX_DESTS - 1):
            t = F.addr(9000 + i)
            self.s.net.token("optimism", t, 6, 0)
            self.s.net.opstack("optimism", USDC, t)
            self.s.call(self.s.reg, "add_destination", pid, self.s.auth("optimism", USDC, t)["auth_id"])
        t = F.addr(9100)
        self.s.net.token("optimism", t, 6, 0)
        self.s.net.opstack("optimism", USDC, t)
        a = self.s.auth("optimism", USDC, t)["auth_id"]
        self.refuses("add_destination", pid, a, why="PAIR_HAS_8_DESTINATIONS")

    def test_omitted_destination_cannot_hide_supply(self):
        # the vault holds 500k; OP_USDC (500k) is registered, OP_USDC2 (300k, real deposits) was omitted
        n = self.s.net
        n.supply("optimism", F.OP_USDC2, 300_000 * 10 ** 6)
        n.deposits(CR.OP_L1_BRIDGE, USDC, F.OP_USDC2, 300_000 * 10 ** 6)
        n.supply("optimism", F.OP_USDC, 200_000 * 10 ** 6)
        pid = self.s.pair("op_usdc")
        self.s.after_bond()
        c1 = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(c1)["verdict"], "BACKED")
        # the vault really holds only 400k against 500k outstanding
        n.balance("ethereum", USDC, CR.OP_L1_BRIDGE, 400_000 * 10 ** 6)
        self.s.after_bond()
        self.s.finalize_after_window(c1)
        a = self.s.auth("optimism", USDC, F.OP_USDC2, sender=STRANGER)["auth_id"]
        self.s.call(self.s.reg, "add_destination", pid, a, sender=STRANGER)
        self.s.w.advance(MON)
        self.s.net.mine_to(self.s.w.now() - 60)
        c2 = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(c2)["verdict"], "UNDER_BACKED")

    def test_fake_destination_cannot_frame_an_honest_pair(self):
        pid, bid = self.bonded("op_usdc")
        a = self.s.auth("optimism", USDC, F.OP_FAKE, sender=STRANGER)["auth_id"]
        self.s.call(self.s.reg, "add_destination", pid, a, sender=STRANGER)
        cid = self.s.challenge(bid, self.s.blocks(pid), sender=STRANGER)["check_id"]
        out = self.provisional(cid)
        self.assertEqual(out["verdict"], "BACKED")
        self.assertEqual(self.s.check(cid)["ruling1"]["counted"], [str(500_000 * 10 ** 6), "1"])

    def test_open_check_keeps_its_destinations(self):
        pid = self.s.pair("op_usdc")
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        a = self.s.auth("optimism", USDC, F.OP_USDC2)["auth_id"]
        self.s.call(self.s.reg, "add_destination", pid, a)
        self.assertEqual(len(self.s.check(cid)["dests"]), 1)
        self.s.read(cid)
        self.assertEqual(len(self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)["reading"]["dests"]), 1)


class Bonds(Base):
    def test_bond_ok(self):
        pid = self.s.pair()
        b = self.s.bond(pid, GEN)
        bd = self.s.view(self.s.reg, "get_bond", b["bond_id"])
        self.assertEqual((bd["status"], bd["amount"], bd["operator"], bd["since"]), ("ACTIVE", str(GEN), OPERATOR, F.NOW))
        self.assertLedger()

    def test_bond_below_min_refunded(self):
        pid = self.s.pair()
        self.refunded(self.s.bond(pid, MIN_BOND - 1), "BOND_BELOW_MINIMUM")
        self.assertEqual(self.s.claimable(OPERATOR), MIN_BOND - 1)
        self.assertEqual(self.stats()["bonds"], 0)
        self.assertLedger()

    def test_bond_exactly_min_ok(self):
        self.assertTrue(self.s.bond(self.s.pair(), MIN_BOND)["ok"])

    def test_bond_no_pair_refunded(self):
        self.refunded(self.s.bond(5, GEN), "NO_SUCH_PAIR")
        self.assertLedger()

    def test_bond_too_large_refunded(self):
        pid = self.s.pair()
        self.refunded(self.s.bond(pid, RG.MAX_AMOUNT + 1), "BOND_TOO_LARGE")

    def test_top_up(self):
        pid = self.s.pair()
        bid = self.s.bond(pid)["bond_id"]
        r = self.s.call(self.s.reg, "top_up", bid, value=GEN)
        self.assertEqual(r["amount"], str(2 * GEN))
        self.assertLedger()

    def test_top_up_not_operator(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.refunded(self.s.call(self.s.reg, "top_up", bid, sender=STRANGER, value=GEN), "ONLY_THE_OPERATOR")
        self.assertEqual(self.s.claimable(STRANGER), GEN)

    def test_top_up_unbonding(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.refunded(self.s.call(self.s.reg, "top_up", bid, value=GEN), "BOND_IS_UNBONDING")

    def test_top_up_zero(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.refunded(self.s.call(self.s.reg, "top_up", bid, value=0), "AMOUNT_OUT_OF_RANGE")

    def test_top_up_no_bond(self):
        self.refunded(self.s.call(self.s.reg, "top_up", 4, value=GEN), "NO_SUCH_BOND")

    def test_unbond_only_operator(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.refuses("request_unbond", bid, why="ONLY_THE_OPERATOR", sender=STRANGER)

    def test_unbond_twice(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.refuses("request_unbond", bid, why="BOND_IS_UNBONDING")

    def test_withdraw_before_request(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.refuses("withdraw_bond", bid, why="REQUEST_UNBOND_FIRST")

    def test_withdraw_delay_boundary(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND - 1)
        self.refuses("withdraw_bond", bid, why="WITHDRAWABLE_AT_")
        self.s.w.advance(1)
        r = self.s.call(self.s.reg, "withdraw_bond", bid)
        self.assertEqual(r["credited"], str(GEN))
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "WITHDRAWN")
        self.assertEqual(self.s.claimable(OPERATOR), GEN)
        self.assertLedger()

    def test_withdraw_twice(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND)
        self.s.call(self.s.reg, "withdraw_bond", bid)
        self.refuses("withdraw_bond", bid, why="BOND_IS_WITHDRAWN")

    def test_withdraw_not_operator(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND)
        self.refuses("withdraw_bond", bid, why="ONLY_THE_OPERATOR", sender=STRANGER)

    def test_withdraw_blocked_by_open_check(self):
        pid, bid, cid = self.challenged()
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND)
        self.refuses("withdraw_bond", bid, why="CHECK_1_IS_OPEN_ON_THIS_BOND")
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertTrue(self.s.call(self.s.reg, "withdraw_bond", bid)["ok"])
        self.assertEqual(self.s.claimable(OPERATOR), GEN + MIN_STAKE)
        self.assertLedger()

    def test_claim(self):
        bid = self.s.bond(self.s.pair())["bond_id"]
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND)
        self.s.call(self.s.reg, "withdraw_bond", bid)
        r = self.s.call(self.s.reg, "claim")
        self.assertEqual(r["claimed"], str(GEN))
        self.assertEqual(stub.BALANCES.get(OPERATOR, 0) >= GEN, True)
        self.refuses("claim", why="NOTHING_TO_CLAIM")
        l = self.assertLedger()
        self.assertEqual(l["held_now"], "0")

    def test_slashed_bond_cannot_be_withdrawn(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.refuses("withdraw_bond", bid, why="BOND_IS_SLASHED")
        self.refuses("request_unbond", bid, why="BOND_IS_SLASHED")


class Challenge(Base):
    def test_challenge_ok(self):
        pid, bid, cid = self.challenged()
        c = self.s.check(cid)
        self.assertEqual((c["status"], c["purpose"], c["bond_id"], c["stake"]), ("OPEN", "CHALLENGE", bid, str(MIN_STAKE)))
        self.assertEqual(c["read_deadline"], self.s.w.now() + READ_TO)
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["open_check"], cid)
        self.assertLedger()

    def test_stake_below_min(self):
        pid, bid = self.bonded()
        self.refunded(self.s.challenge(bid, self.s.blocks(pid), stake=MIN_STAKE - 1), "STAKE_BELOW_MINIMUM")
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE - 1)
        self.assertLedger()

    def test_stake_zero(self):
        pid, bid = self.bonded()
        self.refunded(self.s.challenge(bid, self.s.blocks(pid), stake=0), "STAKE_BELOW_MINIMUM")

    def test_operator_cannot_challenge_self(self):
        pid, bid = self.bonded()
        self.refunded(self.s.challenge(bid, self.s.blocks(pid), sender=OPERATOR), "OPERATOR_CANNOT_CHALLENGE")

    def test_no_bond(self):
        self.s.pair()
        self.refunded(self.s.challenge(3, {"ethereum": 1, "arbitrum": 1}), "NO_SUCH_BOND")

    def test_bad_blocks(self):
        pid, bid = self.bonded()
        self.refunded(self.s.challenge(bid, {"ethereum": 1}), "BLOCKS_MUST_NAME_EXACTLY")
        self.refunded(self.s.challenge(bid, {"ethereum": 1, "base": 1}), "BLOCKS_MUST_NAME_EXACTLY")
        self.assertLedger()

    def test_blocks_text_not_json(self):
        pid, bid = self.bonded()
        r = self.s.call(self.s.reg, "challenge", bid, "{nope", sender=CHALLENGER, value=MIN_STAKE)
        self.refunded(r, "BLOCKS_NOT_JSON")

    def test_double_check_refused(self):
        pid, bid, cid = self.challenged()
        r = self.s.challenge(bid, self.s.blocks(pid), sender=STRANGER)
        self.refunded(r, "CHECK_1_IS_OPEN_ON_THIS_PAIR")
        self.assertEqual(self.s.claimable(STRANGER), MIN_STAKE)
        self.assertLedger()

    def test_double_check_other_bond_same_pair_refused(self):
        pid, bid = self.bonded()
        bid2 = self.s.bond(pid, GEN, sender=STRANGER)["bond_id"]
        self.s.after_bond()
        self.s.challenge(bid, self.s.blocks(pid))
        self.refunded(self.s.challenge(bid2, self.s.blocks(pid)), "IS_OPEN_ON_THIS_PAIR")

    def test_under_backed_slashes(self):
        pid, bid, cid = self.challenged(short=True)
        out = self.provisional(cid)
        self.assertEqual((out["status"], out["verdict"]), ("PROVISIONAL", "UNDER_BACKED"))
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["amount"], str(GEN), "nothing moves while provisional")
        f = self.s.finalize_after_window(cid)
        self.assertEqual(f["payouts"]["slash"], str(GEN))
        self.assertEqual(f["payouts"]["bounty"], str(GEN // 2))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE + GEN // 2)
        self.assertEqual(self.s.claimable(DEPLOYER), GEN // 2)
        b = self.s.view(self.s.reg, "get_bond", bid)
        self.assertEqual((b["status"], b["amount"], b["slashed"]), ("SLASHED", "0", str(GEN)))
        self.assertLedger()

    def test_backed_stake_goes_to_bond(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        f = self.s.finalize_after_window(cid)
        self.assertEqual(f["payouts"]["bond_in"], str(MIN_STAKE))
        b = self.s.view(self.s.reg, "get_bond", bid)
        self.assertEqual((b["amount"], b["won"]), (str(GEN + MIN_STAKE), str(MIN_STAKE)))
        self.assertEqual(self.s.claimable(CHALLENGER), 0)
        self.assertLedger()

    def test_blocks_before_bond_refunded(self):
        pid = self.s.pair()
        old = self.s.blocks(pid, ts=F.NOW - 900)
        bid = self.s.bond(pid)["bond_id"]
        self.s.after_bond()
        self.make_short()
        cid = self.s.challenge(bid, old)["check_id"]
        out = self.provisional(cid)
        self.assertEqual((out["status"], out["reason"]), ("INCONCLUSIVE", "SOURCE_BLOCK_BEFORE_THE_BOND_STARTED"))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["amount"], str(GEN))
        self.assertLedger()

    def test_blocks_after_unbond_refunded(self):
        pid, bid = self.bonded()
        self.s.call(self.s.reg, "request_unbond", bid)
        stop = self.s.w.now()
        self.s.w.advance(1300)
        self.s.net.mine_to(self.s.w.now() - 60)
        self.make_short()
        cid = self.s.challenge(bid, self.s.blocks(pid, ts=stop + 60))["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "SOURCE_BLOCK_AFTER_THE_BOND_STOPPED")

    def test_unbonding_bond_still_slashable_for_covered_blocks(self):
        pid, bid = self.bonded()
        covered = self.s.blocks(pid)
        self.make_short(from_block=0)
        self.s.call(self.s.reg, "request_unbond", bid)
        cid = self.s.challenge(bid, covered)["check_id"]
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "SLASHED")

    def test_challenge_withdrawn_bond_refunded(self):
        pid, bid = self.bonded()
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND)
        self.s.call(self.s.reg, "withdraw_bond", bid)
        self.refunded(self.s.challenge(bid, self.s.blocks(pid)), "BOND_IS_WITHDRAWN")

    def test_challenge_slashed_bond_refunded(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.refunded(self.s.challenge(bid, self.s.blocks(pid), sender=STRANGER), "BOND_IS_SLASHED")

    def test_data_inconclusive_refunds_and_becomes_latest(self):
        pid, bid, cid = self.challenged()
        stub.WEB.tamper[CR.CHAINS["arbitrum"][1][1]] = lambda req, ans: dict(ans, result=F.w(1)) \
            if req["method"] == "eth_call" else ans
        out = self.provisional(cid)
        self.assertEqual((out["status"], out["reason"]), ("INCONCLUSIVE", "RPC_DISAGREE"))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_latest", pid)["check_id"], cid)
        self.assertLedger()

    def test_pin_inconclusive_not_latest(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid, gap=700)
        cid = self.s.challenge(bid, bl)["check_id"]
        out = self.provisional(cid)
        self.assertTrue(out["reason"].startswith("GAP_"))
        self.assertFalse(self.s.view(self.s.reg, "get_latest", pid)["found"])

    def test_source_older_than_dest_refunded(self):
        pid, bid = self.bonded()
        st = self.s.net.ts("ethereum", self.s.blocks(pid)["ethereum"])
        bl = {"ethereum": self.s.blocks(pid)["ethereum"], "arbitrum": self.s.net.block_at("arbitrum", st + 5)}
        cid = self.s.challenge(bid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "SOURCE_BLOCK_OLDER_THAN_ARBITRUM_BLOCK")
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)

    def test_gap_exactly_600_rules(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid)
        st = self.s.net.ts("ethereum", bl["ethereum"])
        bl["arbitrum"] = self.s.net.block_at("arbitrum", st - 600)
        self.assertEqual(st - self.s.net.ts("arbitrum", bl["arbitrum"]), 600)
        cid = self.s.challenge(bid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "BACKED")

    def test_gap_601_inconclusive(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid)
        st = self.s.net.ts("ethereum", bl["ethereum"])
        bl["arbitrum"] = self.s.net.block_at("arbitrum", st - 601)
        cid = self.s.challenge(bid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "GAP_601S_OVER_600S")

    def test_tolerance_frozen_at_registration(self):
        pid, bid = self.bonded(tol=100)
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 990_000 * 10 ** 6)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "BACKED")

    def test_tolerance_one_below_edge(self):
        pid, bid = self.bonded(tol=100)
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 990_000 * 10 ** 6 - 1)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "UNDER_BACKED")

    def test_decimals_changed_after_registration(self):
        pid, bid = self.bonded()
        self.s.net.decimals("arbitrum", F.ARB_USDC, 18)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        out = self.provisional(cid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertTrue(out["reason"].startswith("DECIMALS_MISMATCH"))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)


class Monitor(Base):
    def test_monitor_ok(self):
        pid = self.s.pair()
        self.s.after_bond()
        r = self.s.monitor(pid, self.s.blocks(pid))
        c = self.s.check(r["check_id"])
        self.assertEqual((c["purpose"], c["stake"], c["bond_id"]), ("MONITOR", "0", 0))

    def ruled_inconclusive(self, pid, bl, sender=PATROL):
        """A monitoring check that is RULED (data INCONCLUSIVE: the RPCs
        disagree) closes at once and counts against the rate limit."""
        url = CR.CHAINS["arbitrum"][1][1]
        stub.WEB.tamper[url] = lambda req, ans: dict(ans, result=F.w(1)) if req["method"] == "eth_call" else ans
        cid = self.s.monitor(pid, bl, sender=sender)["check_id"]
        self.provisional(cid)
        del stub.WEB.tamper[url]
        self.assertEqual(self.s.check(cid)["status"], "INCONCLUSIVE")
        return cid

    def test_rate_limit_exact(self):
        pid = self.s.pair()
        self.s.after_bond()
        bl = self.s.blocks(pid)
        self.ruled_inconclusive(pid, bl)
        t0 = self.s.view(self.s.reg, "get_pair", pid)["last_monitor_at"]
        self.assertEqual(t0, self.s.w.now())
        self.s.w.set_time(t0 + MON - 1)
        self.refuses("monitor", pid, json.dumps(bl), why="RATE_LIMITED_UNTIL_" + str(t0 + MON), sender=PATROL)
        self.s.w.set_time(t0 + MON)
        self.assertTrue(self.s.monitor(pid, bl)["ok"])

    def test_rate_limit_applies_to_everyone(self):
        pid = self.s.pair()
        self.s.after_bond()
        bl = self.s.blocks(pid)
        self.ruled_inconclusive(pid, bl, sender=PATROL)
        self.refuses("monitor", pid, json.dumps(bl), why="RATE_LIMITED_UNTIL_", sender=STRANGER)

    def test_junk_pins_do_not_use_up_the_rate_limit(self):
        pid = self.s.pair()
        self.s.after_bond()
        bl = self.s.blocks(pid)
        junk = dict(bl, arbitrum=self.s.net.block_at("arbitrum", self.s.net.ts("ethereum", bl["ethereum"]) - 900))
        cid = self.s.monitor(pid, junk, sender=STRANGER)["check_id"]
        self.provisional(cid)
        self.assertEqual(self.s.check(cid)["status"], "INCONCLUSIVE")
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["last_monitor_at"], 0)
        self.assertTrue(self.s.monitor(pid, bl, sender=PATROL)["ok"])

    def test_monitor_after_timeout(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.s.w.advance(READ_TO)
        self.s.call(self.s.reg, "expire", cid, sender=PATROL)
        self.assertTrue(self.s.monitor(pid, self.s.blocks(pid))["ok"])

    def test_monitor_while_open_refused(self):
        pid = self.s.pair()
        self.s.after_bond()
        self.s.monitor(pid, self.s.blocks(pid))
        self.s.w.advance(MON)
        self.refuses("monitor", pid, json.dumps(self.s.blocks(pid)), why="CHECK_1_IS_OPEN", sender=PATROL)

    def test_monitor_bad_blocks(self):
        pid = self.s.pair()
        self.refuses("monitor", pid, '{"ethereum": 5}', why="BLOCKS_MUST_NAME", sender=PATROL)

    def test_monitor_no_pair(self):
        self.refuses("monitor", 4, "{}", why="NO_SUCH_PAIR", sender=PATROL)

    def test_challenge_supersedes_monitor(self):
        pid, bid = self.bonded()
        m = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        r = self.s.challenge(bid, self.s.blocks(pid))
        self.assertEqual(r["superseded"], m)
        mc = self.s.check(m)
        self.assertEqual((mc["status"], mc["how"]), ("INCONCLUSIVE", "SUPERSEDED"))
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["open_check"], r["check_id"])
        self.assertFalse(self.s.view(self.s.reg, "get_latest", pid)["found"])
        # its reading can no longer be recorded
        with self.assertRaises(Reverted):
            self.s.read(m)

    def test_challenge_supersedes_contested_monitor_refunds_contest(self):
        pid, bid = self.bonded()
        m = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(m)
        self.s.call(self.s.reg, "contest", m, sender=CONTESTER, value=MIN_STAKE)
        self.s.challenge(bid, self.s.blocks(pid))
        self.assertEqual(self.s.claimable(CONTESTER), MIN_STAKE)
        self.assertLedger()

    def test_monitor_becomes_latest_after_final(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.assertFalse(self.s.view(self.s.reg, "get_latest", pid)["found"])
        self.s.finalize_after_window(cid)
        l = self.s.view(self.s.reg, "get_latest", pid)
        self.assertEqual((l["check_id"], l["verdict"]), (cid, "BACKED"))


class Rule(Base):
    def test_rule_before_read(self):
        pid, bid, cid = self.challenged()
        self.refuses("rule", cid, why="NOT_READ_YET", sender=PATROL)

    def test_rule_twice(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.refuses("rule", cid, why="NOTHING_TO_RULE_ON_IN_PROVISIONAL", sender=PATROL)

    def test_rule_no_check(self):
        self.refuses("rule", 9, why="NO_SUCH_CHECK", sender=PATROL)

    def test_reading_for_other_request_refused(self):
        pid, bid, cid = self.challenged()
        self.s.read(cid)
        reader = self.s.w.instances[self.s.reader]
        key = self.s.reg.lower() + "|" + str(cid) + "|1"
        reader.readings[key].request_sha = "0" * 64
        self.refuses("rule", cid, why="READING_IS_FOR_ANOTHER_REQUEST", sender=PATROL)

    def test_provisional_deadline(self):
        pid, bid, cid = self.challenged()
        out = self.provisional(cid)
        self.assertEqual(out["contestable_until"], self.s.w.now() + WINDOW)

    def test_rule_after_read_deadline_still_rules(self):
        pid, bid, cid = self.challenged()
        self.s.read(cid)
        self.s.w.advance(READ_TO + 50)
        self.assertEqual(self.s.rule(cid)["status"], "PROVISIONAL")

    def test_ruling_numbers_from_code(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        r = self.s.check(cid)["ruling1"]
        self.assertEqual((r["locked_norm"], r["supply_norm"], r["ratio_bps"]),
                         (str(10 ** 12), str(10 ** 12), 10000))


class Contest(Base):
    def contested(self, short=False):
        pid, bid, cid = self.challenged(short=short)
        self.provisional(cid)
        r = self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.assertTrue(r["ok"], r)
        return pid, bid, cid

    def test_contest_ok(self):
        pid, bid, cid = self.contested()
        c = self.s.check(cid)
        self.assertEqual((c["status"], c["round"], c["contester"]), ("CONTESTED", 2, CONTESTER))
        self.assertLedger()

    def test_contest_window_boundary(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.w.advance(WINDOW - 1)
        self.assertTrue(self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)["ok"])

    def test_contest_at_deadline_refunded(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.w.advance(WINDOW)
        r = self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.refunded(r, "CONTEST_WINDOW_CLOSED_AT_")
        self.assertEqual(self.s.claimable(CONTESTER), MIN_STAKE)

    def test_contest_low_stake(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.refunded(self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=1), "STAKE_BELOW_MINIMUM")

    def test_contest_open_check(self):
        pid, bid, cid = self.challenged()
        self.refunded(self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE), "NOT_PROVISIONAL_OPEN")

    def test_contest_twice(self):
        pid, bid, cid = self.contested()
        self.refunded(self.s.call(self.s.reg, "contest", cid, sender=STRANGER, value=MIN_STAKE),
                      "NOT_PROVISIONAL_CONTESTED")

    def test_contest_no_check(self):
        self.refunded(self.s.call(self.s.reg, "contest", 3, sender=STRANGER, value=MIN_STAKE), "NO_SUCH_CHECK")

    def test_contest_upheld_backed_stake_to_bond(self):
        pid, bid, cid = self.contested()
        self.s.read(cid, 2)
        out = self.s.rule(cid)
        self.assertEqual((out["status"], out["verdict"]), ("FINAL", "BACKED"))
        self.assertEqual(self.s.check(cid)["how"], "CONTEST_UPHELD_RULING")
        b = self.s.view(self.s.reg, "get_bond", bid)
        self.assertEqual(b["amount"], str(GEN + 2 * MIN_STAKE))
        self.assertEqual(self.s.claimable(CONTESTER), 0)
        self.assertLedger()

    def test_contest_upheld_under_stake_to_challenger(self):
        pid, bid, cid = self.contested(short=True)
        self.s.read(cid, 2)
        out = self.s.rule(cid)
        self.assertEqual(out["verdict"], "UNDER_BACKED")
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE + GEN // 2 + MIN_STAKE)
        self.assertLedger()

    def test_contest_on_monitor_lost_goes_to_treasury(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.s.read(cid, 2)
        self.s.rule(cid)
        self.assertEqual(self.s.claimable(DEPLOYER), MIN_STAKE)
        self.assertLedger()

    def test_contest_disagrees_all_refunded(self):
        pid, bid, cid = self.contested(short=True)
        # the archive answers differently for the same pinned block on the re-read
        bl = self.s.check(cid)["blocks"]
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 10 ** 13, from_block=bl["ethereum"])
        self.s.read(cid, 2)
        out = self.s.rule(cid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        c = self.s.check(cid)
        self.assertEqual((c["how"], c["reason"]), ("CONTEST_DISAGREES", "CONTEST_DISAGREES"))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)
        self.assertEqual(self.s.claimable(CONTESTER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["amount"], str(GEN))
        self.assertEqual(self.s.view(self.s.reg, "get_latest", pid)["check_id"], cid)
        self.assertLedger()

    def test_contest_reread_data_inconclusive(self):
        pid, bid, cid = self.contested()
        stub.WEB.tamper[CR.CHAINS["ethereum"][1][1]] = lambda req, ans: dict(ans, result=F.w(1)) \
            if req["method"] == "eth_call" else ans
        self.s.read(cid, 2)
        out = self.s.rule(cid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertTrue(self.s.check(cid)["reason"].startswith("CONTEST_REREAD_INCONCLUSIVE:RPC_DISAGREE"))
        self.assertLedger()

    def test_contest_reread_outage_retries_not_recorded(self):
        pid, bid, cid = self.contested()
        stub.WEB.down.add(CR.CHAINS["ethereum"][1][0])
        with self.assertRaises(Reverted) as e:
            self.s.read(cid, 2)
        self.assertIn("RETRY: RPC_UNREADABLE", e.exception.msg)
        self.assertFalse(self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 2)["found"])
        stub.WEB.down.clear()
        self.s.read(cid, 2)
        self.assertEqual(self.s.rule(cid)["status"], "FINAL")

    def test_contest_timeout_first_ruling_stands(self):
        pid, bid, cid = self.contested(short=True)
        self.s.w.advance(CONTEST_TO - 1)
        self.refuses("expire", cid, why="REREAD_DEADLINE_AT_", sender=PATROL)
        self.s.w.advance(1)
        out = self.s.call(self.s.reg, "expire", cid, sender=PATROL)
        self.assertEqual((out["status"], out["verdict"]), ("FINAL", "UNDER_BACKED"))
        self.assertEqual(self.s.check(cid)["how"], "TIMEOUT_CONTEST_UNREAD")
        self.assertEqual(self.s.claimable(CONTESTER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "SLASHED")
        self.assertLedger()

    def test_contest_timeout_refused_when_reading_exists(self):
        pid, bid, cid = self.contested()
        self.s.read(cid, 2)
        self.s.w.advance(CONTEST_TO)
        self.refuses("expire", cid, why="A_READING_EXISTS_CALL_RULE", sender=PATROL)


class Finalize(Base):
    def test_before_deadline(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.w.advance(WINDOW - 1)
        self.refuses("finalize", cid, why="CONTESTABLE_UNTIL_", sender=PATROL)

    def test_at_deadline(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.w.advance(WINDOW)
        self.assertEqual(self.s.call(self.s.reg, "finalize", cid, sender=STRANGER)["status"], "FINAL")

    def test_twice(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.refuses("finalize", cid, why="NOT_PROVISIONAL_FINAL", sender=PATROL)

    def test_open(self):
        pid, bid, cid = self.challenged()
        self.refuses("finalize", cid, why="NOT_PROVISIONAL_OPEN", sender=PATROL)

    def test_no_check(self):
        self.refuses("finalize", 1, why="NO_SUCH_CHECK", sender=PATROL)

    def test_counters_after_final(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        s = self.stats()["counts"]
        self.assertEqual(s["status:FINAL"], 0)
        self.s.finalize_after_window(cid)
        s = self.stats()["counts"]
        self.assertEqual((s["status:FINAL"], s["verdict:UNDER_BACKED"], s["how:WINDOW_PASSED"]), (1, 1, 1))


class Expire(Base):
    def test_open_before_deadline(self):
        pid, bid, cid = self.challenged()
        self.s.w.advance(READ_TO - 1)
        self.refuses("expire", cid, why="READ_DEADLINE_AT_", sender=PATROL)

    def test_open_unread_at_deadline(self):
        pid, bid, cid = self.challenged()
        self.s.w.advance(READ_TO)
        out = self.s.call(self.s.reg, "expire", cid, sender=STRANGER)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        c = self.s.check(cid)
        self.assertEqual((c["how"], c["reason"]), ("TIMEOUT_UNREAD", "NO_READING_BEFORE_DEADLINE"))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["open_check"], 0)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["open_check"], 0)
        self.assertFalse(self.s.view(self.s.reg, "get_latest", pid)["found"])
        self.assertLedger()

    def test_open_with_reading_must_rule(self):
        pid, bid, cid = self.challenged()
        self.s.read(cid)
        self.s.w.advance(READ_TO)
        self.refuses("expire", cid, why="A_READING_EXISTS_CALL_RULE", sender=PATROL)
        self.assertEqual(self.s.rule(cid)["status"], "PROVISIONAL")

    def test_expired_cannot_be_read(self):
        pid, bid, cid = self.challenged()
        self.s.w.advance(READ_TO)
        self.s.call(self.s.reg, "expire", cid, sender=PATROL)
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_expire_provisional_refused(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.refuses("expire", cid, why="NOTHING_TO_EXPIRE_IN_PROVISIONAL", sender=PATROL)

    def test_expire_final_refused(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.refuses("expire", cid, why="NOTHING_TO_EXPIRE_IN_FINAL", sender=PATROL)

    def test_new_challenge_after_expiry(self):
        pid, bid, cid = self.challenged()
        self.s.w.advance(READ_TO)
        self.s.call(self.s.reg, "expire", cid, sender=PATROL)
        self.assertTrue(self.s.challenge(bid, self.s.blocks(pid))["ok"])


class StuckStates(Base):
    """Every non-terminal state has a permissionless exit that a stranger can
    take once its deadline passes, and every exit ends FINAL or INCONCLUSIVE."""

    def drive(self, cid):
        for _ in range(6):
            c = self.s.check(cid)
            if c["status"] in ("FINAL", "INCONCLUSIVE"):
                return c
            self.s.w.advance(max(WINDOW, READ_TO, CONTEST_TO) + 1)
            if c["status"] == "PROVISIONAL":
                self.s.call(self.s.reg, "finalize", cid, sender=STRANGER)
            else:
                rnd = 1 if c["status"] == "OPEN" else 2
                if self.s.view(self.s.reader, "get_reading", self.s.reg, cid, rnd)["found"]:
                    self.s.call(self.s.reg, "rule", cid, sender=STRANGER)
                else:
                    self.s.call(self.s.reg, "expire", cid, sender=STRANGER)
        return self.s.check(cid)

    def test_open_unread(self):
        pid, bid, cid = self.challenged()
        self.assertEqual(self.drive(cid)["status"], "INCONCLUSIVE")

    def test_open_read_unruled(self):
        pid, bid, cid = self.challenged()
        self.s.read(cid)
        self.assertEqual(self.drive(cid)["status"], "FINAL")

    def test_provisional(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.assertEqual(self.drive(cid)["status"], "FINAL")

    def test_contested_unread(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.assertEqual(self.drive(cid)["status"], "FINAL")

    def test_contested_read_unruled(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.s.read(cid, 2)
        self.assertEqual(self.drive(cid)["status"], "FINAL")

    def test_rpcs_down_forever(self):
        pid, bid, cid = self.challenged()
        stub.WEB.down.add("*")
        self.s.read(cid)        # round 1: recorded INCONCLUSIVE
        self.assertEqual(self.drive(cid)["status"], "INCONCLUSIVE")
        self.assertLedger()

    def test_rpcs_down_during_contest(self):
        pid, bid, cid = self.challenged()
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        stub.WEB.down.add("*")
        with self.assertRaises(Reverted):
            self.s.read(cid, 2)
        self.assertEqual(self.drive(cid)["status"], "FINAL")
        self.assertLedger()

    def test_every_bond_can_exit(self):
        pid, bid, cid = self.challenged()
        self.s.call(self.s.reg, "request_unbond", bid)
        self.drive(cid)
        self.s.w.advance(UNBOND)
        self.assertTrue(self.s.call(self.s.reg, "withdraw_bond", bid)["ok"])


class Gate(Base):
    def gate(self, pid):
        return self.s.view(self.s.gate, "is_backed", pid, self.s.w.now())

    def final_monitor(self, pid):
        self.s.w.advance(MON)
        self.s.net.mine_to(self.s.w.now() - 60)
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        if self.s.check(cid)["status"] == "PROVISIONAL":
            self.s.finalize_after_window(cid)
        return cid

    def test_never_checked(self):
        pid = self.s.pair()
        self.assertEqual(self.gate(pid)["reason"], "NEVER_CHECKED")

    def test_backed_then_stale(self):
        pid = self.s.pair()
        self.final_monitor(pid)
        g = self.gate(pid)
        self.assertTrue(g["backed"], g)
        self.s.w.advance(3600)
        self.assertTrue(self.gate(pid)["reason"].startswith("STALE_"))

    def test_provisional_does_not_count(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.assertEqual(self.gate(pid)["reason"], "NEVER_CHECKED")

    def test_under(self):
        pid = self.s.pair("nomad_usdc")
        self.final_monitor(pid)
        self.assertEqual(self.gate(pid)["reason"], "UNDER_BACKED")

    def test_newer_data_inconclusive_overrides(self):
        pid = self.s.pair()
        self.final_monitor(pid)
        stub.WEB.tamper[CR.CHAINS["arbitrum"][1][1]] = lambda req, ans: dict(ans, result=F.w(1)) \
            if req["method"] == "eth_call" else ans
        self.final_monitor(pid)
        self.assertEqual(self.gate(pid)["reason"], "INCONCLUSIVE")

    def test_older_blocks_finalized_later_do_not_override(self):
        pid = self.s.pair()
        self.s.after_bond()
        old = self.s.blocks(pid)
        newer_cid = self.final_monitor(pid)
        self.s.w.advance(MON)
        old_cid = self.s.monitor(pid, old)["check_id"]
        self.provisional(old_cid)
        self.s.finalize_after_window(old_cid)
        self.assertEqual(self.s.view(self.s.reg, "get_latest", pid)["check_id"], newer_cid)

    def test_borrow_allowed_and_refused_recorded(self):
        good = self.s.pair()
        bad = self.s.pair("nomad_usdc")
        self.final_monitor(good)
        self.final_monitor(bad)
        a = self.s.call(self.s.gate, "borrow", good, "1000", "test", sender=F.addr(77))
        b = self.s.call(self.s.gate, "borrow", bad, "1000", "test", sender=F.addr(77))
        self.assertEqual((a["allowed"], b["allowed"], b["reason"]), (True, False, "UNDER_BACKED"))
        at = self.s.view(self.s.gate, "get_attempts", 0, 10)
        self.assertEqual((at["total"], at["allowed"], at["refused"]), (2, 1, 1))

    def test_borrow_bad_amount(self):
        pid = self.s.pair()
        self.final_monitor(pid)
        self.assertEqual(self.s.call(self.s.gate, "borrow", pid, "-5", "")["reason"], "BAD_AMOUNT")

    def test_borrow_no_pair(self):
        self.assertEqual(self.s.call(self.s.gate, "borrow", 77, "5", "")["reason"], "NO_SUCH_PAIR")

    def test_gate_constructor_bounds(self):
        with self.assertRaises(Exception):
            self.s.w.deploy("CollateralGate", self.s.reg, 59, 0)
        with self.assertRaises(Exception):
            self.s.w.deploy("CollateralGate", "nope", 600, 0)


class Conservation(Base):
    """Sum in == sum out: every wei received is, at every step, in exactly one
    of bonds / open stakes / claimable / claimed, and once everything is
    settled and claimed the registry holds nothing."""

    def drain(self):
        for b in self.s.view(self.s.reg, "get_bonds", 0, 50)["bonds"]:
            if b["status"] == "ACTIVE":
                self.s.call(self.s.reg, "request_unbond", b["bond_id"], sender=b["operator"])
        self.s.w.advance(UNBOND + 1)
        for b in self.s.view(self.s.reg, "get_bonds", 0, 50)["bonds"]:
            if b["status"] == "UNBONDING" and b["open_check"] == 0:
                self.s.call(self.s.reg, "withdraw_bond", b["bond_id"], sender=b["operator"])
        for who in (OPERATOR, CHALLENGER, CONTESTER, STRANGER, PATROL, DEPLOYER):
            if self.s.claimable(who) > 0:
                self.s.call(self.s.reg, "claim", sender=who)

    def test_full_lifecycle_drains_to_zero(self):
        pid, bid, cid = self.challenged(short=False)
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=CONTESTER, value=MIN_STAKE)
        self.s.read(cid, 2)
        self.s.rule(cid)
        pid2, bid2, cid2 = self.challenged("pol_usdc", short=True)
        self.provisional(cid2)
        self.s.finalize_after_window(cid2)
        self.refunded(self.s.bond(99, GEN), "NO_SUCH_PAIR")
        self.assertLedger()
        self.drain()
        l = self.assertLedger()
        self.assertEqual((l["held_now"], l["bonds"], l["open_stakes"], l["claimable"]), ("0", "0", "0", "0"))
        self.assertEqual(int(l["received"]), int(l["claimed"]))
        self.assertEqual(sum(a for (_, _, a) in self.s.w.transfers), int(l["received"]))

    def test_random_sequences(self):
        rnd = random.Random(7)
        names = ["arb_usdc", "op_usdc", "pol_usdc", "nomad_usdc"]
        pids = [self.s.pair(n) for n in names]
        actors = [OPERATOR, CHALLENGER, CONTESTER, STRANGER]
        bonds = []
        self.s.after_bond()
        for step in range(160):
            op = rnd.choice(["bond", "challenge", "monitor", "read", "rule", "contest", "finalize", "expire",
                             "unbond", "withdraw", "claim", "advance", "short", "junk"])
            who = rnd.choice(actors)
            try:
                if op == "bond":
                    r = self.s.bond(rnd.choice(pids), rnd.choice([MIN_BOND - 1, MIN_BOND, GEN]), sender=who)
                    if r["ok"]:
                        bonds.append(r["bond_id"])
                elif op == "challenge" and bonds:
                    b = self.s.view(self.s.reg, "get_bond", rnd.choice(bonds))
                    self.s.challenge(b["bond_id"], self.s.blocks(b["pair_id"]), sender=who,
                                     stake=rnd.choice([1, MIN_STAKE, 2 * MIN_STAKE]))
                elif op == "monitor":
                    p = rnd.choice(pids)
                    self.s.monitor(p, self.s.blocks(p))
                elif op in ("read", "rule", "contest", "finalize", "expire") and self.stats()["checks"] > 0:
                    cid = rnd.randint(1, self.stats()["checks"])
                    c = self.s.check(cid)
                    if op == "read":
                        self.s.read(cid, 2 if c["status"] == "CONTESTED" else 1)
                    elif op == "contest":
                        self.s.call(self.s.reg, "contest", cid, sender=who, value=rnd.choice([0, MIN_STAKE]))
                    else:
                        self.s.call(self.s.reg, op, cid, sender=who)
                elif op == "unbond" and bonds:
                    b = self.s.view(self.s.reg, "get_bond", rnd.choice(bonds))
                    self.s.call(self.s.reg, "request_unbond", b["bond_id"], sender=b["operator"])
                elif op == "withdraw" and bonds:
                    b = self.s.view(self.s.reg, "get_bond", rnd.choice(bonds))
                    self.s.call(self.s.reg, "withdraw_bond", b["bond_id"], sender=b["operator"])
                elif op == "claim":
                    self.s.call(self.s.reg, "claim", sender=who)
                elif op == "advance":
                    self.s.w.advance(rnd.choice([10, 60, 120, 400]))
                    self.s.net.mine_to(self.s.w.now() - 60)
                elif op == "short":
                    self.make_short(rnd.choice(["arb_usdc", "op_usdc", "pol_usdc"]))
                elif op == "junk":
                    self.s.call(self.s.reg, rnd.choice(["bond", "top_up", "contest"]), 999, sender=who, value=7)
            except Reverted:
                pass
            self.assertLedger()
        # settle everything that is still open, then drain
        for cid in range(1, self.stats()["checks"] + 1):
            StuckStates.drive(self, cid)
        self.drain()
        l = self.assertLedger()
        self.assertEqual(l["held_now"], "0")
        self.assertEqual(int(l["received"]), int(l["claimed"]))


class Views(Base):
    def test_pagination_and_order(self):
        for n in ["arb_usdc", "arb_wbtc", "op_usdc"]:
            self.s.pair(n)
        self.s.after_bond()
        for pid in (1, 2, 3):
            self.s.monitor(pid, self.s.blocks(pid))
        cs = self.s.view(self.s.reg, "get_checks", 0, 2)
        self.assertEqual([c["check_id"] for c in cs["checks"]], [3, 2])
        self.assertEqual(self.s.view(self.s.reg, "get_checks", 2, 5)["checks"][0]["check_id"], 1)
        ps = self.s.view(self.s.reg, "get_pairs", 1, 99)
        self.assertEqual([p["pair_id"] for p in ps["pairs"]], [2, 3])
        self.assertEqual(ps["pairs"][0]["open"]["check_id"], 2)
        self.assertLessEqual(len(self.s.view(self.s.reg, "get_pairs", 0, 10 ** 6)["pairs"]), RG.MAX_PAGE)

    def test_config(self):
        c = self.s.cfg()
        self.assertEqual((c["mode"], c["window_s"], c["treasury"], c["bounty_bps"]), ("DEMO", 90, DEPLOYER, 5000))

    def test_check_request_view(self):
        pid, bid, cid = self.challenged()
        r = self.s.view(self.s.reg, "get_check_request", cid)
        self.assertEqual((r["ok"], r["round"], r["check_id"], r["vault"]), (True, 1, cid, F.ARB_GW))
        self.provisional(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_check_request", cid)["why"], "CHECK_IS_PROVISIONAL")

    def test_bad_mode(self):
        with self.assertRaises(Exception):
            self.s.w.deploy("BackedByRegistry", "TEST", self.s.reader)

    def test_bad_reader(self):
        with self.assertRaises(Exception):
            self.s.w.deploy("BackedByRegistry", "DEMO", "x")


class Canonical(Base):
    mode = "CANONICAL"

    def test_canonical_windows(self):
        c = self.s.cfg()
        self.assertEqual((c["window_s"], c["read_timeout_s"], c["unbond_delay_s"], c["monitor_interval_s"]),
                         (21600, 7200, 86400, 3600))
        self.assertEqual((c["min_stake"], c["min_bond"]), (str(10 ** 17), str(10 ** 18)))

    def test_six_hour_window(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.w.advance(21599)
        self.refuses("finalize", cid, why="CONTESTABLE_UNTIL_", sender=PATROL)
        self.s.w.advance(1)
        self.assertEqual(self.s.call(self.s.reg, "finalize", cid, sender=PATROL)["status"], "FINAL")

    def test_canonical_monitor_interval(self):
        pid = self.s.pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.w.advance(21600)
        self.s.call(self.s.reg, "finalize", cid, sender=PATROL)
        self.s.net.mine_to(self.s.w.now() - 60)
        self.assertTrue(self.s.monitor(pid, self.s.blocks(pid))["ok"])


if __name__ == "__main__":
    unittest.main()
