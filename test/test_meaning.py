"""What CollateralGate's answer MEANS. `backed` is true only for a fresh FINAL
BACKED ruling of exactly the pair and tokens asked about, with complete
coverage, no recent other ruling and a tolerance within the gate's limit.
Every other combination - missing, pending, stale, partial or someone
else's data - is never favorable. Copycats (the same tokens under another
pair id, look-alike tokens, another chain) are never read for the caller."""
import itertools
import unittest

import fixtures as F
from fixtures import GT, STRANGER

SRC, CHAIN, DST = F.USDC, "arbitrum", F.ARB_USDC
NOW = 100_000
MAX_AGE = 3600
MAX_TOL = 50

VERDICTS = [("BACKED", "FINAL"), ("UNDER_BACKED", "FINAL"), ("INCONCLUSIVE", "INCONCLUSIVE"), ("BACKED", "PROVISIONAL"),
            ("BACKED", "INCONCLUSIVE"), ("", "")]
AGES = [("fresh", NOW - 100), ("edge", NOW - MAX_AGE), ("stale", NOW - MAX_AGE - 1), ("future", NOW + 5), ("zero", 0)]
COVERAGE = ["COMPLETE", "GAP", "UNREAD", "OPEN", "", None]
ALERTS = ["OK", "ALERT", "BREACH", "", None]
BAD = [("none", 0), ("recent", NOW - 10), ("old", NOW - MAX_AGE - 1)]
TOLS = [0, MAX_TOL, MAX_TOL + 1]
BOUND = [("same", (SRC, CHAIN, DST)), ("other_source", (F.DAI, CHAIN, DST)), ("other_chain", (SRC, "optimism", DST)),
         ("lookalike_token", (SRC, CHAIN, F.addr(0xbad))), ("junk", ("x", CHAIN, "")),
         ("upper_case", (SRC.upper().replace("0X", "0x"), CHAIN, DST.upper().replace("0X", "0x")))]


def latest(verdict, status, st, cov, alert, bad, tol):
    d = {"found": verdict != "", "pair": True, "check_id": 3, "verdict": verdict, "status": status, "source_time": st,
         "ratio_bps": 10100, "tolerance_bps": tol, "last_bad_time": bad, "source_token": SRC,
         "dests": [{"chain": CHAIN, "token": DST}], "open_check": 0, "unlisted": []}
    if cov is not None:
        d["coverage"] = cov
    if alert is not None:
        d["alert"] = alert
    return d


def favorable_expected(verdict, status, age, cov, alert, bad, tol, bound):
    return (verdict == "BACKED" and status == "FINAL" and age in ("fresh", "edge") and cov == "COMPLETE"
            and alert in ("OK", "ALERT") and bad != "recent" and tol <= MAX_TOL and bound in ("same", "upper_case"))


class Matrix(unittest.TestCase):
    pass


def _build():
    n = 0
    for (verdict, status), cov, alert in itertools.product(VERDICTS, COVERAGE, ALERTS):
        def t(self, verdict=verdict, status=status, cov=cov, alert=alert):
            for (age, st), (bad, bt), tol, (bound, b) in itertools.product(AGES, BAD, TOLS, BOUND):
                out = GT.gate_answer(latest(verdict, status, st, cov, alert, bt, tol), NOW, MAX_AGE, MAX_TOL, *b)
                want = favorable_expected(verdict, status, age, cov, alert, bad, tol, bound)
                self.assertEqual(out["backed"], want, (verdict, status, age, cov, alert, bad, tol, bound, out))
                self.assertIn(out["state"], GT.STATES)
                self.assertEqual(out["backed"], out["state"] in GT.FAVORABLE)
                if bound not in ("same", "upper_case"):
                    self.assertEqual(out["state"], "NOT_THIS_PAIR")
        name = "test_%s_%s_cov_%s_alert_%s" % (verdict or "none", status or "none", cov, alert)
        setattr(Matrix, name, t)
        n += 1
    return n


_build()


class States(unittest.TestCase):
    def ask(self, **k):
        d = latest("BACKED", "FINAL", NOW - 100, "COMPLETE", "OK", 0, 0)
        d.update(k)
        return GT.gate_answer(d, NOW, MAX_AGE, MAX_TOL, SRC, CHAIN, DST)

    def test_backed(self):
        self.assertEqual(self.ask()["state"], "BACKED")

    def test_backed_alert_is_favorable_and_says_so(self):
        o = self.ask(alert="ALERT")
        self.assertEqual((o["state"], o["backed"]), ("BACKED_ALERT", True))

    def test_each_coverage_state_has_its_own_name(self):
        self.assertEqual(self.ask(coverage="GAP")["state"], "COVERAGE_GAP")
        self.assertEqual(self.ask(coverage="OPEN")["state"], "COVERAGE_OPEN")
        self.assertEqual(self.ask(coverage="UNREAD")["state"], "COVERAGE_UNREAD")
        self.assertEqual(self.ask(coverage="")["state"], "COVERAGE_UNREAD")

    def test_pending_vs_never(self):
        self.assertEqual(self.ask(found=False, open_check=4)["state"], "PENDING")
        self.assertEqual(self.ask(found=False, open_check=0)["state"], "NEVER_CHECKED")

    def test_order_under_before_stale(self):
        self.assertEqual(self.ask(verdict="UNDER_BACKED", source_time=1)["state"], "UNDER_BACKED")

    def test_missing_fields_are_not_favorable(self):
        for k in ("source_token", "dests", "status", "verdict", "source_time", "coverage", "alert"):
            d = latest("BACKED", "FINAL", NOW - 100, "COMPLETE", "OK", 0, 0)
            del d[k]
            self.assertFalse(GT.gate_answer(d, NOW, MAX_AGE, MAX_TOL, SRC, CHAIN, DST)["backed"], k)

    def test_junk_field_types_are_not_favorable(self):
        for k, v in (("dests", "x"), ("dests", [1]), ("source_time", "abc"), ("tolerance_bps", "x"), ("last_bad_time", None)):
            d = latest("BACKED", "FINAL", NOW - 100, "COMPLETE", "OK", 0, 0)
            d[k] = v
            o = GT.gate_answer(d, NOW, MAX_AGE, MAX_TOL, SRC, CHAIN, DST)
            if k in ("tolerance_bps", "last_bad_time"):
                continue           # junk there reads as 0, which is the value the registry would report
            self.assertFalse(o["backed"], (k, v))


class Copycats(unittest.TestCase):
    """On the wired deployment: a copycat pair with the same tokens and a lax
    tolerance, and a pair of another token, are never read for the caller."""

    def setUp(self):
        self.s = F.Setup("DEMO")

    def final(self, pid):
        self.s.after_bond(1200)
        cid = self.s.monitor(pid, self.s.blocks(pid))["check_id"]
        self.s.read(cid)
        self.s.rule(cid)
        if self.s.check(cid)["status"] == "PROVISIONAL":
            self.s.finalize_after_window(cid)

    def test_copycat_with_lax_tolerance(self):
        real = self.s.pair("arb_usdc", tol=0)
        copy = self.s.pair("arb_usdc", tol=1000)
        self.s.net.balance("ethereum", F.USDC, F.ARB_GW, 950_000 * 10 ** 6)     # 95%: BACKED only within 10% tolerance
        self.final(real)
        self.final(copy)
        st = (F.USDC, "arbitrum", F.ARB_USDC)
        now = self.s.w.now()
        a = self.s.view(self.s.gate, "is_backed", real, *st, now)
        b = self.s.view(self.s.gate, "is_backed", copy, *st, now)
        self.assertEqual((a["state"], b["state"]), ("UNDER_BACKED", "TOLERANCE_TOO_WIDE"))

    def test_pair_id_of_another_token(self):
        usdc = self.s.pair("arb_usdc")
        wbtc = self.s.pair("arb_wbtc")
        self.final(wbtc)
        now = self.s.w.now()
        o = self.s.view(self.s.gate, "is_backed", wbtc, F.USDC, "arbitrum", F.ARB_USDC, now)
        self.assertEqual(o["state"], "NOT_THIS_PAIR")
        self.assertEqual(self.s.view(self.s.gate, "is_backed", usdc, F.USDC, "arbitrum", F.ARB_USDC, now)["state"],
                         "NEVER_CHECKED")

    def test_lookalike_destination(self):
        pid = self.s.pair("arb_usdc")
        self.final(pid)
        o = self.s.view(self.s.gate, "is_backed", pid, F.USDC, "arbitrum", F.addr(0x1001 + 99), self.s.w.now())
        self.assertEqual((o["state"], o["backed"]), ("NOT_THIS_PAIR", False))

    def test_same_token_on_another_chain(self):
        pid = self.s.pair("arb_usdc")
        self.final(pid)
        o = self.s.view(self.s.gate, "is_backed", pid, F.USDC, "optimism", F.ARB_USDC, self.s.w.now())
        self.assertEqual(o["state"], "NOT_THIS_PAIR")

    def test_borrow_with_copycat_tokens_is_refused_and_recorded(self):
        pid = self.s.pair("arb_usdc")
        self.final(pid)
        out = self.s.call(self.s.gate, "borrow", pid, F.USDC, "arbitrum", F.OP_FAKE, "1000", "copycat", sender=STRANGER)
        self.assertEqual((out["allowed"], out["state"]), (False, "NOT_THIS_PAIR"))
        a = self.s.view(self.s.gate, "get_attempts", 0, 5)
        self.assertEqual((a["refused"], a["attempts"][0]["dest_token"]), (1, F.OP_FAKE))

    def test_borrow_bound_and_backed(self):
        pid = self.s.pair("arb_usdc")
        self.s.net.balance("ethereum", F.USDC, F.ARB_GW, 1_100_000 * 10 ** 6)
        self.final(pid)
        out = self.s.borrow(pid)
        self.assertEqual((out["allowed"], out["state"]), (True, "BACKED"))

    def test_open_coverage_pair_never_favorable(self):
        pid = self.s.pair("op_usdc")
        self.final(pid)
        self.assertEqual(self.s.gate_ask(pid)["state"], "COVERAGE_OPEN")


if __name__ == "__main__":
    unittest.main()
