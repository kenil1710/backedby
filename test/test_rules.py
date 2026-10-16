"""The pure rules, driven directly: pins (order, gap), decimals,
normalization, tolerance, the deposits cap, slash split, reason classes,
block parsing, labels and the gate.

    cd test && python3 -m unittest -q test_rules
"""
import json
import unittest

import fixtures as F
from fixtures import RG, GT, CR

E = "ethereum"
TERMS = {"source_decimals": 6, "tolerance_bps": 0, "max_gap_s": 600,
         "dests": [{"chain": "arbitrum", "token": F.ARB_USDC, "decimals": 6}]}


def reading(locked, supply, sts=1000, dts=1000, sdec=6, ddec=6, deposits="", status="OK", reason="",
            token=None, chain="arbitrum"):
    return {"status": status, "reason": reason,
            "blocks": {E: {"number": 1, "hash": "0x" + "1" * 64, "timestamp": sts},
                       chain: {"number": 2, "hash": "0x" + "2" * 64, "timestamp": dts}},
            "locked": str(locked), "source_decimals": sdec,
            "dests": [{"chain": chain, "token": token or F.ARB_USDC, "supply": str(supply), "decimals": ddec,
                       "deposits": deposits}]}


def terms(**k):
    t = json.loads(json.dumps(TERMS))
    t.update(k)
    return t


class Pins(unittest.TestCase):
    def blocks(self, s, *d):
        out = {E: {"timestamp": s}}
        for i, t in enumerate(d):
            out["c%d" % i] = {"timestamp": t}
        return out

    def test_same_second_ok(self):
        self.assertEqual(RG.check_pins(self.blocks(1000, 1000), 600), "")

    def test_source_after_dest_ok(self):
        self.assertEqual(RG.check_pins(self.blocks(1000, 900), 600), "")

    def test_source_one_second_before_dest_refused(self):
        self.assertTrue(RG.check_pins(self.blocks(1000, 1001), 600).startswith("SOURCE_BLOCK_OLDER_THAN_"))

    def test_gap_exactly_600_ok(self):
        self.assertEqual(RG.check_pins(self.blocks(1600, 1000), 600), "")

    def test_gap_601_refused(self):
        self.assertEqual(RG.check_pins(self.blocks(1601, 1000), 600), "GAP_601S_OVER_600S")

    def test_gap_599_ok(self):
        self.assertEqual(RG.check_pins(self.blocks(1599, 1000), 600), "")

    def test_polygon_gap_300_ok_301_refused(self):
        self.assertEqual(RG.check_pins(self.blocks(1300, 1000), 300), "")
        self.assertEqual(RG.check_pins(self.blocks(1301, 1000), 300), "GAP_301S_OVER_300S")

    def test_gap_measured_to_oldest_destination(self):
        self.assertEqual(RG.check_pins(self.blocks(1700, 1690, 1099), 600), "GAP_601S_OVER_600S")
        self.assertEqual(RG.check_pins(self.blocks(1700, 1690, 1100), 600), "")

    def test_any_destination_newer_refused(self):
        self.assertTrue(RG.check_pins(self.blocks(1700, 1600, 1701), 600).startswith("SOURCE_BLOCK_OLDER"))

    def test_missing_source(self):
        self.assertEqual(RG.check_pins({"arbitrum": {"timestamp": 1}}, 600), "SOURCE_BLOCK_MISSING")

    def test_kind_gap_table(self):
        self.assertEqual(RG.KIND_MAX_GAP_S, {"polygon": 300})
        self.assertEqual(RG.MAX_GAP_S, 600)


class Verdict(unittest.TestCase):
    def v(self, *a, t=None, cover=None, **k):
        return RG.compute(reading(*a, **k), t or terms(), cover)

    def test_exact_backing_is_backed(self):
        o = self.v(100, 100)
        self.assertEqual((o["verdict"], o["ratio_bps"]), ("BACKED", 10000))

    def test_one_unit_short_is_under(self):
        self.assertEqual(self.v(99, 100)["verdict"], "UNDER_BACKED")

    def test_over_backed(self):
        self.assertEqual(self.v(150, 100)["ratio_bps"], 15000)

    def test_zero_supply_backed_ratio_minus_one(self):
        o = self.v(0, 0)
        self.assertEqual((o["verdict"], o["ratio_bps"]), ("BACKED", -1))

    def test_zero_locked_positive_supply_under(self):
        self.assertEqual(self.v(0, 1)["verdict"], "UNDER_BACKED")

    def test_tolerance_edge_exact(self):
        # 100 bps: locked >= supply * 0.99 -> 99 of 100 is exactly at the edge
        self.assertEqual(self.v(99, 100, t=terms(tolerance_bps=100))["verdict"], "BACKED")

    def test_tolerance_edge_one_below(self):
        self.assertEqual(self.v(9899, 10000, t=terms(tolerance_bps=100))["verdict"], "UNDER_BACKED")

    def test_tolerance_edge_large_numbers(self):
        s = 10 ** 30
        self.assertEqual(self.v(s - s // 100, s, t=terms(tolerance_bps=100))["verdict"], "BACKED")
        self.assertEqual(self.v(s - s // 100 - 1, s, t=terms(tolerance_bps=100))["verdict"], "UNDER_BACKED")

    def test_ratio_floor(self):
        self.assertEqual(self.v(2, 3)["ratio_bps"], 6666)

    def test_decimals_normalized_up(self):
        # 1 WBTC locked (8 dec) vs 1e18 units of an 18-dec representation
        t = terms(source_decimals=8, dests=[{"chain": "arbitrum", "token": F.ARB_USDC, "decimals": 18}])
        o = RG.compute(reading(10 ** 8, 10 ** 18, sdec=8, ddec=18), t, None)
        self.assertEqual((o["verdict"], o["ratio_bps"], o["scale_decimals"]), ("BACKED", 10000, 18))

    def test_decimals_normalized_down_side(self):
        t = terms(source_decimals=18, dests=[{"chain": "arbitrum", "token": F.ARB_USDC, "decimals": 6}])
        o = RG.compute(reading(10 ** 18 - 1, 10 ** 6, sdec=18, ddec=6), t, None)
        self.assertEqual(o["verdict"], "UNDER_BACKED")
        o = RG.compute(reading(10 ** 18, 10 ** 6, sdec=18, ddec=6), t, None)
        self.assertEqual(o["verdict"], "BACKED")

    def test_source_decimals_mismatch_inconclusive(self):
        o = self.v(100, 100, sdec=18)
        self.assertEqual((o["verdict"], o["cls"]), ("INCONCLUSIVE", "DATA"))
        self.assertTrue(o["reason"].startswith("DECIMALS_MISMATCH:source"))

    def test_dest_decimals_mismatch_inconclusive(self):
        o = self.v(100, 100, ddec=18)
        self.assertTrue(o["reason"].startswith("DECIMALS_MISMATCH:0x"))

    def test_deposits_cap_counts_min(self):
        o = self.v(100, 10 ** 15, deposits="1")
        self.assertEqual((o["verdict"], o["counted"]), ("BACKED", ["1"]))

    def test_deposits_cap_does_not_hide_real_shortfall(self):
        o = self.v(50, 100, deposits="100")
        self.assertEqual(o["verdict"], "UNDER_BACKED")

    def test_deposits_above_supply_counts_supply(self):
        self.assertEqual(self.v(100, 100, deposits="500")["counted"], ["100"])

    def test_bad_deposits_text(self):
        self.assertEqual(self.v(100, 100, deposits="x")["reason"], "MALFORMED_ANSWER")

    def test_order_violation_is_pin(self):
        o = self.v(100, 100, sts=1000, dts=1001)
        self.assertEqual((o["verdict"], o["cls"]), ("INCONCLUSIVE", "PIN"))

    def test_gap_violation_is_pin(self):
        o = self.v(100, 100, sts=1601, dts=1000)
        self.assertEqual((o["cls"], o["reason"]), ("PIN", "GAP_601S_OVER_600S"))

    def test_gap_exactly_ten_minutes_rules(self):
        self.assertEqual(self.v(100, 100, sts=1600, dts=1000)["verdict"], "BACKED")

    def test_reading_inconclusive_passthrough(self):
        o = self.v(0, 0, status="INCONCLUSIVE", reason="RPC_DISAGREE")
        self.assertEqual((o["verdict"], o["reason"], o["cls"]), ("INCONCLUSIVE", "RPC_DISAGREE", "DATA"))

    def test_reading_not_finalized_is_pin(self):
        o = self.v(0, 0, status="INCONCLUSIVE", reason="BLOCK_NOT_FINALIZED:arbitrum")
        self.assertEqual(o["cls"], "PIN")

    def test_transport_class(self):
        self.assertEqual(self.v(0, 0, status="INCONCLUSIVE", reason="RPC_UNREADABLE")["cls"], "TRANSPORT")

    def test_malformed_reading(self):
        self.assertEqual(RG.compute({"status": "??"}, terms(), None)["reason"], "MALFORMED_ANSWER")
        self.assertEqual(RG.compute("nope", terms(), None)["cls"], "DATA")

    def test_dest_count_mismatch(self):
        t = terms(dests=TERMS["dests"] * 2)
        self.assertEqual(RG.compute(reading(1, 1), t, None)["reason"], "MALFORMED_ANSWER")

    def test_dest_token_swapped(self):
        self.assertEqual(self.v(1, 1, token=F.OP_USDC)["reason"], "MALFORMED_ANSWER")

    def test_negative_locked_text(self):
        self.assertEqual(self.v("-5", 1)["reason"], "MALFORMED_ANSWER")

    def test_negative_supply_text(self):
        self.assertEqual(self.v(5, "-1")["reason"], "MALFORMED_ANSWER")

    def test_cover_before_bond(self):
        o = self.v(100, 100, sts=1000, dts=1000, cover=[1001, 0])
        self.assertEqual(o["reason"], "SOURCE_BLOCK_BEFORE_THE_BOND_STARTED")

    def test_cover_at_bond_start(self):
        self.assertEqual(self.v(100, 100, sts=1000, dts=1000, cover=[1000, 0])["verdict"], "BACKED")

    def test_cover_after_unbond(self):
        o = self.v(100, 100, sts=1001, dts=1000, cover=[0, 1000])
        self.assertEqual(o["reason"], "SOURCE_BLOCK_AFTER_THE_BOND_STOPPED")

    def test_cover_at_unbond(self):
        self.assertEqual(self.v(100, 100, sts=1000, dts=1000, cover=[0, 1000])["verdict"], "BACKED")

    def test_monitor_has_no_cover(self):
        self.assertEqual(self.v(100, 100, sts=5, dts=5, cover=None)["verdict"], "BACKED")

    def test_summed_supply_two_dests(self):
        t = terms(dests=[{"chain": "optimism", "token": F.OP_USDC, "decimals": 6},
                         {"chain": "optimism", "token": F.OP_USDC2, "decimals": 6}])
        r = reading(150, 100, chain="optimism", token=F.OP_USDC)
        r["dests"].append({"chain": "optimism", "token": F.OP_USDC2, "supply": "60", "decimals": 6, "deposits": ""})
        o = RG.compute(r, t, None)
        self.assertEqual((o["verdict"], o["supply_norm"]), ("UNDER_BACKED", "160"))

    def test_mixed_decimals_two_dests(self):
        t = terms(source_decimals=6, dests=[{"chain": "optimism", "token": F.OP_USDC, "decimals": 6},
                                            {"chain": "optimism", "token": F.OP_USDC2, "decimals": 18}])
        r = reading(2 * 10 ** 6, 10 ** 6, chain="optimism", token=F.OP_USDC)
        r["dests"].append({"chain": "optimism", "token": F.OP_USDC2, "supply": str(10 ** 18), "decimals": 18,
                           "deposits": ""})
        o = RG.compute(r, t, None)
        self.assertEqual((o["verdict"], o["ratio_bps"]), ("BACKED", 10000))


class Split(unittest.TestCase):
    def test_parts_sum(self):
        for b in [0, 1, 2, 3, 9999, 10000, 10001, 10 ** 18 + 7, 10 ** 30 - 1]:
            s = RG.slash_split(b)
            self.assertEqual(s[0], b)
            self.assertEqual(s[1] + s[2], s[0])
            self.assertLessEqual(s[1], s[0])

    def test_half(self):
        self.assertEqual(RG.slash_split(10 ** 18), [10 ** 18, 5 * 10 ** 17, 5 * 10 ** 17])

    def test_odd_wei_goes_to_treasury(self):
        self.assertEqual(RG.slash_split(3), [3, 1, 2])

    def test_negative_clamped(self):
        self.assertEqual(RG.slash_split(-5), [0, 0, 0])


class Classes(unittest.TestCase):
    def test_data(self):
        for r in ["RPC_DISAGREE", "CALL_FAILED:ethereum", "MALFORMED_ANSWER", "DECIMALS_MISMATCH:source 18!=6",
                  "CONTEST_DISAGREES", "CONTEST_REREAD_INCONCLUSIVE"]:
            self.assertEqual(RG.reason_class(r), "DATA", r)

    def test_pin(self):
        for r in ["BLOCK_NOT_FINALIZED:ethereum", "BLOCK_MISSING:base", "GAP_700S_OVER_600S",
                  "SOURCE_BLOCK_OLDER_THAN_ARBITRUM_BLOCK", "SOURCE_BLOCK_BEFORE_THE_BOND_STARTED"]:
            self.assertEqual(RG.reason_class(r), "PIN", r)

    def test_prefix_not_confused(self):
        self.assertEqual(RG.reason_class("RPC_DISAGREEMENTS"), "PIN")

    def test_transport(self):
        self.assertEqual(RG.reason_class("RPC_UNREADABLE"), "TRANSPORT")


class Blocks(unittest.TestCase):
    CH = ["ethereum", "arbitrum"]

    def test_ok(self):
        self.assertEqual(RG.parse_blocks('{"ethereum": 5, "arbitrum": 6}', self.CH), {"ethereum": 5, "arbitrum": 6})

    def test_string_numbers_ok(self):
        self.assertEqual(RG.parse_blocks('{"ethereum": "5", "arbitrum": "6"}', self.CH)["ethereum"], 5)

    def test_missing_chain(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": 5}', self.CH).startswith("BLOCKS_MUST_NAME_EXACTLY_"))

    def test_extra_chain(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": 5, "arbitrum": 6, "base": 7}', self.CH).startswith("BLOCKS_MUST"))

    def test_zero_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": 0, "arbitrum": 6}', self.CH).startswith("BAD_BLOCK_NUMBER"))

    def test_negative_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": -1, "arbitrum": 6}', self.CH).startswith("BAD_BLOCK"))

    def test_huge_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": 10000000000001, "arbitrum": 6}', self.CH).startswith("BAD_BLOCK"))

    def test_float_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": 1.5, "arbitrum": 6}', self.CH).startswith("BAD_BLOCK"))

    def test_bool_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": true, "arbitrum": 6}', self.CH).startswith("BAD_BLOCK"))

    def test_hex_string_block(self):
        self.assertTrue(RG.parse_blocks('{"ethereum": "0x10", "arbitrum": 6}', self.CH).startswith("BAD_BLOCK"))

    def test_not_json(self):
        self.assertEqual(RG.parse_blocks("{eth", self.CH), "BLOCKS_NOT_JSON")

    def test_not_object(self):
        self.assertEqual(RG.parse_blocks("[1,2]", self.CH), "BLOCKS_NOT_AN_OBJECT")


class Labels(unittest.TestCase):
    def test_strips_markup(self):
        self.assertEqual(RG.clean_label('<script>"x"</script>'), "scriptx/script")

    def test_truncates(self):
        self.assertEqual(len(RG.clean_label("a" * 200)), RG.MAX_LABEL)

    def test_collapses_space_and_controls(self):
        self.assertEqual(RG.clean_label("a​  b\n\tc"), "a bc")


class Gate(unittest.TestCase):
    def latest(self, **k):
        d = {"found": True, "pair": True, "check_id": 7, "verdict": "BACKED", "status": "FINAL",
             "source_time": 1000, "ratio_bps": 10010}
        d.update(k)
        return d

    def test_backed_fresh(self):
        self.assertTrue(GT.gate_answer(self.latest(), 1500, 3600)["backed"])

    def test_age_exactly_max(self):
        self.assertTrue(GT.gate_answer(self.latest(), 4600, 3600)["backed"])

    def test_age_one_over(self):
        o = GT.gate_answer(self.latest(), 4601, 3600)
        self.assertEqual((o["backed"], o["reason"]), (False, "STALE_3601S_OVER_3600S"))

    def test_under(self):
        self.assertEqual(GT.gate_answer(self.latest(verdict="UNDER_BACKED"), 1500, 3600)["reason"], "UNDER_BACKED")

    def test_inconclusive(self):
        o = GT.gate_answer(self.latest(verdict="INCONCLUSIVE", status="INCONCLUSIVE"), 1500, 3600)
        self.assertEqual(o["reason"], "INCONCLUSIVE")

    def test_never_checked(self):
        self.assertEqual(GT.gate_answer({"found": False, "pair": True}, 1, 60)["reason"], "NEVER_CHECKED")

    def test_no_pair(self):
        self.assertEqual(GT.gate_answer({"found": False, "pair": False}, 1, 60)["reason"], "NO_SUCH_PAIR")

    def test_unreadable(self):
        self.assertEqual(GT.gate_answer(None, 1, 60)["reason"], "REGISTRY_UNREADABLE")

    def test_future(self):
        self.assertEqual(GT.gate_answer(self.latest(source_time=2000), 1500, 3600)["reason"], "RULING_FROM_THE_FUTURE")

    def test_not_final(self):
        self.assertEqual(GT.gate_answer(self.latest(status="PROVISIONAL"), 1500, 3600)["reason"], "LATEST_RULING_NOT_FINAL")

    def test_no_clock(self):
        self.assertFalse(GT.gate_answer(self.latest(), 0, 3600)["backed"])


def _sweep():
    """Tolerance sweep: for every tolerance, the exact threshold is BACKED and
    one unit below is UNDER_BACKED (supply 10^12 so every bps is integral)."""
    for tol in (0, 1, 5, 10, 25, 50, 100, 250, 500, 999, 1000):
        def ok(self, tol=tol):
            s = 10 ** 12
            edge = s * (10000 - tol) // 10000
            t = terms(tolerance_bps=tol)
            self.assertEqual(RG.compute(reading(edge, s), t, None)["verdict"], "BACKED")
            self.assertEqual(RG.compute(reading(edge - 1, s), t, None)["verdict"], "UNDER_BACKED")
        setattr(Verdict, "test_tolerance_sweep_%d_bps" % tol, ok)
    for sd, dd in ((6, 6), (6, 18), (18, 6), (8, 18), (18, 8), (0, 18), (18, 0), (36, 0), (0, 36)):
        def dec(self, sd=sd, dd=dd):
            big = max(sd, dd)
            t = terms(source_decimals=sd, dests=[{"chain": "arbitrum", "token": F.ARB_USDC, "decimals": dd}])
            one_s, one_d = 10 ** sd, 10 ** dd
            self.assertEqual(RG.compute(reading(5 * one_s, 5 * one_d, sdec=sd, ddec=dd), t, None)["verdict"], "BACKED")
            if big > 0 and sd >= dd:
                self.assertEqual(RG.compute(reading(5 * one_s - 1, 5 * one_d, sdec=sd, ddec=dd), t, None)["verdict"],
                                 "UNDER_BACKED")
        setattr(Verdict, "test_decimals_%d_vs_%d" % (sd, dd), dec)
    for gap in (0, 1, 299, 300, 301, 599, 600, 601, 3600):
        def g(self, gap=gap):
            o = RG.compute(reading(1, 1, sts=10000, dts=10000 - gap), terms(), None)
            self.assertEqual(o["verdict"] == "BACKED", gap <= 600)
            o = RG.compute(reading(1, 1, sts=10000, dts=10000 - gap), terms(max_gap_s=300), None)
            self.assertEqual(o["verdict"] == "BACKED", gap <= 300)
        setattr(Pins, "test_gap_sweep_%ds" % gap, g)


_sweep()

if __name__ == "__main__":
    unittest.main()
