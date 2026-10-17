"""Shared vaults: one Ethereum vault that backs the same token on many chains
must be judged against every destination it backs. USDT0's Ethereum adapter
backs USDT0 on every chain it has a LayerZero peer on; the pair holds all of
them that two RPCs can read (docs/SEEDS.md), each authenticated through the
OFT on its own chain's endpoint.

    cd test && python3 -m unittest -q test_shared
"""
import unittest

import fixtures as F
import world
from fixtures import CR, RG, USDT, STRANGER
from test_registry import Base

Reverted = world.Reverted

# every chain the reader knows that only carries USDT0
USDT0_ONLY = ["mantle", "xlayer", "sei", "flare", "hedera", "unichain", "morph", "ink", "berachain", "hyperevm", "monad"]


class Tables(unittest.TestCase):
    def test_every_oft_kind_is_complete(self):
        for k, chain in CR.KINDS.items():
            if not k.startswith("oft_"):
                continue
            self.assertIn(chain, CR.CHAINS, k)
            self.assertIn(chain, CR.LZ_EID, k)
            self.assertIn(chain, CR.LZ_ENDPOINTS, k)
            self.assertEqual(RG.KINDS.get(k), chain, k)
            self.assertEqual(RG.KIND_MAX_GAP_S[k], RG.FAST_GAP_S, k)

    def test_usdt0_chains_present(self):
        for c in USDT0_ONLY:
            self.assertIn("oft_" + c, CR.KINDS)
        self.assertEqual(len(set(CR.LZ_EID.values())), len(CR.LZ_EID))

    def test_two_distinct_rpcs_per_chain(self):
        for c, (cid, urls) in CR.CHAINS.items():
            self.assertEqual(len(urls), 2, c)
            self.assertNotEqual(urls[0], urls[1], c)
            hosts = [u.split("/")[2] for u in urls]
            self.assertNotEqual(hosts[0], hosts[1], c)

    def test_limits_fit_usdt0(self):
        self.assertGreaterEqual(RG.MAX_DESTS, 3 + len(USDT0_ONLY))
        self.assertEqual(RG.MAX_DESTS, CR.MAX_DESTS)
        self.assertEqual(RG.MAX_ANCHORS, CR.MAX_ANCHORS)


class SharedVault(Base):
    SUPPLY = 10_000 * 10 ** 6

    def setUp(self):
        super().setUp()
        n = self.s.net
        self.tokens = {}
        for i, c in enumerate(USDT0_ONLY):
            tok, oft = F.addr(0x6000 + i), F.addr(0x6100 + i)
            n.token(c, tok, 6, self.SUPPLY)
            if c == "hedera":
                n.oft(c, USDT, tok, F.USDT0_ADAPTER, oft, via_adapter=True)
                self.tokens[c] = (oft, tok)          # authenticated through the OFT
            else:
                n.oft(c, USDT, tok, F.USDT0_ADAPTER, oft)
                self.tokens[c] = (tok, tok)
        n.mine_to(self.s.w.now() - 900)

    def pair_with_all(self):
        a = self.s.auth("polygon", USDT, F.POL_USDT)["auth_id"]
        pid = self.s.call(self.s.reg, "register_pair", str(a), 0, "USDT")["pair_id"]
        v = self.s.auth("oft_polygon", USDT, F.POL_USDT, sender=STRANGER)["auth_id"]
        self.s.call(self.s.reg, "add_vault", pid, v, sender=STRANGER)
        for kind, l2 in [("oft_arbitrum", F.ARB_USDT0)] + [("oft_" + c, self.tokens[c][0]) for c in USDT0_ONLY]:
            d = self.s.auth(kind, USDT, l2, sender=STRANGER)["auth_id"]
            self.s.call(self.s.reg, "add_destination", pid, d, sender=STRANGER)
        return pid

    def test_hedera_auth_names_the_hts_token(self):
        oft, tok = self.tokens["hedera"]
        a = self.s.auth("oft_hedera", USDT, oft)
        self.assertEqual((a["vault"], a["dest_token"]), (F.USDT0_ADAPTER, tok))
        rec = self.s.view(self.s.reader, "get_auth", a["auth_id"])
        self.assertEqual(rec["dest_token"], tok)
        self.assertIn(["hedera", oft, CR.S_TOKEN, F.wa(tok)], rec["anchors"])

    def test_endpoint_is_per_chain(self):
        tok, oft = F.addr(0x6200), F.addr(0x6201)
        self.s.net.token("ink", tok, 6, 1)
        self.s.net.oft("ink", USDT, tok, F.USDT0_ADAPTER, oft, endpoint=CR.LZ_ENDPOINT)
        with self.assertRaises(Reverted) as e:
            self.s.auth("oft_ink", USDT, tok)
        self.assertIn("OFT_NOT_ON_THE_LAYERZERO_ENDPOINT", e.exception.msg)
        self.assertNotEqual(CR.LZ_ENDPOINTS["ink"], CR.LZ_ENDPOINT)

    def test_one_pair_lists_every_destination(self):
        pid = self.pair_with_all()
        p = self.s.view(self.s.reg, "get_pair", pid)
        self.assertEqual(len(p["dests"]), 2 + len(USDT0_ONLY))
        self.assertEqual(sorted({d["chain"] for d in p["dests"]}), sorted(["polygon", "arbitrum"] + USDT0_ONLY))
        self.assertEqual(p["max_gap_s"], RG.FAST_GAP_S)

    def test_destination_cannot_leave_for_another_pair(self):
        pid = self.pair_with_all()
        d = self.s.auth("oft_monad", USDT, self.tokens["monad"][0])["auth_id"]
        with self.assertRaises(Reverted) as e:
            self.s.call(self.s.reg, "register_pair", str(d), 0, "USDT on Monad alone")
        self.assertIn("VAULT_ALREADY_IN_PAIR_" + str(pid), e.exception.msg)

    def test_supply_summed_over_every_chain(self):
        pid = self.pair_with_all()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        out = self.provisional(cid)
        r = self.s.check(cid)["ruling1"]
        want = 700_000 * 10 ** 6 + 800_000 * 10 ** 6 + len(USDT0_ONLY) * self.SUPPLY
        self.assertEqual(r["supply_norm"], str(want))
        self.assertEqual(r["locked_norm"], str(1_500_000 * 10 ** 6))
        self.assertEqual(out["verdict"], "UNDER_BACKED")      # the adapter holds only Polygon + Arbitrum's share

    def test_enough_locked_for_all_is_backed(self):
        pid = self.pair_with_all()
        self.s.net.balance("ethereum", USDT, F.USDT0_ADAPTER, 1_495_000 * 10 ** 6 + len(USDT0_ONLY) * self.SUPPLY)
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.assertEqual(self.provisional(cid)["verdict"], "BACKED")
        rd = self.s.view(self.s.reader, "get_reading", self.s.reg, cid, 1)["reading"]
        self.assertEqual(len(rd["dests"]), 2 + len(USDT0_ONLY))

    def test_one_chain_unreadable_is_inconclusive(self):
        pid = self.pair_with_all()
        self.s.after_bond()
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        tok = self.tokens["sei"][1]
        self.s.net.fn("sei", tok, CR.S_SUPPLY, lambda d, b: F.REVERT)
        out = self.provisional(cid)
        self.assertEqual((out["status"], out["reason"]), ("INCONCLUSIVE", "CALL_FAILED:sei"))


if __name__ == "__main__":
    unittest.main()
