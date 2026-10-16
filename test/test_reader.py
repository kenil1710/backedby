"""ChainReader: authentication by each bridge's own mapping, and reads at
pinned blocks from two RPCs (agreement, errors, finality, batch sizes,
forged leaders).

    cd test && python3 -m unittest -q test_reader
"""
import json
import unittest

import fixtures as F
import stub
import world
from fixtures import CR, Setup, USDC, WBTC, DAI, LINK

Reverted = world.Reverted


class Base(unittest.TestCase):
    def setUp(self):
        stub.FORGE["payload"] = None
        stub.FORGE["mutate"] = None
        self.s = Setup()

    def tearDown(self):
        stub.FORGE["payload"] = None
        stub.FORGE["mutate"] = None

    def refused(self, kind, l1, l2, why):
        with self.assertRaises(Reverted) as e:
            self.s.auth(kind, l1, l2)
        self.assertIn(why, e.exception.msg)
        self.assertEqual(self.s.view(self.s.reader, "get_config")["auths"], 0)


class AuthArbitrum(Base):
    def test_standard_gateway(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)
        rec = self.s.view(self.s.reader, "get_auth", a["auth_id"])
        self.assertEqual((rec["vault"], rec["dest_chain"], rec["source_decimals"]), (F.ARB_GW, "arbitrum", 6))
        self.assertIn("gateway holds the escrow", rec["proof"])

    def test_custom_gateway_with_escrow(self):
        a = self.s.auth("arbitrum", DAI, F.ARB_DAI)
        self.assertEqual(a["vault"], F.ARB_DAI_ESCROW)

    def test_wrong_dest_refused(self):
        self.refused("arbitrum", USDC, F.ARB_WBTC, "L1_ROUTER_MAPS_TOKEN_TO_")

    def test_no_gateway_refused(self):
        self.refused("arbitrum", LINK, F.ARB_USDC, "ROUTER_HAS_NO_GATEWAY_FOR_TOKEN")

    def test_l2_router_disagrees_refused(self):
        self.s.net.arbitrum(USDC, F.ARB_USDC, l2_router_says=F.ARB_WBTC)
        self.refused("arbitrum", USDC, F.ARB_USDC, "L2_ROUTER_DISAGREES")

    def test_decimals_unreadable_refused(self):
        self.s.net.fn("arbitrum", F.ARB_USDC, CR.S_DECIMALS, lambda d, b: F.REVERT)
        self.refused("arbitrum", USDC, F.ARB_USDC, "DECIMALS_UNREADABLE")

    def test_decimals_absurd_refused(self):
        self.s.net.decimals("arbitrum", F.ARB_USDC, 77)
        self.refused("arbitrum", USDC, F.ARB_USDC, "DECIMALS_UNREADABLE")


class AuthOpStack(Base):
    def test_optimism(self):
        a = self.s.auth("optimism", USDC, F.OP_USDC)
        self.assertEqual(a["vault"], CR.OP_L1_BRIDGE)
        rec = self.s.view(self.s.reader, "get_auth", a["auth_id"])
        self.assertIn("L1StandardBridge.deposits(l1,l2)=500000000000", rec["proof"])

    def test_base_legacy_getters(self):
        self.assertEqual(self.s.auth("base", USDC, F.BASE_USDC)["vault"], CR.BASE_L1_BRIDGE)

    def test_remote_token_mismatch(self):
        self.s.net.opstack("optimism", WBTC, F.OP_USDC2)
        self.refused("optimism", USDC, F.OP_USDC2, "REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN")

    def test_not_standard_bridge(self):
        self.s.net.opstack("optimism", USDC, F.OP_USDC2, bridge=F.addr(999))
        self.refused("optimism", USDC, F.OP_USDC2, "NOT_MINTED_BY_THE_L2_STANDARD_BRIDGE")

    def test_plain_erc20_refused(self):
        self.s.net.token("optimism", F.addr(777), 6, 1)
        self.refused("optimism", USDC, F.addr(777), "REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN")

    def test_eoa_refused(self):
        self.refused("optimism", USDC, F.addr(778), "REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN")

    def test_wrong_chain_for_kind(self):
        # a base token presented as an optimism destination: nothing at that address on optimism
        self.refused("optimism", USDC, F.BASE_USDC, "REMOTE_TOKEN_IS_NOT")

    def test_fake_lookalike_authenticates_but_is_capped(self):
        # OP_FAKE answers remoteToken()=USDC and bridge()=L2StandardBridge and has minted 10^15
        # outside the bridge. It authenticates (its getters are right) - which is exactly why
        # its supply is counted only up to the bridge's own deposits for it (1 wei).
        a = self.s.auth("optimism", USDC, F.OP_FAKE)
        self.assertEqual(a["vault"], CR.OP_L1_BRIDGE)


class AuthOpDai(Base):
    def test_ok(self):
        self.assertEqual(self.s.auth("op_dai", DAI, F.OP_DAI)["vault"], F.OP_DAI_ESCROW)

    def test_wrong_l1(self):
        self.refused("op_dai", USDC, F.OP_DAI, "DAI_BRIDGE_L1_TOKEN_MISMATCH")

    def test_wrong_l2(self):
        self.refused("op_dai", DAI, F.OP_USDC, "DAI_BRIDGE_L2_TOKEN_MISMATCH")

    def test_l2_bridge_points_elsewhere(self):
        self.s.net.fn("optimism", CR.OP_DAI_L2_BRIDGE, CR.S_L1_DAI_BRIDGE, lambda d, b: F.wa(F.addr(5)))
        self.refused("op_dai", DAI, F.OP_DAI, "L2_DAI_BRIDGE_POINTS_ELSEWHERE")

    def test_no_escrow(self):
        self.s.net.fn("ethereum", CR.OP_DAI_L1_BRIDGE, CR.S_ESCROW, lambda d, b: F.w(0))
        self.refused("op_dai", DAI, F.OP_DAI, "DAI_BRIDGE_HAS_NO_ESCROW")


class AuthPolygon(Base):
    def test_ok(self):
        self.assertEqual(self.s.auth("polygon", USDC, F.POL_USDC)["vault"], F.POL_PRED)

    def test_wrong_child(self):
        self.refused("polygon", USDC, F.OP_USDC, "ROOT_CHAIN_MANAGER_MAPS_TOKEN_TO_")

    def test_unmapped_root(self):
        self.refused("polygon", WBTC, F.POL_USDC, "ROOT_CHAIN_MANAGER_MAPS_TOKEN_TO_0x0000")

    def test_child_manager_disagrees(self):
        self.s.net.polygon(USDC, F.POL_USDC, child_says=WBTC)
        self.refused("polygon", USDC, F.POL_USDC, "CHILD_CHAIN_MANAGER_DISAGREES")

    def test_no_predicate(self):
        self.s.net.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TYPE_TO_PRED, lambda d, b: F.w(0))
        self.refused("polygon", USDC, F.POL_USDC, "TYPE_HAS_NO_PREDICATE")

    def test_no_type(self):
        self.s.net.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TOKEN_TO_TYPE, lambda d, b: F.w(0))
        self.refused("polygon", USDC, F.POL_USDC, "TOKEN_HAS_NO_TYPE")


class AuthNomad(Base):
    def test_ok(self):
        self.assertEqual(self.s.auth("nomad", USDC, F.BEAM_USDC)["vault"], CR.NOMAD_ETH_ROUTER)

    def test_wrong_rep(self):
        self.refused("nomad", USDC, F.addr(4242), "TOKEN_REGISTRY_DOES_NOT_MAP")

    def test_wrong_source(self):
        self.refused("nomad", WBTC, F.BEAM_USDC, "TOKEN_REGISTRY_DOES_NOT_MAP")

    def test_remote_router_elsewhere(self):
        self.s.net.nomad(USDC, F.BEAM_USDC, remote=F.addr(66))
        self.refused("nomad", USDC, F.BEAM_USDC, "MOONBEAM_ROUTER_REMOTE_IS_NOT_THE_ETHEREUM_ROUTER")

    def test_other_domain(self):
        self.s.net.nomad(USDC, F.BEAM_USDC, domain=1000)
        self.refused("nomad", USDC, F.BEAM_USDC, "TOKEN_REGISTRY_DOES_NOT_MAP")

    def test_source_not_local_on_ethereum(self):
        self.s.net.fn("ethereum", F.NOMAD_ETH_REG, CR.S_GET_TOKEN_ID, lambda d, b: F.w(1650811245) + F.wa(USDC)[2:])
        self.refused("nomad", USDC, F.BEAM_USDC, "SOURCE_TOKEN_IS_NOT_LOCAL_ON_ETHEREUM")


class AuthInputs(Base):
    def test_unsupported_kind(self):
        self.refused("wormhole", USDC, F.ARB_USDC, "UNSUPPORTED_BRIDGE_KIND")

    def test_bad_address(self):
        self.refused("arbitrum", "0x1234", F.ARB_USDC, "BAD_TOKEN_ADDRESS")

    def test_zero_address(self):
        self.refused("arbitrum", "0x" + "0" * 40, F.ARB_USDC, "BAD_TOKEN_ADDRESS")

    def test_kind_case_insensitive(self):
        self.assertEqual(self.s.auth(" Arbitrum ", USDC.upper().replace("0X", "0x"), F.ARB_USDC)["vault"], F.ARB_GW)

    def test_no_clock(self):
        self.s.w.now_iso = "garbage"
        self.refused("arbitrum", USDC, F.ARB_USDC, "NO_CLOCK")

    def test_ids_increment(self):
        a = self.s.auth("arbitrum", USDC, F.ARB_USDC)
        b = self.s.auth("arbitrum", USDC, F.ARB_USDC)
        self.assertEqual((a["auth_id"], b["auth_id"]), (1, 2))

    def test_missing_auth_view(self):
        self.assertEqual(self.s.view(self.s.reader, "get_auth", 99), {"found": False})


class AuthTransport(Base):
    def test_one_rpc_down_refused(self):
        stub.WEB.down.add(CR.CHAINS["arbitrum"][1][1])
        self.refused("arbitrum", USDC, F.ARB_USDC, "RPC_UNREADABLE")

    def test_rpcs_disagree_refused(self):
        url = CR.CHAINS["ethereum"][1][1]

        def lie(req, ans):
            if req["method"] == "eth_call" and req["params"][0]["data"].startswith(CR.S_CALC_L2):
                ans = dict(ans)
                ans["result"] = F.wa(F.addr(1))
            return ans
        stub.WEB.tamper[url] = lie
        self.refused("arbitrum", USDC, F.ARB_USDC, "RPC_DISAGREE")

    def test_wrong_chain_id_refused(self):
        self.s.net.mc["arbitrum"].chain_id = 1
        self.refused("arbitrum", USDC, F.ARB_USDC, "RPC_WRONG_CHAIN_OR_UNREADABLE")

    def test_http_500_refused(self):
        stub.WEB.rpc_status[CR.CHAINS["ethereum"][1][0]] = 500
        self.refused("arbitrum", USDC, F.ARB_USDC, "RPC_UNREADABLE")

    def test_forged_vault_rejected_by_validators(self):
        stub.FORGE["mutate"] = lambda r: dict(r, vault=F.addr(13))
        with self.assertRaises(Reverted) as e:
            self.s.auth("arbitrum", USDC, F.ARB_USDC)
        self.assertIn("UNDETERMINED", e.exception.msg)

    def test_forged_decimals_rejected(self):
        stub.FORGE["mutate"] = lambda r: dict(r, dest_decimals=18)
        with self.assertRaises(Reverted):
            self.s.auth("arbitrum", USDC, F.ARB_USDC)

    def test_leader_block_ahead_of_validator_rejected(self):
        def ahead():
            self.s.net.mine_to(self.s.w.now() + 600)
        def back():
            for ch, m in self.s.net.mc.items():
                m.finalized = F.START[ch]
        stub.WEB.leader_hook = ahead
        stub.WEB.validator_hook = back
        with self.assertRaises(Reverted):
            self.s.auth("arbitrum", USDC, F.ARB_USDC)

    def test_only_allowlisted_urls_contacted(self):
        stub.WEB.log.clear()
        self.s.auth("nomad", USDC, F.BEAM_USDC)
        allowed = set(u for c in CR.CHAINS.values() for u in c[1])
        self.assertTrue(set(stub.WEB.log) <= allowed)

    def test_not_allowlisted_url_refused(self):
        with self.assertRaises(CR.ReadFailed):
            CR.rpc_send("https://evil.example/rpc", [["eth_chainId", []]])


class Read(Base):
    def pair_check(self, name="arb_usdc", **k):
        pid = self.s.pair(name)
        self.s.after_bond()
        blocks = self.s.blocks(pid, **k)
        cid = self.s.monitor(pid, blocks)["check_id"]
        return pid, cid, blocks

    def reading(self, cid, rnd=1):
        return self.s.view(self.s.reader, "get_reading", self.s.reg, cid, rnd)

    def test_ok_reading(self):
        pid, cid, blocks = self.pair_check()
        out = self.s.read(cid)
        self.assertEqual(out["status"], "OK")
        r = self.reading(cid)["reading"]
        self.assertEqual(r["locked"], str(1_000_000 * 10 ** 6))
        self.assertEqual(r["blocks"]["ethereum"]["number"], blocks["ethereum"])
        self.assertEqual(r["dests"][0]["supply"], str(1_000_000 * 10 ** 6))

    def test_values_at_the_pinned_block_not_latest(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.balance("ethereum", USDC, F.ARB_GW, 1, from_block=blocks["ethereum"] + 1)
        self.s.read(cid)
        self.assertEqual(self.reading(cid)["reading"]["locked"], str(1_000_000 * 10 ** 6))

    def test_deposits_read_for_opstack(self):
        pid, cid, _ = self.pair_check("op_usdc")
        self.s.read(cid)
        self.assertEqual(self.reading(cid)["reading"]["dests"][0]["deposits"], str(500_000 * 10 ** 6))

    def test_no_deposits_for_arbitrum(self):
        pid, cid, _ = self.pair_check()
        self.s.read(cid)
        self.assertEqual(self.reading(cid)["reading"]["dests"][0]["deposits"], "")

    def test_already_read(self):
        pid, cid, _ = self.pair_check()
        self.s.read(cid)
        with self.assertRaises(Reverted) as e:
            self.s.read(cid)
        self.assertIn("ALREADY_READ", e.exception.msg)

    def test_wrong_round(self):
        pid, cid, _ = self.pair_check()
        with self.assertRaises(Reverted) as e:
            self.s.read(cid, 2)
        self.assertIn("NOT_THIS_ROUND", e.exception.msg)

    def test_round_out_of_range(self):
        pid, cid, _ = self.pair_check()
        with self.assertRaises(Reverted):
            self.s.read(cid, 3)

    def test_no_such_check(self):
        self.s.pair()
        with self.assertRaises(Reverted) as e:
            self.s.read(5)
        self.assertIn("REQUEST_NOT_READABLE", e.exception.msg)

    def test_closed_check_not_readable(self):
        pid, cid, _ = self.pair_check()
        self.s.read(cid)
        self.s.rule(cid)
        self.s.finalize_after_window(cid)
        with self.assertRaises(Reverted):
            self.s.read(cid, 2)

    def test_not_a_registry(self):
        with self.assertRaises(Reverted) as e:
            self.s.call(self.s.reader, "read_check", F.addr(1234), 1, 1, sender=F.PATROL)
        self.assertIn("REGISTRY_UNREADABLE", e.exception.msg)

    def test_not_finalized_inconclusive(self):
        pid = self.s.pair()
        self.s.after_bond()
        self.s.net.mine_to(self.s.w.now() + 3000, finalize=False)
        blocks = {"ethereum": self.s.net.head["ethereum"], "arbitrum": self.s.net.head["arbitrum"]}
        cid = self.s.monitor(pid, blocks)["check_id"]
        out = self.s.read(cid)
        self.assertEqual((out["status"], out["reason"][:19]), ("INCONCLUSIVE", "BLOCK_NOT_FINALIZED"))

    def test_finalized_on_one_rpc_only_inconclusive(self):
        pid, cid, blocks = self.pair_check()
        m2 = stub.MockChain(1, F.START["ethereum"], F.NOW - 900)
        m2.blocks = dict(self.s.net.mc["ethereum"].blocks)
        m2.fns = self.s.net.mc["ethereum"].fns
        m2.code = self.s.net.mc["ethereum"].code
        m2.finalized = blocks["ethereum"] - 1
        stub.WEB.chains[CR.CHAINS["ethereum"][1][1]] = m2
        self.assertEqual(self.s.read(cid)["reason"], "BLOCK_NOT_FINALIZED:ethereum")

    def test_disagreement_inconclusive(self):
        pid, cid, blocks = self.pair_check()

        def lie(req, ans):
            if req["method"] == "eth_call" and req["params"][0]["data"].startswith(CR.S_SUPPLY):
                return dict(ans, result=F.w(5))
            return ans
        stub.WEB.tamper[CR.CHAINS["arbitrum"][1][1]] = lie
        out = self.s.read(cid)
        self.assertEqual((out["status"], out["reason"]), ("INCONCLUSIVE", "RPC_DISAGREE"))

    def test_block_hash_disagreement_inconclusive(self):
        pid, cid, blocks = self.pair_check()

        def lie(req, ans):
            if req["method"] == "eth_getBlockByNumber" and req["params"][0] != "finalized" and ans.get("result"):
                r = dict(ans["result"])
                r["hash"] = "0x" + "9" * 64
                return dict(ans, result=r)
            return ans
        stub.WEB.tamper[CR.CHAINS["ethereum"][1][0]] = lie
        self.assertEqual(self.s.read(cid)["reason"], "RPC_DISAGREE")

    def test_rpc_down_inconclusive_round1(self):
        pid, cid, blocks = self.pair_check()
        stub.WEB.down.add(CR.CHAINS["arbitrum"][1][0])
        out = self.s.read(cid)
        self.assertEqual((out["status"], out["reason"]), ("INCONCLUSIVE", "RPC_UNREADABLE"))

    def test_rpc_error_object_inconclusive(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.mc["arbitrum"].fail = lambda m, p: {"code": -32000, "message": "missing trie node"} if m == "eth_call" else None
        self.assertEqual(self.s.read(cid)["reason"], "RPC_UNREADABLE")

    def test_transient_jsonrpc_error_is_retried(self):
        pid, cid, blocks = self.pair_check()
        n = {"left": 2}

        def burst(m, p):
            if m == "eth_call" and n["left"] > 0:
                n["left"] -= 1
                return {"code": -32005, "message": "Too many requests"}
            return None
        self.s.net.mc["arbitrum"].fail = burst
        self.assertEqual(self.s.read(cid)["status"], "OK")

    def test_http_429_then_ok_is_retried(self):
        pid, cid, blocks = self.pair_check()
        url = CR.CHAINS["arbitrum"][1][1]
        n = {"left": 1}
        orig = stub._web_request

        def flaky(u, **k):
            if u == url and n["left"] > 0:
                n["left"] -= 1
                return stub._Response(429, "{}")
            return orig(u, **k)
        CR.gl.nondet.web.request = flaky
        try:
            self.assertEqual(self.s.read(cid)["status"], "OK")
        finally:
            CR.gl.nondet.web.request = orig

    def test_revert_is_not_retried(self):
        pid, cid, blocks = self.pair_check()
        calls = {"n": 0}

        def rev(d, b):
            calls["n"] += 1
            return F.REVERT
        self.s.net.fn("ethereum", USDC, CR.S_BALANCE, rev)
        self.s.read(cid)
        self.assertLessEqual(calls["n"], 4)   # leader + validator, each RPC once

    def test_balance_reverts_call_failed(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.fn("ethereum", USDC, CR.S_BALANCE, lambda d, b: F.REVERT)
        self.assertEqual(self.s.read(cid)["reason"], "CALL_FAILED:ethereum")

    def test_supply_reverts_call_failed(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.fn("arbitrum", F.ARB_USDC, CR.S_SUPPLY, lambda d, b: F.REVERT)
        self.assertEqual(self.s.read(cid)["reason"], "CALL_FAILED:arbitrum")

    def test_short_return_call_failed(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.fn("arbitrum", F.ARB_USDC, CR.S_SUPPLY, lambda d, b: "0x01")
        self.assertEqual(self.s.read(cid)["reason"], "CALL_FAILED:arbitrum")

    def test_decimals_absurd_call_failed(self):
        pid, cid, blocks = self.pair_check()
        self.s.net.decimals("arbitrum", F.ARB_USDC, 255)
        self.assertEqual(self.s.read(cid)["reason"], "CALL_FAILED:arbitrum")

    def test_block_missing(self):
        pid = self.s.pair()
        self.s.after_bond()
        blocks = self.s.blocks(pid)
        del self.s.net.mc["arbitrum"].blocks[blocks["arbitrum"]]
        cid = self.s.monitor(pid, blocks)["check_id"]
        self.assertEqual(self.s.read(cid)["reason"], "BLOCK_MISSING:arbitrum")

    def test_forged_reading_rejected(self):
        pid, cid, blocks = self.pair_check()
        stub.FORGE["mutate"] = lambda r: dict(r, locked="1")
        with self.assertRaises(Reverted) as e:
            self.s.read(cid)
        self.assertIn("UNDETERMINED", e.exception.msg)
        self.assertFalse(self.reading(cid)["found"])

    def test_forged_inconclusive_rejected(self):
        pid, cid, blocks = self.pair_check()
        stub.FORGE["payload"] = {"status": "INCONCLUSIVE", "reason": "RPC_DISAGREE", "blocks": {}, "locked": "",
                                 "source_decimals": -1, "dests": []}
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_validator_sees_other_data_no_record(self):
        pid, cid, blocks = self.pair_check()

        def flip():
            self.s.net.supply("arbitrum", F.ARB_USDC, 7)
        stub.WEB.validator_hook = flip
        with self.assertRaises(Reverted):
            self.s.read(cid)

    def test_batches_respect_drpc_cap(self):
        pid, cid, blocks = self.pair_check("op_usdc")
        stub.WEB.caps["https://optimism.drpc.org"] = 3
        stub.WEB.caps["https://polygon.drpc.org"] = 3
        self.assertEqual(self.s.read(cid)["status"], "OK")

    def test_batch_over_cap_would_fail(self):
        # the cap table is what keeps dRPC answering: without it the batch is refused
        pid, cid, blocks = self.pair_check("op_usdc")
        stub.WEB.caps["https://optimism.drpc.org"] = 2
        self.assertEqual(self.s.read(cid)["reason"], "RPC_UNREADABLE")

    def test_reading_view_shape(self):
        pid, cid, blocks = self.pair_check()
        self.s.read(cid)
        r = self.reading(cid)
        for k in ("request_sha", "status", "reason", "reading", "read_at", "reader", "round"):
            self.assertIn(k, r)
        self.assertEqual(r["reader"], F.PATROL)

    def test_req_shape_checks(self):
        ok = {"ok": True, "source_chain": "ethereum", "vault": F.ARB_GW, "source_token": USDC,
              "dests": [{"chain": "arbitrum", "token": F.ARB_USDC}], "blocks": {"ethereum": 5, "arbitrum": 6}}
        self.assertEqual(CR._req_ok(ok), "")
        self.assertEqual(CR._req_ok(dict(ok, source_chain="base")), "BAD_SOURCE_CHAIN")
        self.assertEqual(CR._req_ok(dict(ok, blocks={"ethereum": 5})), "BLOCKS_DO_NOT_MATCH_CHAINS")
        self.assertEqual(CR._req_ok(dict(ok, dests=[])), "BAD_DESTS")
        self.assertEqual(CR._req_ok(dict(ok, dests=[{"chain": "solana", "token": F.ARB_USDC}])), "BAD_DEST")
        self.assertEqual(CR._req_ok(dict(ok, blocks={"ethereum": 0, "arbitrum": 6})), "BAD_BLOCK_NUMBER")
        self.assertEqual(CR._req_ok(dict(ok, ok=False)), "NOT_READABLE")
        self.assertEqual(CR._req_ok(dict(ok, vault="nope")), "BAD_ADDRESSES")

    def test_config(self):
        c = self.s.view(self.s.reader, "get_config")
        self.assertEqual(sorted(c["chains"]), sorted(["ethereum", "arbitrum", "optimism", "base", "polygon", "moonbeam"]))
        for ch in c["chains"].values():
            self.assertEqual(len(ch["rpcs"]), 2)
            self.assertNotEqual(ch["rpcs"][0], ch["rpcs"][1])


class Parse(unittest.TestCase):
    def test_revert_code_3(self):
        self.assertEqual(CR.parse_batch([{"id": 0, "error": {"code": 3, "message": "x"}}], 1), [["revert", None]])

    def test_revert_message(self):
        self.assertEqual(CR.parse_batch([{"id": 0, "error": {"code": -32000, "message": "execution reverted"}}], 1),
                         [["revert", None]])

    def test_other_error_raises(self):
        with self.assertRaises(CR.ReadFailed):
            CR.parse_batch([{"id": 0, "error": {"code": -32000, "message": "header not found"}}], 1)

    def test_missing_id_raises(self):
        with self.assertRaises(CR.ReadFailed):
            CR.parse_batch([{"id": 1, "result": "0x"}], 1)

    def test_bool_id_ignored(self):
        with self.assertRaises(CR.ReadFailed):
            CR.parse_batch([{"id": True, "result": "0x"}], 1)

    def test_out_of_order(self):
        got = CR.parse_batch([{"id": 1, "result": "b"}, {"id": 0, "result": "a"}], 2)
        self.assertEqual(got, [["ok", "a"], ["ok", "b"]])

    def test_single_object(self):
        self.assertEqual(CR.parse_batch({"id": 0, "result": "z"}, 1), [["ok", "z"]])

    def test_proj_eth_call(self):
        self.assertEqual(CR._proj(["eth_call"], ["ok", "0xAB"]), ["ok", "0xab"])
        self.assertEqual(CR._proj(["eth_call"], ["ok", "0xabc"]), ["bad", None])
        self.assertEqual(CR._proj(["eth_call"], ["ok", "zz"]), ["bad", None])
        self.assertEqual(CR._proj(["eth_call"], ["revert", None]), ["revert", None])

    def test_proj_block_ignores_extra_fields(self):
        a = CR._block_of(["ok", {"number": "0x1", "timestamp": "0x2", "hash": "0x" + "a" * 64, "miner": "x"}])
        b = CR._block_of(["ok", {"number": "0x1", "timestamp": "0x2", "hash": "0x" + "a" * 64, "miner": "y"}])
        self.assertEqual(a, b)

    def test_block_bad_hash(self):
        self.assertIsNone(CR._block_of(["ok", {"number": "0x1", "timestamp": "0x2", "hash": "0x12"}]))

    def test_word_helpers(self):
        self.assertEqual(CR._word(["ok", "0x" + "0" * 63 + "5"]), 5)
        self.assertEqual(CR._word(["revert", None]), -1)
        self.assertEqual(CR._addr_w(["ok", "0x" + "f" * 64]), "")
        self.assertEqual(CR._addr_w(["ok", F.wa(USDC)]), USDC)


if __name__ == "__main__":
    unittest.main()
