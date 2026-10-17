"""Pairs with more than one vault: LayerZero OFT authentication, add_vault
(and every way it is refused), summed locked, the fast-bridge gap, and the
false UNDER_BACKED that a missing vault produces until it is added.

    cd test && python3 -m unittest -q test_vaults
"""
import json
import unittest

import fixtures as F
import stub
import world
from fixtures import CR, RG, Setup, USDC, USDT, GEN, OPERATOR, CHALLENGER, STRANGER, PATROL
from test_registry import Base, MIN_STAKE

Reverted = world.Reverted


class OftAuth(Base):
    def test_polygon_oft_vault_is_the_adapter(self):
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)
        self.assertEqual(a["vault"], F.USDT0_ADAPTER)
        rec = self.s.view(self.s.reader, "get_auth", a["auth_id"])
        self.assertEqual(rec["dest_chain"], "polygon")
        self.assertEqual(len(rec["anchors"]), 5)

    def test_arbitrum_oft(self):
        self.assertEqual(self.s.auth("oft_arbitrum", USDT, F.ARB_USDT0)["vault"], F.USDT0_ADAPTER)

    def test_native_oft(self):
        t = F.addr(0x7a7a)
        self.s.net.token("arbitrum", t, 6, 5)
        self.s.net.oft("arbitrum", USDT, t, F.addr(0x7a7b), None, native=True)
        self.assertEqual(self.s.auth("oft_arbitrum", USDT, t)["vault"], F.addr(0x7a7b))

    def refused(self, kind, l1, l2, why):
        with self.assertRaises(Reverted) as e:
            self.s.auth(kind, l1, l2)
        self.assertIn(why, e.exception.msg)

    def test_no_ethereum_peer(self):
        self.s.net.oft("polygon", USDT, F.POL_USDT, F.USDT0_ADAPTER, F.POL_OFT, peer_back="0x" + "0" * 40)
        self.refused("oft_polygon", USDT, F.POL_USDT, "OFT_HAS_NO_ETHEREUM_PEER")

    def test_wrong_endpoint(self):
        self.s.net.oft("polygon", USDT, F.POL_USDT, F.USDT0_ADAPTER, F.POL_OFT, endpoint=F.addr(9))
        self.refused("oft_polygon", USDT, F.POL_USDT, "OFT_NOT_ON_THE_LAYERZERO_ENDPOINT")

    def test_adapter_token_mismatch(self):
        self.refused("oft_polygon", USDC, F.POL_USDT, "ADAPTER_TOKEN_IS_NOT_THE_SOURCE_TOKEN")

    def test_adapter_peer_mismatch(self):
        self.s.net.oft("polygon", USDT, F.POL_USDT, F.USDT0_ADAPTER, F.POL_OFT, adapter_peer=F.addr(10))
        self.refused("oft_polygon", USDT, F.POL_USDT, "ADAPTER_PEER_IS_NOT_THE_DESTINATION_OFT")

    def test_oft_token_mismatch(self):
        self.s.net.fn("polygon", F.POL_OFT, CR.S_TOKEN, lambda d, b: F.wa(F.addr(11)))
        self.refused("oft_polygon", USDT, F.POL_USDT, "OFT_TOKEN_IS_NOT_THE_DESTINATION_TOKEN")

    def test_plain_token_refused(self):
        self.refused("oft_polygon", USDT, F.POL_USDC, "OFT_HAS_NO_ETHEREUM_PEER")


class AddVault(Base):
    def usdt_pair(self, tol=0):
        """USDT on Polygon registered through the PoS predicate only."""
        a = self.s.auth("polygon", USDT, F.POL_USDT)["auth_id"]
        return self.s.call(self.s.reg, "register_pair", str(a), tol, "USDT on Polygon")["pair_id"]

    def add_vault(self, pid, kind="oft_polygon", dest=None, sender=STRANGER):
        a = self.s.auth(kind, USDT, dest or F.POL_USDT, sender=sender)["auth_id"]
        return self.s.call(self.s.reg, "add_vault", pid, a, sender=sender)

    def monitor_ruled(self, pid):
        self.s.w.advance(60)
        self.s.net.mine_to(self.s.w.now() - 30)
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        return self.provisional(cid), cid

    def test_add_vault_ok(self):
        pid = self.usdt_pair()
        r = self.add_vault(pid)
        self.assertEqual((r["vaults"], r["max_gap_s"]), (2, 120))
        p = self.s.view(self.s.reg, "get_pair", pid)
        self.assertEqual([v["vault"] for v in p["vaults"]], [F.POL_PRED, F.USDT0_ADAPTER])
        self.assertEqual(p["vaults"][1]["added_by"], STRANGER)
        self.assertEqual(p["max_gap_s"], 120)

    def test_false_under_corrected_by_adding_the_vault(self):
        pid = self.usdt_pair()
        self.s.after_bond()
        out, c1 = self.monitor_ruled(pid)
        self.assertEqual(out["verdict"], "UNDER_BACKED")         # 5k locked against 700k
        self.s.finalize_after_window(c1)
        self.add_vault(pid)
        self.s.w.advance(RG.MODES["DEMO"][4])
        out, c2 = self.monitor_ruled(pid)
        self.assertEqual(out["verdict"], "BACKED")
        r = self.s.check(c2)["ruling1"]
        self.assertEqual(r["locked_norm"], str(1_500_000 * 10 ** 6))
        self.assertEqual(self.s.check(c2)["vaults"], [F.POL_PRED, F.USDT0_ADAPTER])

    def test_summed_locked_reads_every_vault(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.s.read(cid)
        rd = self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)["reading"]
        self.assertEqual(rd["locked_by_vault"], [str(5_000 * 10 ** 6), str(1_495_000 * 10 ** 6)])

    def test_add_destination_through_the_new_vault(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        a = self.s.auth("oft_arbitrum", USDT, F.ARB_USDT0)["auth_id"]
        r = self.s.call(self.s.reg, "add_destination", pid, a, sender=STRANGER)
        self.assertEqual(r["destinations"], 2)
        self.s.after_bond()
        out, cid = self.monitor_ruled(pid)
        self.assertEqual(self.s.check(cid)["ruling1"]["supply_norm"], str(1_500_000 * 10 ** 6))
        self.assertEqual(out["verdict"], "BACKED")

    def test_duplicate_vault_refused(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)["auth_id"]
        self.refuses("add_vault", pid, a, why="VAULT_ALREADY_IN_THIS_PAIR", sender=STRANGER)

    def test_same_vault_through_another_destination_refused(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        a = self.s.auth("oft_arbitrum", USDT, F.ARB_USDT0)["auth_id"]
        self.refuses("add_vault", pid, a, why="VAULT_DOES_NOT_BACK_A_DESTINATION_OF_THIS_PAIR", sender=STRANGER)

    def test_primary_vault_again_refused(self):
        pid = self.usdt_pair()
        a = self.s.auth("polygon", USDT, F.POL_USDT)["auth_id"]
        self.refuses("add_vault", pid, a, why="VAULT_ALREADY_IN_THIS_PAIR", sender=STRANGER)

    def test_vault_in_another_pair_refused(self):
        a = self.s.auth("oft_arbitrum", USDT, F.ARB_USDT0)["auth_id"]
        self.s.call(self.s.reg, "register_pair", str(a), 0, "USDT0 on Arbitrum")
        pid = self.usdt_pair()
        b = self.s.auth("oft_polygon", USDT, F.POL_USDT)["auth_id"]
        self.refuses("add_vault", pid, b, why="VAULT_ALREADY_IN_PAIR_1", sender=STRANGER)

    def test_fake_vault_refused(self):
        # an attacker's adapter that claims token()=USDT, with its own OFT and its own Polygon token
        self.s.net.oft("polygon", USDT, F.POL_FAKE_USDT, F.FAKE_ADAPTER, F.FAKE_OFT)
        self.s.net.balance("ethereum", USDT, F.FAKE_ADAPTER, 10 ** 15)
        pid = self.usdt_pair()
        a = self.s.auth("oft_polygon", USDT, F.POL_FAKE_USDT, sender=STRANGER)["auth_id"]
        self.refuses("add_vault", pid, a, why="VAULT_DOES_NOT_BACK_A_DESTINATION_OF_THIS_PAIR", sender=STRANGER)
        self.refuses("add_destination", pid, a, why="AUTH_IS_FOR_ANOTHER_PAIR", sender=STRANGER)

    def test_fake_adapter_cannot_claim_the_real_token(self):
        # the attacker points their adapter's peer at the real Polygon OFT; the OFT's peer is still the real adapter
        self.s.net.fn("ethereum", F.FAKE_ADAPTER, CR.S_TOKEN, lambda d, b: F.wa(USDT))
        self.s.net.fn("ethereum", F.FAKE_ADAPTER, CR.S_PEERS, lambda d, b: F.wa(F.POL_OFT))
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)
        self.assertEqual(a["vault"], F.USDT0_ADAPTER)       # derived from the token, never supplied

    def test_other_source_token_refused(self):
        pid = self.s.pair("pol_usdc")
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)["auth_id"]
        self.refuses("add_vault", pid, a, why="AUTH_IS_FOR_ANOTHER_SOURCE_TOKEN", sender=STRANGER)

    def test_stale_auth_refused(self):
        pid = self.usdt_pair()
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)["auth_id"]
        self.s.w.advance(3601)
        self.refuses("add_vault", pid, a, why="TOO_OLD", sender=STRANGER)

    def test_no_pair(self):
        self.refuses("add_vault", 9, 1, why="NO_SUCH_PAIR", sender=STRANGER)

    def test_vault_limit(self):
        pid = self.usdt_pair()
        p = self.s.w.instances[self.s.reg].pairs[pid]
        p.vaults_json = json.dumps([{"vault": F.addr(900 + i), "kind": "polygon", "auth_id": 1, "added_by": "", "added_at": 0}
                                    for i in range(RG.MAX_VAULTS)])
        a = self.s.auth("oft_polygon", USDT, F.POL_USDT)["auth_id"]
        self.refuses("add_vault", pid, a, why="PAIR_HAS_8_VAULTS", sender=STRANGER)

    def test_open_check_keeps_its_vaults(self):
        pid = self.usdt_pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.add_vault(pid)
        self.assertEqual(self.s.check(cid)["vaults"], [F.POL_PRED])
        self.assertEqual(self.provisional(cid)["verdict"], "UNDER_BACKED")
        self.assertEqual(self.s.check(cid)["max_gap_s"], 300)

    def test_fast_gap_enforced_after_add_vault(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        self.s.after_bond()
        bl = self.s.blocks(pid)
        st = self.s.net.ts("ethereum", bl["ethereum"])
        bl["polygon"] = self.s.net.block_at("polygon", st - 121)
        gap = st - self.s.net.ts("polygon", bl["polygon"])
        self.assertGreater(gap, 120)
        cid = self.s.monitor(pid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["reason"], "GAP_%dS_OVER_120S" % gap)

    def test_fast_gap_120_rules(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        self.s.after_bond()
        bl = self.s.blocks(pid)
        st = self.s.net.ts("ethereum", bl["ethereum"])
        bl["polygon"] = self.s.net.block_at("polygon", st - 120)
        cid = self.s.monitor(pid, bl)["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "BACKED")

    def test_oft_remapped_is_mapping_changed(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        self.s.net.fn("polygon", F.POL_USDT, CR.S_OFT_CONTRACT, lambda d, b: F.wa(F.addr(12)))
        self.s.after_bond()
        out, cid = self.monitor_ruled(pid)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertIn("MAPPING_CHANGED", self.s.check(cid)["reason"])

    def test_challenge_uses_all_vaults(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        bid = self.s.bond(pid, GEN)["bond_id"]
        self.s.after_bond()
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.provisional(cid)
        self.s.finalize_after_window(cid)
        self.assertEqual(self.s.check(cid)["verdict"], "BACKED")
        self.assertLedger()

    def test_counters(self):
        pid = self.usdt_pair()
        self.add_vault(pid)
        self.assertEqual(self.stats()["counts"]["vaults_added"], 1)


if __name__ == "__main__":
    unittest.main()
