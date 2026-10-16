"""The internal attack round (docs/ATTACK_REPORT.md): one test class per
finding, each written as the attack and asserting the attack fails.

    cd test && python3 -m unittest -q test_attacks
"""
import json
import unittest

import fixtures as F
import stub
import world
from fixtures import CR, RG, GT, Setup, USDC, WBTC, DAI, GEN, OPERATOR, CHALLENGER, CONTESTER, STRANGER, PATROL, DEPLOYER
from test_registry import Base, MIN_STAKE, MIN_BOND, WINDOW, READ_TO, CONTEST_TO, UNBOND, MON

Reverted = world.Reverted


class H1LookalikeToken(Base):
    """A contract that answers remoteToken()=USDC and bridge()=L2StandardBridge
    but mints at will is added as a destination to frame an honest operator."""

    def test_frame_attempt_fails(self):
        pid, bid = self.bonded("op_usdc")
        self.s.net.supply("optimism", F.OP_FAKE, 10 ** 30)
        a = self.s.auth("optimism", USDC, F.OP_FAKE, sender=STRANGER)["auth_id"]
        self.s.call(self.s.reg, "add_destination", pid, a, sender=STRANGER)
        cid = self.s.challenge(bid, self.s.blocks(pid), sender=STRANGER)["check_id"]
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.s.check(cid)["verdict"], "BACKED")
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "ACTIVE")

    def test_cap_is_the_bridges_own_deposits(self):
        pid = self.s.pair("op_usdc")
        self.s.net.deposits(CR.OP_L1_BRIDGE, USDC, F.OP_USDC, 1)
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.assertEqual(self.s.check(cid)["ruling1"]["counted"], ["1"])

    def test_no_cap_for_kinds_without_deposits(self):
        pid = self.s.pair("arb_usdc")
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.s.read(cid)
        r = self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)["reading"]
        self.assertEqual(r["dests"][0]["deposits"], "")


class H2BridgeMigration(Base):
    """The bridge moves its escrow (or its mapping) after registration. Reading
    the old vault alone would show UNDER_BACKED and slash an honest operator."""

    def test_anchors_recorded(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)
        rec = self.s.view(self.s.reader, "get_auth", a["auth_id"])
        self.assertEqual(len(rec["anchors"]), 3)
        self.assertEqual(rec["anchors"][0][0:2], ["ethereum", CR.ARB_L1_ROUTER])

    def test_arbitrum_gateway_moved(self):
        pid, bid = self.bonded("arb_usdc")
        # router now points USDC at the USDC custom gateway and the old gateway is emptied
        self.s.net.arbitrum(USDC, F.ARB_USDC, gw="0xcee284f754e854890e311e3280b767f80797180d")
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 0)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        out = self.provisional(cid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertTrue(self.s.check(cid)["reason"].startswith("MAPPING_CHANGED:ethereum:" + CR.ARB_L1_ROUTER))
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["amount"], str(GEN))

    def test_dai_escrow_moved(self):
        pid, bid = self.bonded("arb_dai")
        self.s.net.fn("ethereum", F.ARB_DAI_GW, CR.S_L1_ESCROW, lambda d, b: F.wa(F.addr(31337)))
        self.s.net.balance("ethereum", DAI, F.ARB_DAI_ESCROW, 0)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["status"], "INCONCLUSIVE")
        self.assertIn("MAPPING_CHANGED", self.s.check(cid)["reason"])

    def test_polygon_predicate_moved(self):
        pid, bid = self.bonded("pol_usdc")
        self.s.net.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TYPE_TO_PRED, lambda d, b: F.wa(F.addr(4)))
        self.s.net.balance("ethereum", USDC, F.POL_PRED, 0)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertIn("MAPPING_CHANGED", self.provisional(cid)["reason"])

    def test_polygon_child_remapped(self):
        pid, bid = self.bonded("pol_usdc")
        self.s.net.polygon(USDC, F.addr(5555))
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertIn("MAPPING_CHANGED", self.provisional(cid)["reason"])

    def test_op_dai_escrow_moved(self):
        pid, bid = self.bonded("op_dai")
        self.s.net.fn("ethereum", CR.OP_DAI_L1_BRIDGE, CR.S_ESCROW, lambda d, b: F.wa(F.addr(8)))
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertIn("MAPPING_CHANGED", self.provisional(cid)["reason"])

    def test_nomad_router_reenrolled(self):
        pid = self.s.pair("nomad_usdc")
        self.s.net.nomad(USDC, F.BEAM_USDC, remote=F.addr(77))
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.assertIn("MAPPING_CHANGED:moonbeam", self.provisional(cid)["reason"])

    def test_mapping_change_is_the_latest_ruling(self):
        pid = self.s.pair("arb_usdc")
        self.s.net.arbitrum(USDC, F.ARB_WBTC)
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_latest", pid)["verdict"], "INCONCLUSIVE")

    def test_unchanged_mapping_rules_normally(self):
        pid, bid, cid = self.challenged("arb_dai")
        self.assertEqual(self.provisional(cid)["verdict"], "BACKED")


class H3PairSquatting(Base):
    """The first registrant picks a 10% tolerance for the canonical pair, so a
    strict pair could never exist and the lax one passes 9%-short vaults."""

    def test_strict_variant_still_registers(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC, sender=STRANGER)["auth_id"]
        lax = self.s.call(self.s.reg, "register_pair", str(a), 1000, "lax", sender=STRANGER)["pair_id"]
        b = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        strict = self.s.call(self.s.reg, "register_pair", str(b), 0, "strict")["pair_id"]
        self.assertNotEqual(lax, strict)

    def test_same_variant_twice_refused(self):
        self.s.pair("arb_usdc", tol=10)
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        self.refuses("register_pair", str(a), 10, "x", why="PAIR_EXISTS_AS_1")

    def test_gate_refuses_lax_tolerance(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)["auth_id"]
        pid = self.s.call(self.s.reg, "register_pair", str(a), 1000, "lax")["pair_id"]
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 910_000 * 10 ** 6)
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.s.check(cid)["verdict"], "BACKED")
        g = self.s.view(self.s.gate, "is_backed", pid, self.s.w.now())
        self.assertEqual((g["backed"], g["reason"]), (False, "TOLERANCE_1000BPS_OVER_50BPS"))

    def test_destination_added_per_variant(self):
        a = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        p0 = self.s.call(self.s.reg, "register_pair", str(a), 0, "x")["pair_id"]
        a = self.s.auth("optimism", USDC, F.OP_USDC)["auth_id"]
        p1 = self.s.call(self.s.reg, "register_pair", str(a), 5, "x")["pair_id"]
        for pid in (p0, p1):
            b = self.s.auth("optimism", USDC, F.OP_USDC2)["auth_id"]
            self.assertEqual(self.s.call(self.s.reg, "add_destination", pid, b)["destinations"], 2)


class M1PolygonMintable(Base):
    def test_mintable_type_refused(self):
        self.s.net.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TOKEN_TO_TYPE,
                      lambda d, b: "0x5ffef61af1560b9aefc0e42aaa0f9464854ab113ab7b8bfab271be94cdb1d053")
        with self.assertRaises(Reverted) as e:
            self.s.auth("polygon", USDC, F.POL_USDC)
        self.assertIn("TOKEN_TYPE_IS_NOT_ERC20_ESCROW", e.exception.msg)


class M2ArbitrumNonEscrowGateway(Base):
    def test_unknown_gateway_refused(self):
        self.s.net.arbitrum(WBTC, F.ARB_WBTC, gw=F.addr(0xbad))
        with self.assertRaises(Reverted) as e:
            self.s.auth("arbitrum", WBTC, F.ARB_WBTC)
        self.assertIn("IS_NOT_AN_ESCROW_GATEWAY", e.exception.msg)

    def test_known_gateways(self):
        self.assertEqual(len(CR.ARB_ESCROW_GATEWAYS), 4)
        self.assertIn(F.ARB_GW, CR.ARB_ESCROW_GATEWAYS)


class M3InFlightDepositFlash(Base):
    """A deposit locked on L1 but not yet minted counts as locked and not as
    supply - by design it only ever looks over-backed. An attacker can use it
    to get ONE BACKED ruling for a pair the patrol just found UNDER_BACKED."""

    def final_monitor(self, pid):
        self.s.w.advance(MON)
        self.s.net.mine_to(self.s.w.now() - 60)
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        if self.s.check(cid)["status"] == "PROVISIONAL":
            self.s.finalize_after_window(cid)
        return cid

    def test_flash_backed_after_under_is_refused_by_the_gate(self):
        pid = self.s.pair("arb_usdc")
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 900_000 * 10 ** 6)
        self.final_monitor(pid)
        # attacker deposits 200k (locked now, minted later), files a check at that instant
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 1_100_000 * 10 ** 6)
        c2 = self.final_monitor(pid)
        self.assertEqual(self.s.check(c2)["verdict"], "BACKED")
        g = self.s.view(self.s.gate, "is_backed", pid, self.s.w.now())
        self.assertFalse(g["backed"])
        self.assertTrue(g["reason"].startswith("A_RULING_"), g)

    def test_recovers_once_the_bad_ruling_ages_out(self):
        pid = self.s.pair("arb_usdc")
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 900_000 * 10 ** 6)
        self.final_monitor(pid)
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 1_000_000 * 10 ** 6)
        self.s.w.advance(3600)
        self.final_monitor(pid)
        self.assertTrue(self.s.view(self.s.gate, "is_backed", pid, self.s.w.now())["backed"])

    def test_data_inconclusive_counts_as_not_backed(self):
        pid = self.s.pair("arb_usdc")
        stub.WEB.tamper[CR.CHAINS["arbitrum"][1][1]] = lambda req, ans: dict(ans, result=F.w(1)) \
            if req["method"] == "eth_call" else ans
        self.final_monitor(pid)
        stub.WEB.tamper.clear()
        self.final_monitor(pid)
        self.assertTrue(self.s.view(self.s.gate, "is_backed", pid, self.s.w.now())["reason"].startswith("A_RULING_"))

    def test_pin_inconclusive_does_not_count(self):
        pid = self.s.pair("arb_usdc")
        self.s.after_bond()
        bl = self.s.blocks(pid, gap=900)
        cid = self.s.monitor(pid, bl)["check_id"]
        self.provisional(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_pair", pid)["last_bad_time"], 0)

    def test_flash_cannot_save_a_bond(self):
        # the challenger picks the blocks; in-flight deposits only add to locked
        pid, bid = self.bonded("arb_usdc")
        self.make_short("arb_usdc")
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "SLASHED")


class BlockGames(Base):
    def test_block_numbers_swapped_between_chains(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid)
        cid = self.s.challenge(bid, {"ethereum": bl["arbitrum"], "arbitrum": bl["ethereum"]})["check_id"]
        out = self.provisional(cid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE)

    def test_future_block(self):
        pid, bid = self.bonded()
        cid = self.s.challenge(bid, {"ethereum": 10 ** 9, "arbitrum": 10 ** 10})["check_id"]
        self.assertTrue(self.provisional(cid)["reason"].startswith("BLOCK_NOT_FINALIZED"))

    def test_dest_one_second_newer(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid)
        st = self.s.net.ts("ethereum", bl["ethereum"])
        bl["arbitrum"] = self.s.net.first_at("arbitrum", st + 1)
        cid = self.s.challenge(bid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "SOURCE_BLOCK_OLDER_THAN_ARBITRUM_BLOCK")

    def test_in_flight_withdrawal_inside_gap_only_over_backs(self):
        # burn on L2 before the dest block, release on L1 after the source block: over-backed
        pid, bid = self.bonded()
        bl = self.s.blocks(pid, gap=300)
        self.s.net.supply("arbitrum", F.ARB_USDC, 900_000 * 10 ** 6, from_block=bl["arbitrum"] - 10)
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 900_000 * 10 ** 6, from_block=bl["ethereum"] + 1)
        cid = self.s.challenge(bid, bl)["check_id"]
        self.provisional(cid)
        r = self.s.check(cid)["ruling1"]
        self.assertEqual(r["verdict"], "BACKED")
        self.assertGreater(int(r["locked_norm"]), int(r["supply_norm"]))

    def test_in_flight_deposit_inside_gap_only_over_backs(self):
        pid, bid = self.bonded()
        bl = self.s.blocks(pid, gap=300)
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 1_100_000 * 10 ** 6, from_block=bl["ethereum"] - 5)
        self.s.net.supply("arbitrum", F.ARB_USDC, 1_100_000 * 10 ** 6, from_block=bl["arbitrum"] + 1)
        cid = self.s.challenge(bid, bl)["check_id"]
        self.provisional(cid)
        self.assertEqual(self.s.check(cid)["ruling1"]["ratio_bps"], 11000)


class Decimals(Base):
    def test_rpcs_disagree_on_decimals(self):
        pid, bid = self.bonded()

        def lie(req, ans):
            if req["method"] == "eth_call" and req["params"][0]["data"] == CR.S_DECIMALS:
                return dict(ans, result=F.w(18))
            return ans
        stub.WEB.tamper[CR.CHAINS["arbitrum"][1][0]] = lie
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "RPC_DISAGREE")

    def test_source_decimals_upgraded(self):
        pid, bid = self.bonded()
        self.s.net.decimals("ethereum", USDC, 18)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertTrue(self.provisional(cid)["reason"].startswith("DECIMALS_MISMATCH:source"))

    def test_decimals_cannot_be_used_to_inflate(self):
        # a destination reporting 0 decimals with a tiny supply is refused at the read, not normalized
        pid, bid = self.bonded()
        self.s.net.decimals("arbitrum", F.ARB_USDC, 0)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["status"], "INCONCLUSIVE")


class ProxyAndRebasing(Base):
    def test_upgraded_destination_mints_is_under(self):
        pid, bid = self.bonded()
        self.s.net.supply("arbitrum", F.ARB_USDC, 5_000_000 * 10 ** 6)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "UNDER_BACKED")

    def test_negative_rebase_of_vault_balance_is_under(self):
        pid, bid = self.bonded()
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 999_999 * 10 ** 6)
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "UNDER_BACKED")


class Payouts(Base):
    def test_claim_zeroes_first_and_pays_once(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        owed = self.s.claimable(CHALLENGER)
        n = len(self.s.w.transfers)
        self.s.call(self.s.reg, "claim", sender=CHALLENGER)
        self.assertEqual(self.s.w.transfers[n:], [(self.s.reg, CHALLENGER, owed)])
        with self.assertRaises(Reverted):
            self.s.call(self.s.reg, "claim", sender=CHALLENGER)
        self.assertLedger()

    def test_every_payable_refunds_garbage(self):
        for fn, args in (("bond", ["x"]), ("top_up", [-1]), ("challenge", [0, "{}"]), ("contest", [10 ** 20])):
            r = self.s.call(self.s.reg, fn, *args, sender=STRANGER, value=123)
            self.assertFalse(r["ok"], fn)
        self.assertEqual(self.s.claimable(STRANGER), 4 * 123)
        self.assertLedger()

    def test_treasury_is_fixed(self):
        self.assertEqual(self.s.cfg()["treasury"], DEPLOYER)


class ContestAbuse(Base):
    def test_contest_only_delays_and_is_bounded(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=OPERATOR, value=MIN_STAKE)
        self.s.w.advance(CONTEST_TO)
        out = self.s.call(self.s.reg, "expire", cid, sender=PATROL)
        self.assertEqual(out["verdict"], "UNDER_BACKED")
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "SLASHED")

    def test_losing_contest_pays_the_winner(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=OPERATOR, value=MIN_STAKE)
        self.s.read(cid, 2)
        self.s.rule(cid)
        self.assertEqual(self.s.claimable(CHALLENGER), MIN_STAKE + GEN // 2 + MIN_STAKE)
        self.assertEqual(self.s.claimable(OPERATOR), 0)

    def test_contest_cannot_change_the_blocks(self):
        pid, bid, cid = self.challenged(short=True)
        self.provisional(cid)
        self.s.call(self.s.reg, "contest", cid, sender=OPERATOR, value=MIN_STAKE)
        r = self.s.view(self.s.reg, "get_check_request", cid)
        self.assertEqual(r["blocks"], self.s.check(cid)["blocks"])
        self.assertEqual(r["round"], 2)


class Collusion(Base):
    def test_friendly_challenge_cannot_erase_history(self):
        pid, bid = self.bonded()
        bad = self.s.blocks(pid)
        self.make_short(from_block=bad["ethereum"])
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 1_000_000 * 10 ** 6, from_block=bad["ethereum"] + 1)
        self.s.call(self.s.reg, "request_unbond", bid)
        # a friend files a challenge on good blocks to hold the lane
        good = dict(bad, ethereum=bad["ethereum"] + 1)
        good["arbitrum"] = self.s.net.block_at("arbitrum", self.s.net.ts("ethereum", good["ethereum"]))
        f = self.s.challenge(bid, good, sender=STRANGER)["check_id"]
        self.provisional(f)
        self.s.finalize_after_window(f)
        # the operator still cannot leave before the real challenger proves the old blocks
        real = self.s.challenge(bid, bad)["check_id"]
        self.provisional(real)
        self.s.finalize_after_window(real)
        self.assertEqual(self.s.view(self.s.reg, "get_bond", bid)["status"], "SLASHED")

    def test_withdraw_impossible_while_any_check_open(self):
        pid, bid, cid = self.challenged()
        self.s.call(self.s.reg, "request_unbond", bid)
        self.s.w.advance(UNBOND * 10)
        self.refuses("withdraw_bond", bid, why="IS_OPEN_ON_THIS_BOND")


if __name__ == "__main__":
    unittest.main()
