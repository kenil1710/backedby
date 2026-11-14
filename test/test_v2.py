"""v2 rules, offline, against the deployed build files: Wormhole and CCIP
authentication, Wormhole's ledger, coverage scans (LayerZero peers through
Multicall3, CCIP supported chains), Chainlink PoR next to the ratio, the alert
state, per-pair history, and bounded recovery (transient reads are PENDING
inside a fixed window; validators never take a leader's PENDING or range)."""
import json
import unittest

import fixtures as F
import stub
from fixtures import CR, RG, GEN, OPERATOR, PATROL, STRANGER
from world import Reverted

E6 = 10 ** 6


class Base(unittest.TestCase):
    def setUp(self):
        stub.FORGE["payload"] = None
        stub.FORGE["mutate"] = None
        self.s = F.Setup("DEMO")
        n = self.s.net
        n.scan_rpcs()
        # Wormhole USDC to Arbitrum and Polygon
        n.token("arbitrum", F.WH_ARB_USDC, 6, 1_000 * E6)
        n.token("polygon", F.WH_POL_USDC, 6, 2_000 * E6)
        n.wormhole("arbitrum", F.USDC, F.WH_ARB_USDC)
        n.wormhole("polygon", F.USDC, F.WH_POL_USDC)
        n.balance("ethereum", F.USDC, CR.WH_ETH_BRIDGE, 10_000 * E6)
        n.wh_ledger(F.USDC, 10_000 * E6)
        # Wormhole WETH (18 decimals: the ledger is kept in 8)
        n.token("ethereum", F.WETH, 18)
        n.token("arbitrum", F.WH_ARB_WETH, 18, 5 * GEN)
        n.wormhole("arbitrum", F.WETH, F.WH_ARB_WETH)
        n.balance("ethereum", F.WETH, CR.WH_ETH_BRIDGE, 100 * GEN)
        n.wh_ledger(F.WETH, 100 * 10 ** 8)
        # CCIP GHO to Arbitrum and Base
        n.token("ethereum", F.GHO, 18)
        n.token("arbitrum", F.ARB_GHO, 18, 300 * GEN)
        n.token("base", F.BASE_GHO, 18, 200 * GEN)
        n.ccip("arbitrum", F.GHO, F.ARB_GHO, F.GHO_POOL, F.ARB_GHO_POOL)
        n.ccip("base", F.GHO, F.BASE_GHO, F.GHO_POOL, F.BASE_GHO_POOL)
        n.balance("ethereum", F.GHO, F.GHO_POOL, 600 * GEN)
        n.mine_to(self.s.w.now() - 900)

    def tearDown(self):
        stub.FORGE["payload"] = None
        stub.FORGE["mutate"] = None
        for k in list(CR.POR_FEEDS):
            if k in (F.USDC.lower(), F.WBTC.lower(), F.GHO.lower()):
                del CR.POR_FEEDS[k]

    def auth(self, kind, l1, l2):
        return self.s.auth(kind, l1, l2)

    def register(self, *auths, tol=0):
        r = self.s.call(self.s.reg, "register_pair", ",".join(str(a["auth_id"]) for a in auths), tol, "v2")
        return r["pair_id"]

    def wh_pair(self):
        return self.register(self.auth("wh_arbitrum", F.USDC, F.WH_ARB_USDC), self.auth("wh_polygon", F.USDC, F.WH_POL_USDC))

    def gho_pair(self, both=True):
        a = [self.auth("ccip_arbitrum", F.GHO, F.ARB_GHO)]
        if both:
            a.append(self.auth("ccip_base", F.GHO, F.BASE_GHO))
        return self.register(*a)

    def ruled(self, pid):
        self.s.after_bond(1200)
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.s.read(cid)
        self.s.rule(cid)
        return self.s.check(cid)

    def final(self, pid):
        c = self.ruled(pid)
        if c["status"] == "PROVISIONAL":
            self.s.finalize_after_window(c["check_id"])
        return self.s.check(c["check_id"])


class Wormhole(Base):
    def test_auth_records_vault_family_and_remote(self):
        a = self.auth("wh_arbitrum", F.USDC, F.WH_ARB_USDC)
        self.assertEqual((a["vault"], a["family"], a["remote"]), (CR.WH_ETH_BRIDGE, "LEDGER", "wh:23"))

    def test_wrapped_asset_maps_elsewhere_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, wrapped_map=F.OP_USDC2)
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("WRAPPED_ASSET_OF_SOURCE_IS_", e.exception.msg)

    def test_not_a_wrapped_asset_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, is_wrapped=False)
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("NOT_A_WRAPPED_ASSET", e.exception.msg)

    def test_wrong_origin_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, origin=(2, F.DAI))
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("WRAPPED_ORIGIN_IS_NOT_THE_SOURCE_TOKEN", e.exception.msg)

    def test_origin_on_another_chain_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, origin=(1, F.USDC))
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("WRAPPED_ORIGIN_IS_NOT_THE_SOURCE_TOKEN", e.exception.msg)

    def test_unregistered_chain_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, eth_registers=False)
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("ETH_TOKEN_BRIDGE_DOES_NOT_REGISTER_OPTIMISM", e.exception.msg)

    def test_dest_bridge_not_registering_ethereum_refused(self):
        self.s.net.wormhole("optimism", F.USDC, F.OP_USDC, dest_registers=False)
        with self.assertRaises(Reverted) as e:
            self.auth("wh_optimism", F.USDC, F.OP_USDC)
        self.assertIn("DEST_BRIDGE_DOES_NOT_REGISTER_ETHEREUM", e.exception.msg)

    def test_ledger_counts_destinations_the_pair_does_not_list(self):
        pid = self.wh_pair()
        c = self.ruled(pid)
        r = c["ruling1"]
        self.assertEqual(r["verdict"], "BACKED")
        self.assertEqual(r["ratio_bps"], 10000)          # vault 10,000 against the ledger 10,000, not 3,000 listed
        led = r["ledgers"][CR.WH_ETH_BRIDGE]
        self.assertEqual((led["ledger_norm"], led["listed_norm"]), (str(10_000 * E6), str(3_000 * E6)))

    def test_vault_below_ledger_is_under_backed_although_above_listed(self):
        pid = self.wh_pair()
        self.s.net.balance("ethereum", F.USDC, CR.WH_ETH_BRIDGE, 9_999 * E6)
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["ratio_bps"]), ("UNDER_BACKED", 9999))

    def test_listed_above_ledger_counts_listed(self):
        pid = self.wh_pair()
        self.s.net.wh_ledger(F.USDC, 2_000 * E6)
        self.s.net.balance("ethereum", F.USDC, CR.WH_ETH_BRIDGE, 2_500 * E6)
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["supply_norm"]), ("UNDER_BACKED", str(3_000 * E6)))

    def test_ledger_kept_in_8_decimals_is_scaled(self):
        pid = self.register(self.auth("wh_arbitrum", F.WETH, F.WH_ARB_WETH))
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["ratio_bps"]), ("BACKED", 10000))
        self.assertEqual(r["ledgers"][CR.WH_ETH_BRIDGE]["ledger_norm"], str(100 * GEN))

    def test_ledger_unreadable_is_data_inconclusive(self):
        pid = self.wh_pair()
        self.s.net.fn("ethereum", CR.WH_ETH_BRIDGE, CR.S_WH_OUTSTANDING, lambda d, b: "0x")
        c = self.ruled(pid)
        self.assertEqual((c["status"], c["reason"]), ("INCONCLUSIVE", "CALL_FAILED:ledger"))

    def test_ledger_coverage_is_complete(self):
        pid = self.wh_pair()
        self.assertEqual(self.ruled(pid)["ruling1"]["coverage"]["state"], "COMPLETE")

    def test_request_names_the_ledger_vault(self):
        pid = self.wh_pair()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        req = self.s.view(self.s.reg, "get_check_request", cid)
        self.assertEqual(req["ledgers"], [CR.WH_ETH_BRIDGE])
        self.assertEqual(req["scans"], [])

    def test_mapping_change_after_auth_is_caught(self):
        pid = self.wh_pair()
        self.s.net._wh_wrapped[("arbitrum", F.USDC.lower())] = F.OP_USDC2
        c = self.ruled(pid)
        self.assertTrue(c["reason"].startswith("MAPPING_CHANGED:arbitrum"), c["reason"])


class Ccip(Base):
    def test_auth_records_vault_family_and_remote(self):
        a = self.auth("ccip_arbitrum", F.GHO, F.ARB_GHO)
        self.assertEqual((a["vault"], a["family"], a["remote"]), (F.GHO_POOL, "CCIP", "ccip:4949039107694359620"))

    def refused(self, why, **k):
        self.s.net.ccip("optimism", F.GHO, F.OP_USDC, F.GHO_POOL, F.addr(0x6e9), **k)
        with self.assertRaises(Reverted) as e:
            self.auth("ccip_optimism", F.GHO, F.OP_USDC)
        self.assertIn(why, e.exception.msg)

    def test_burn_mint_source_pool_refused(self):
        self.refused("SOURCE_POOL_IS_NOT_LOCK_RELEASE", src_type="BurnMintTokenPool 1.5.1")

    def test_siloed_source_pool_refused(self):
        self.refused("SOURCE_POOL_IS_NOT_LOCK_RELEASE", src_type="SiloedLockReleaseTokenPool 1.6.0")

    def test_lock_release_dest_pool_refused(self):
        self.refused("DEST_POOL_IS_NOT_BURN_MINT", dst_type="LockReleaseTokenPool 1.5.1")

    def test_remote_token_mismatch_refused(self):
        self.refused("SOURCE_POOL_REMOTE_TOKEN_IS_NOT_THE_DEST_TOKEN", remote_token=F.OP_USDC2)

    def test_dest_remote_token_mismatch_refused(self):
        self.refused("DEST_POOL_REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN", back_token=F.DAI)

    def test_dest_pool_not_naming_source_refused(self):
        self.refused("DEST_POOL_DOES_NOT_NAME_THE_SOURCE_POOL", dest_names_src=False)

    def test_source_pool_not_naming_dest_refused(self):
        self.refused("SOURCE_POOL_DOES_NOT_NAME_THE_DEST_POOL", src_names_dest=False)

    def test_no_pool_refused(self):
        with self.assertRaises(Reverted) as e:
            self.auth("ccip_arbitrum", F.LINK, F.ARB_GHO)
        self.assertIn("NO_CCIP_POOL_FOR_SOURCE_TOKEN", e.exception.msg)

    def test_complete_when_every_supported_chain_is_listed(self):
        pid = self.gho_pair()
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["ratio_bps"], r["coverage"]["state"]), ("BACKED", 12000, "COMPLETE"))

    def test_gap_names_the_unlisted_chain(self):
        pid = self.gho_pair(both=False)
        r = self.ruled(pid)["ruling1"]
        self.assertEqual(r["coverage"]["state"], "GAP")
        self.assertEqual(r["coverage"]["unlisted"], [{"vault": F.GHO_POOL, "id": "ccip:15971525489660198786"}])
        self.assertEqual(r["verdict"], "BACKED")      # coverage never changes the arithmetic

    def test_gap_closed_by_adding_the_destination(self):
        pid = self.gho_pair(both=False)
        self.assertEqual(self.final(pid)["ruling1"]["coverage"]["state"], "GAP")
        a = self.auth("ccip_base", F.GHO, F.BASE_GHO)
        self.s.call(self.s.reg, "add_destination", pid, a["auth_id"], sender=STRANGER)
        v = self.s.view(self.s.reg, "get_pair", pid)["vaults"][0]
        self.assertEqual(sorted(v["remotes"]), ["ccip:15971525489660198786", "ccip:4949039107694359620"])
        self.assertEqual(self.ruled(pid)["ruling1"]["coverage"]["state"], "COMPLETE")

    def test_unknown_selector_is_a_gap(self):
        pid = self.gho_pair()
        self.s.net.ccip_support(F.GHO_POOL, [4949039107694359620, 15971525489660198786, 6433500567565415381])
        r = self.ruled(pid)["ruling1"]
        self.assertEqual(r["coverage"]["unlisted"], [{"vault": F.GHO_POOL, "id": "ccip:6433500567565415381"}])

    def test_scan_unreadable_is_unread_never_complete(self):
        pid = self.gho_pair()
        self.s.net.fn("ethereum", F.GHO_POOL, CR.S_CCIP_CHAINS, lambda d, b: "0x")
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["coverage"]["state"]), ("BACKED", "UNREAD"))

    def test_scan_too_long_is_unread(self):
        pid = self.gho_pair()
        self.s.net.ccip_support(F.GHO_POOL, list(range(1, CR.MAX_SCAN_IDS + 2)))
        self.assertEqual(self.ruled(pid)["ruling1"]["coverage"]["state"], "UNREAD")


class LayerZeroScan(Base):
    def usdt0(self):
        a = self.auth("oft_polygon", F.USDT, F.POL_USDT)
        b = self.auth("oft_arbitrum", F.USDT, F.ARB_USDT0)
        return self.register(a, b)

    def test_complete_when_every_peer_is_listed(self):
        r = self.ruled(self.usdt0())["ruling1"]
        self.assertEqual(r["coverage"]["state"], "COMPLETE")

    def test_peer_on_an_unlisted_eid_is_a_gap(self):
        pid = self.usdt0()
        self.s.net._oft_peers[F.USDT0_ADAPTER.lower()][30500] = F.addr(0x5050)
        r = self.ruled(pid)["ruling1"]
        self.assertEqual(r["coverage"]["unlisted"], [{"vault": F.USDT0_ADAPTER, "id": "lz:30500"}])

    def test_peer_at_the_edges_of_the_scan(self):
        pid = self.usdt0()
        peers = self.s.net._oft_peers[F.USDT0_ADAPTER.lower()]
        peers[CR.LZ_SCAN[0]] = F.addr(1)
        peers[CR.LZ_SCAN[1] - 1] = F.addr(2)
        ids = [u["id"] for u in self.ruled(pid)["ruling1"]["coverage"]["unlisted"]]
        self.assertEqual(ids, ["lz:%d" % CR.LZ_SCAN[0], "lz:%d" % (CR.LZ_SCAN[1] - 1)])

    def test_scan_rpcs_disagree_is_unread(self):
        pid = self.usdt0()
        stub.WEB.tamper[CR.SCAN_RPCS[1]] = lambda req, ans: dict(ans, result="0x" + "00" * 64) \
            if req["method"] == "eth_call" and req["params"][0]["to"] == CR.MULTICALL3 else ans
        r = self.ruled(pid)["ruling1"]
        # the fixture's USDT0 adapter holds 1,495,000 against 1,500,000 minted: the verdict is the arithmetic's
        self.assertEqual((r["verdict"], r["coverage"]["state"]), ("UNDER_BACKED", "UNREAD"))

    def test_scan_rpc_down_is_unread(self):
        pid = self.usdt0()
        stub.WEB.down.add(CR.SCAN_RPCS[1])
        self.assertEqual(self.ruled(pid)["ruling1"]["coverage"]["state"], "UNREAD")

    def test_mapping_vault_plus_adapter(self):
        a = self.auth("polygon", F.USDT, F.POL_USDT)
        pid = self.register(a)
        v = self.auth("oft_polygon", F.USDT, F.POL_USDT)
        self.s.call(self.s.reg, "add_vault", pid, v["auth_id"])
        r = self.ruled(pid)["ruling1"]["coverage"]
        self.assertEqual([x["family"] for x in r["by_vault"]], ["MAPPING", "LZ"])
        self.assertEqual(r["unlisted"], [{"vault": F.USDT0_ADAPTER, "id": "lz:30110"}])

    def test_multicall_encoding_round_trip(self):
        data = CR.mc_encode([[F.USDT0_ADAPTER, CR.S_PEERS + CR._u(e)] for e in (30109, 30110, 30111)])
        self.s.net.mine_to(self.s.w.now())
        blk = self.s.net.mc["ethereum"].finalized
        out = CR.mc_decode(F._mc_answer(self.s.net, data, blk), 3)
        self.assertEqual([x > 0 for x in out], [True, True, False])

    def test_decode_rejects_a_count_mismatch(self):
        data = CR.mc_encode([[F.USDT0_ADAPTER, CR.S_PEERS + CR._u(30109)]])
        self.assertIsNone(CR.mc_decode(F._mc_answer(self.s.net, data, self.s.net.mc["ethereum"].finalized), 2))

    def test_a_reverting_peer_entry_is_unread(self):
        pid = self.usdt0()
        self.s.net.fn("ethereum", F.USDT0_ADAPTER, CR.S_PEERS,
                      lambda d, b: F.REVERT if F.arg(d, 0) == 30777 else F.wa(self.s.net._oft_peers[F.USDT0_ADAPTER.lower()].get(F.arg(d, 0), "0x" + "0" * 40)))
        self.assertEqual(self.ruled(pid)["ruling1"]["coverage"]["state"], "UNREAD")

    def test_endpoint_supporting_an_eid_above_the_range_makes_the_scan_unread(self):
        pid = self.usdt0()
        self.s.net.lz_supported.add(CR.LZ_GUARD[0] + 7)
        r = self.ruled(pid)["ruling1"]
        self.assertEqual(r["coverage"]["state"], "UNREAD")
        self.assertEqual(r["coverage"]["by_vault"][0]["state"], "UNREAD")

    def test_scan_covers_the_whole_range(self):
        self.assertEqual(CR.LZ_SCAN, (30101, 31101))
        self.assertEqual(CR.LZ_GUARD[0], CR.LZ_SCAN[1])

    def test_decode_rejects_junk(self):
        for junk in ("", "0x", "0x12", None, "0x" + "f" * 64):
            self.assertIsNone(CR.mc_decode(junk, 1))


class ValidatorTolerance(Base):
    """A validator takes a leader's UNREAD scan or PoR (it can only make the
    answer less favorable) but never a leader's scan or PoR data it did not read itself."""

    def filed(self):
        a = self.auth("oft_polygon", F.USDT, F.POL_USDT)
        b = self.auth("oft_arbitrum", F.USDT, F.ARB_USDT0)
        pid = self.register(a, b)
        self.s.after_bond()
        return self.s.monitor(pid, self.s.blocks(pid))["check_id"]

    def test_leader_scan_error_is_accepted(self):
        cid = self.filed()

        def unread(r):
            r["coverage"][0] = dict(r["coverage"][0], ids=[], error="SCAN_UNREADABLE")
            return r
        stub.FORGE["mutate"] = unread
        self.assertEqual(self.s.read(cid)["status"], "OK")
        stub.FORGE["mutate"] = None
        self.s.rule(cid)
        self.assertEqual(self.s.check(cid)["ruling1"]["coverage"]["state"], "UNREAD")

    def test_leader_scan_data_must_match(self):
        cid = self.filed()

        def hide(r):
            r["coverage"][0]["ids"] = r["coverage"][0]["ids"][:1]
            return r
        stub.FORGE["mutate"] = hide
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_leader_cannot_turn_an_error_into_data(self):
        cid = self.filed()
        stub.WEB.validator_hook = lambda: stub.WEB.down.add(CR.SCAN_RPCS[1])
        with self.assertRaises(Reverted):
            self.s.read(cid)
        stub.WEB.validator_hook = None
        stub.WEB.down.clear()

    def test_leader_cannot_drop_a_scan(self):
        cid = self.filed()

        def drop(r):
            r["coverage"] = []
            return r
        stub.FORGE["mutate"] = drop
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_verdict_fields_must_be_identical(self):
        cid = self.filed()

        def more(r):
            r["locked_by_vault"][0] = str(int(r["locked_by_vault"][0]) + 1)
            return r
        stub.FORGE["mutate"] = more
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_agrees_pure(self):
        x = {"status": "OK", "coverage": [{"vault": "a", "family": "LZ", "ids": [1], "error": ""}], "por": {"answer": "1"}}
        self.assertTrue(CR.reading_agrees(x, x))
        self.assertTrue(CR.reading_agrees(x, dict(x, por={"error": "POR_UNREADABLE"})))
        self.assertFalse(CR.reading_agrees(x, dict(x, por={"answer": "2"})))
        self.assertFalse(CR.reading_agrees(x, dict(x, por=None)))
        self.assertFalse(CR.reading_agrees(dict(x, por=None), dict(x, por={"error": "x"})))
        self.assertFalse(CR.reading_agrees(x, dict(x, coverage=[{"vault": "a", "family": "LZ", "ids": [1, 2], "error": "SCAN_UNREADABLE"}])))
        self.assertFalse(CR.reading_agrees(x, dict(x, coverage=[{"vault": "b", "family": "LZ", "ids": [], "error": "E"}])))
        self.assertFalse(CR.reading_agrees(x, "junk"))


class Por(Base):
    def wbtc_pair(self):
        return self.s.pair("arb_wbtc")

    def test_no_feed_no_por(self):
        self.assertIsNone(self.ruled(self.s.pair("arb_usdc"))["ruling1"]["por"])

    def test_match(self):
        pid = self.wbtc_pair()
        self.s.net.supply("ethereum", F.WBTC, 1000 * 10 ** 8)
        self.s.net.por(F.WBTC, 1000 * 10 ** 8, self.s.w.now())
        p = self.ruled(pid)["ruling1"]["por"]
        self.assertEqual((p["status"], p["por_ratio_bps"], p["delta_bps"]), ("MATCH", 10000, 0))

    def test_diff_is_explained(self):
        pid = self.wbtc_pair()
        self.s.net.balance("ethereum", F.WBTC, F.ARB_GW, 120 * 10 ** 8)
        self.s.net.supply("ethereum", F.WBTC, 1000 * 10 ** 8)
        self.s.net.por(F.WBTC, 1000 * 10 ** 8, self.s.w.now())
        p = self.ruled(pid)["ruling1"]["por"]
        self.assertEqual((p["status"], p["delta_bps"]), ("DIFF", 2000))
        self.assertEqual(p["explain"], "BRIDGE_VAULT_SURPLUS_EXCEEDS_CUSTODY_SURPLUS")

    def test_custody_below_supply_is_named(self):
        pid = self.wbtc_pair()
        self.s.net.supply("ethereum", F.WBTC, 1000 * 10 ** 8)
        self.s.net.por(F.WBTC, 900 * 10 ** 8, self.s.w.now())
        p = self.ruled(pid)["ruling1"]["por"]
        self.assertEqual(p["status"], "DIFF")
        self.assertTrue(p["explain"].endswith(";CUSTODY_RESERVES_BELOW_SUPPLY"), p["explain"])

    def test_stale_answer(self):
        pid = self.wbtc_pair()
        self.s.net.supply("ethereum", F.WBTC, 1000 * 10 ** 8)
        self.s.net.por(F.WBTC, 1000 * 10 ** 8, self.s.w.now() - RG.POR_MAX_AGE_S - 5000)
        self.assertEqual(self.ruled(pid)["ruling1"]["por"]["status"], "STALE")

    def test_feed_unreadable_never_touches_the_verdict(self):
        pid = self.wbtc_pair()
        self.s.net.por(F.WBTC, 1, 1)
        self.s.net.fn("ethereum", F.POR_FEED, CR.S_LATEST_ROUND, lambda d, b: "0x")
        r = self.ruled(pid)["ruling1"]
        self.assertEqual((r["verdict"], r["por"]["status"]), ("BACKED", "UNREAD"))

    def test_compare_pure(self):
        por = {"answer": "100", "decimals": 0, "supply": "100", "supply_decimals": 0, "updated_at": 10}
        self.assertEqual(RG.por_compare(por, 10050, 20)["status"], "MATCH")
        self.assertEqual(RG.por_compare(por, 10051, 20)["status"], "DIFF")
        self.assertEqual(RG.por_compare(por, 9950, 20)["status"], "MATCH")
        self.assertEqual(RG.por_compare(por, 9949, 20)["status"], "DIFF")
        self.assertEqual(RG.por_compare(por, 10000, 10 + RG.POR_MAX_AGE_S)["status"], "MATCH")
        self.assertEqual(RG.por_compare(por, 10000, 11 + RG.POR_MAX_AGE_S)["status"], "STALE")
        self.assertIsNone(RG.por_compare(None, 10000, 20))
        self.assertEqual(RG.por_compare({"error": "POR_UNREADABLE"}, 10000, 20)["status"], "UNREAD")
        self.assertEqual(RG.por_compare(dict(por, supply="0"), 10000, 20)["status"], "UNREAD")


class Alert(unittest.TestCase):
    def test_boundaries(self):
        m = RG.ALERT_MARGIN_BPS
        for tol in (0, 10, 50, 1000):
            line = 10000 - tol
            self.assertEqual(RG.alert_state("BACKED", line + m, tol), "OK")
            self.assertEqual(RG.alert_state("BACKED", line + m - 1, tol), "ALERT")
            self.assertEqual(RG.alert_state("BACKED", line, tol), "ALERT")
        self.assertEqual(RG.alert_state("UNDER_BACKED", 5000, 0), "BREACH")
        self.assertEqual(RG.alert_state("INCONCLUSIVE", -1, 0), "")


class History(Base):
    def test_final_rulings_become_points(self):
        pid = self.s.pair("arb_usdc")
        for _ in range(3):
            self.s.w.advance(3600)
            self.final(pid)
        h = self.s.view(self.s.reg, "get_history", pid, 0, 50)
        self.assertEqual((h["total"], len(h["points"]), h["next_offset"]), (3, 3, -1))
        p = h["points"][0]
        for k in ("check_id", "source_time", "verdict", "ratio_bps", "alert", "coverage", "por", "blocks"):
            self.assertIn(k, p)
        self.assertEqual(p["coverage"], "COMPLETE")

    def test_inconclusive_is_not_a_point(self):
        pid = self.s.pair("arb_usdc")
        F.data_fault("arbitrum")
        c = self.ruled(pid)
        F.data_fault("arbitrum", False)
        self.assertEqual(c["status"], "INCONCLUSIVE")
        self.assertEqual(self.s.view(self.s.reg, "get_history", pid, 0, 50)["total"], 0)

    def test_pagination(self):
        pid = self.s.pair("arb_usdc")
        for _ in range(5):
            self.s.w.advance(3600)
            self.final(pid)
        a = self.s.view(self.s.reg, "get_history", pid, 0, 2)
        b = self.s.view(self.s.reg, "get_history", pid, a["next_offset"], 2)
        c = self.s.view(self.s.reg, "get_history", pid, b["next_offset"], 2)
        ids = [p["check_id"] for p in a["points"] + b["points"] + c["points"]]
        self.assertEqual((len(ids), len(set(ids)), c["next_offset"]), (5, 5, -1))

    def test_page_is_bounded(self):
        pid = self.s.pair("arb_usdc")
        self.final(pid)
        self.assertEqual(len(self.s.view(self.s.reg, "get_history", pid, 0, 10 ** 9)["points"]), 1)
        self.assertEqual(self.s.view(self.s.reg, "get_history", 99, 0, 5)["found"], False)

    def test_alert_point(self):
        pid = self.s.pair("arb_usdc")
        self.s.net.balance("ethereum", F.USDC, F.ARB_GW, 1_000_500 * E6)    # 100.05%: within 10 bps? no, 5 bps above the line
        self.assertEqual(self.final(pid)["ruling1"]["alert"], "ALERT")
        self.assertEqual(self.s.view(self.s.reg, "get_history", pid, 0, 5)["points"][0]["alert"], "ALERT")
        self.assertEqual(self.s.view(self.s.reg, "get_latest", pid)["alert"], "ALERT")


class BoundedRecovery(Base):
    def filed(self, name="arb_usdc"):
        pid = self.s.pair(name)
        self.s.after_bond()
        return pid, self.s.monitor(pid, self.s.blocks(pid))["check_id"]

    def test_transient_is_pending_and_the_check_stays_open(self):
        pid, cid = self.filed()
        stub.WEB.down.add(CR.CHAINS["arbitrum"][1][1])
        for i in range(3):
            self.assertEqual(self.s.read(cid, sender=F.addr(900 + i))["status"], "PENDING")
        g = self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)
        self.assertEqual((g["found"], g["pending"]), (False, 3))
        self.assertEqual(self.s.check(cid)["status"], "OPEN")
        stub.WEB.down.clear()
        self.assertEqual(self.s.read(cid, sender=STRANGER)["status"], "OK")
        self.assertEqual(self.s.rule(cid)["status"], "PROVISIONAL")

    def test_retries_never_move_the_deadline(self):
        pid, cid = self.filed()
        d0 = self.s.check(cid)["read_deadline"]
        stub.WEB.down.add("*")
        for _ in range(4):
            self.s.w.advance(30)
            self.s.read(cid)
        self.assertEqual(self.s.check(cid)["read_deadline"], d0)
        self.assertEqual(self.s.view(self.s.reg, "get_check_request", cid)["read_by"], d0)

    def test_reads_after_the_window_are_refused_and_expire_refunds(self):
        pid, bid = self.s.pair("arb_usdc"), None
        bid = self.s.bond(pid)["bond_id"]
        self.s.after_bond()
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        stub.WEB.down.add("*")
        self.s.read(cid)
        stub.WEB.down.clear()
        self.s.w.set_time(self.s.check(cid)["read_deadline"] + 1)
        with self.assertRaises(Reverted) as e:
            self.s.read(cid)
        self.assertIn("READ_WINDOW_CLOSED_AT_", e.exception.msg)
        out = self.s.call(self.s.reg, "expire", cid, sender=STRANGER)
        self.assertEqual(out["status"], "INCONCLUSIVE")
        self.assertEqual(self.s.check(cid)["how"], "TIMEOUT_UNREAD")
        self.assertEqual(self.s.claimable(F.CHALLENGER), int(self.s.cfg()["min_stake"]))

    def test_read_at_the_deadline_is_accepted(self):
        pid, cid = self.filed()
        self.s.w.set_time(self.s.check(cid)["read_deadline"])
        self.assertEqual(self.s.read(cid)["status"], "OK")

    def test_validator_rejects_a_leader_claiming_pending(self):
        pid, cid = self.filed()
        stub.FORGE["payload"] = {"status": "PENDING"}
        with self.assertRaises(Reverted) as e:
            self.s.read(cid)
        self.assertIn("UNDETERMINED", e.exception.msg)
        stub.FORGE["payload"] = None
        g = self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)
        self.assertEqual((g["found"], g["pending"]), (False, 0))

    def test_validator_rejects_a_forged_reading_when_its_own_read_fails(self):
        pid, cid = self.filed()
        good = {}

        def keep(r):
            good.update(r)
            return r
        stub.FORGE["mutate"] = keep
        stub.WEB.validator_hook = lambda: stub.WEB.down.add("*")
        with self.assertRaises(Reverted):
            self.s.read(cid)
        stub.WEB.validator_hook = None
        stub.WEB.down.clear()
        self.assertEqual(good.get("status"), "OK")

    def test_validator_rejects_a_leader_reading_other_blocks(self):
        pid, cid = self.filed()

        def other(r):
            r["blocks"]["ethereum"]["number"] += 1
            return r
        stub.FORGE["mutate"] = other
        with self.assertRaises(Reverted) as e:
            self.s.read(cid)
        self.assertIn("UNDETERMINED", e.exception.msg)

    def test_contest_round_has_its_own_fixed_window(self):
        pid = self.s.pair("arb_usdc")
        bid = self.s.bond(pid)["bond_id"]
        self.s.after_bond()
        cid = self.s.challenge(bid, self.s.blocks(pid))["check_id"]
        self.s.read(cid)
        self.s.rule(cid)
        self.s.call(self.s.reg, "contest", cid, sender=F.CONTESTER, value=int(self.s.cfg()["min_stake"]))
        c = self.s.check(cid)
        self.assertEqual(self.s.view(self.s.reg, "get_check_request", cid)["read_by"], c["contest_read_deadline"])
        stub.WEB.down.add("*")
        self.assertEqual(self.s.read(cid, 2)["status"], "PENDING")
        self.assertEqual(self.s.check(cid)["contest_read_deadline"], c["contest_read_deadline"])

    def test_junk_reads_of_other_checks_do_not_touch_this_one(self):
        pid, cid = self.filed()
        d0 = self.s.check(cid)["read_deadline"]
        for bad in (0, -1, cid + 7, "x"):
            with self.assertRaises(Reverted):
                self.s.read(bad)
        self.assertEqual(self.s.check(cid)["read_deadline"], d0)

    def test_request_shape_checked_by_the_reader(self):
        req = {"ok": True, "source_chain": "ethereum", "source_token": F.USDC, "vaults": [F.ARB_GW],
               "dests": [{"chain": "arbitrum", "token": F.ARB_USDC}], "blocks": {"ethereum": 1, "arbitrum": 1}}
        self.assertEqual(CR._req_ok(req), "")
        self.assertEqual(CR._req_ok(dict(req, scans=[[F.addr(1), "LZ"]])), "BAD_SCANS")
        self.assertEqual(CR._req_ok(dict(req, scans=[[F.ARB_GW, "EVIL"]])), "BAD_SCANS")
        self.assertEqual(CR._req_ok(dict(req, ledgers=[F.ARB_GW])), "BAD_LEDGERS")
        self.assertEqual(CR._req_ok(dict(req, vaults=[CR.WH_ETH_BRIDGE], ledgers=[CR.WH_ETH_BRIDGE] * 2)), "BAD_LEDGERS")


class Families(Base):
    def test_family_of_every_kind(self):
        for k in CR.KINDS:
            self.assertEqual(CR.family(k), RG.family(k), k)
        self.assertEqual(RG.family("arbitrum"), "MAPPING")
        self.assertEqual(RG.family("optimism"), "OPEN")
        self.assertEqual(RG.family("nomad"), "OPEN")
        self.assertEqual(RG.family("oft_base"), "LZ")

    def test_kinds_agree(self):
        self.assertEqual(CR.KINDS, RG.KINDS)

    def test_remote_ids_agree(self):
        for k, ch in CR.KINDS.items():
            self.assertEqual(CR.remote_id(k), RG.remote_of(k, ch), k)

    def test_open_bridge_is_open_coverage(self):
        pid = self.s.pair("op_usdc")
        r = self.ruled(pid)["ruling1"]
        self.assertEqual(r["coverage"]["state"], "OPEN")

    def test_coverage_pure(self):
        v = [{"vault": "a", "family": "LZ", "remotes": ["lz:1"]}]
        self.assertEqual(RG.coverage_of(v, [{"vault": "a", "ids": [1], "error": ""}])["state"], "COMPLETE")
        self.assertEqual(RG.coverage_of(v, [{"vault": "a", "ids": [1, 2], "error": ""}])["state"], "GAP")
        self.assertEqual(RG.coverage_of(v, [])["state"], "UNREAD")
        self.assertEqual(RG.coverage_of(v, None)["state"], "UNREAD")
        self.assertEqual(RG.coverage_of(v, [{"vault": "a", "ids": [1], "error": "SCAN_UNREADABLE"}])["state"], "UNREAD")
        self.assertEqual(RG.coverage_of(v, [{"vault": "b", "ids": [1], "error": ""}])["state"], "UNREAD")
        both = v + [{"vault": "o", "family": "OPEN", "remotes": []}]
        self.assertEqual(RG.coverage_of(both, [{"vault": "a", "ids": [1, 9], "error": ""}])["state"], "GAP")
        self.assertEqual(RG.coverage_of(both, [{"vault": "a", "ids": [1], "error": ""}])["state"], "OPEN")
        self.assertEqual(RG.coverage_of([], [])["state"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
