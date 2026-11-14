# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import hashlib
import json
import typing

# CollateralGate - a consumer of BackedByRegistry: would a lending market
# accept this bridged token as collateral right now?
#
# Every question is bound to ONE pair and the exact tokens the caller means:
# is_backed(pair_id, source_token, dest_chain, dest_token, now) answers
# NOT_THIS_PAIR unless that pair's source token is `source_token` and it lists
# (dest_chain, dest_token) as a destination. Anyone can register a pair, so a
# copycat (the same tokens under another tolerance, or a look-alike token)
# is a different pair id that the caller did not name, and is never read.
#
# States (backed is true only for BACKED and BACKED_ALERT):
#   BACKED              latest ruling FINAL BACKED, fresh, coverage COMPLETE
#   BACKED_ALERT        the same, but within the registry's alert margin of the tolerance line
#   UNDER_BACKED        latest ruling FINAL UNDER_BACKED
#   INCONCLUSIVE        latest ruling INCONCLUSIVE (the pair's data could not be ruled on)
#   RECENT_NOT_BACKED   a ruling inside max_age said something other than BACKED
#   STALE               the latest ruling's pinned Ethereum block is older than max_age
#   PENDING             never ruled, but a check is open
#   NEVER_CHECKED       never ruled, nothing open
#   COVERAGE_GAP        a vault backs a destination the pair does not list
#   COVERAGE_UNREAD     a vault's coverage scan could not be read at the pinned block
#   COVERAGE_OPEN       a vault whose bridge cannot be enumerated on chain
#   TOLERANCE_TOO_WIDE  the pair's frozen tolerance is above max_tolerance_bps
#   NOT_THIS_PAIR / NO_SUCH_PAIR / REGISTRY_UNREADABLE / NO_CLOCK / RULING_FROM_THE_FUTURE
# Never favorable on missing, pending or stale data. borrow() asks it and
# records the answer either way. No value is held or moved. No owner, no setter.

VERSION = "2.0.0"
MAX_PAGE = 50
MAX_NOTE = 80
FAVORABLE = ("BACKED", "BACKED_ALERT")
STATES = ("BACKED", "BACKED_ALERT", "UNDER_BACKED", "INCONCLUSIVE", "RECENT_NOT_BACKED", "STALE", "PENDING",
          "NEVER_CHECKED", "COVERAGE_GAP", "COVERAGE_UNREAD", "COVERAGE_OPEN", "TOLERANCE_TOO_WIDE", "NOT_THIS_PAIR",
          "NO_SUCH_PAIR", "REGISTRY_UNREADABLE", "NO_CLOCK", "RULING_FROM_THE_FUTURE", "BAD_AMOUNT")

# INLINE:common


def bound_to(latest: typing.Any, source_token: str, dest_chain: str, dest_token: str) -> bool:
    """True only if the registry's pair is exactly the caller's tokens."""
    if not isinstance(latest, dict):
        return False
    st = _addr(source_token)
    dt = _addr(dest_token)
    if st == "" or dt == "" or _addr(latest.get("source_token", "")) != st:
        return False
    dests = latest.get("dests")
    if not isinstance(dests, list):
        return False
    for d in dests:
        if isinstance(d, dict) and d.get("chain") == str(dest_chain) and _addr(d.get("token", "")) == dt:
            return True
    return False


def gate_answer(latest: typing.Any, now: int, max_age: int, max_tol: int, source_token: str, dest_chain: str,
                dest_token: str) -> dict:
    """The whole rule, pure. latest: BackedByRegistry.get_latest(pair)."""
    out = {"backed": False, "state": "", "check_id": 0, "verdict": "", "source_time": 0, "age_s": 0,
           "ratio_bps": -1, "alert": "", "coverage": "", "unlisted": 0, "por": ""}

    def done(state: str) -> dict:
        out["state"] = state
        out["backed"] = state in FAVORABLE
        out["reason"] = state
        return out
    if not isinstance(latest, dict):
        return done("REGISTRY_UNREADABLE")
    if latest.get("pair") is not True:
        return done("NO_SUCH_PAIR")
    if not bound_to(latest, source_token, dest_chain, dest_token):
        return done("NOT_THIS_PAIR")
    if now <= 0:
        return done("NO_CLOCK")
    if latest.get("found") is not True:
        return done("PENDING" if _as_int(latest.get("open_check", 0), 0) > 0 else "NEVER_CHECKED")
    v = str(latest.get("verdict", ""))
    st = _as_int(latest.get("source_time", 0), 0)
    out["check_id"] = _as_int(latest.get("check_id", 0), 0)
    out["verdict"] = v
    out["source_time"] = st
    out["age_s"] = now - st
    out["ratio_bps"] = latest.get("ratio_bps", -1)
    out["alert"] = str(latest.get("alert", ""))
    out["coverage"] = str(latest.get("coverage", ""))
    out["unlisted"] = len(latest.get("unlisted") or [])
    out["por"] = str(latest.get("por", ""))
    if v == "UNDER_BACKED":
        return done("UNDER_BACKED")
    if v != "BACKED" or latest.get("status") != "FINAL":
        return done("INCONCLUSIVE")
    if st <= 0 or now - st > max_age:
        return done("STALE")
    if now - st < 0:
        return done("RULING_FROM_THE_FUTURE")
    bad = _as_int(latest.get("last_bad_time", 0), 0)
    if bad > 0 and now - bad <= max_age:
        return done("RECENT_NOT_BACKED")
    if _as_int(latest.get("tolerance_bps", 0), 0) > max_tol:
        return done("TOLERANCE_TOO_WIDE")
    cov = out["coverage"]
    if cov != "COMPLETE":
        return done("COVERAGE_GAP" if cov == "GAP" else ("COVERAGE_OPEN" if cov == "OPEN" else "COVERAGE_UNREAD"))
    if out["alert"] == "ALERT":
        return done("BACKED_ALERT")
    if out["alert"] != "OK":
        return done("INCONCLUSIVE")
    return done("BACKED")


@gl.storage.allow
@dataclass
class Attempt:
    attempt_id: u64
    sender: str
    pair_id: u64
    amount: str
    allowed: bool
    reason: str
    check_id: u64
    at: u64
    note: str
    dest_chain: str
    dest_token: str


class CollateralGate(gl.contract.Contract):
    registry: Address
    max_age_s: u64
    max_tolerance_bps: u64
    n: u64
    allowed_n: u64
    refused_n: u64
    attempts: gl.storage.TreeMap[u64, Attempt]

    def __init__(self, registry: str, max_age_s: int, max_tolerance_bps: int) -> None:
        r = _addr(registry)
        if r == "":
            raise gl.vm.UserError("registry must be a 0x address")
        m = _as_int(max_age_s, -1)
        if m < 60 or m > 30 * 86400:
            raise gl.vm.UserError("max_age_s must be 60..2592000")
        t = _as_int(max_tolerance_bps, -1)
        if t < 0 or t > 1000:
            raise gl.vm.UserError("max_tolerance_bps must be 0..1000")
        self.registry = Address(r)
        self.max_age_s = u64(m)
        self.max_tolerance_bps = u64(t)
        self.n = u64(0)
        self.allowed_n = u64(0)
        self.refused_n = u64(0)

    def _latest(self, pair_id: int) -> typing.Any:
        try:
            raw = gl.contract.get_at(self.registry).view().get_latest(pair_id)
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None

    @gl.public.view
    def is_backed(self, pair_id: int, source_token: str, dest_chain: str, dest_token: str, now: int) -> typing.Any:
        """Bound to (pair, its source token, one of its destinations). `now`:
        the caller's clock (views have none); borrow() uses the transaction's."""
        pid = max(_as_int(pair_id, 0), 0)
        out = gate_answer(self._latest(pid), _as_int(now, 0), int(self.max_age_s), int(self.max_tolerance_bps),
                          source_token, dest_chain, dest_token)
        out["pair_id"] = pid
        out["max_age_s"] = int(self.max_age_s)
        out["max_tolerance_bps"] = int(self.max_tolerance_bps)
        return out

    @gl.public.write
    def borrow(self, pair_id: int, source_token: str, dest_chain: str, dest_token: str, amount: str,
               note: str) -> typing.Any:
        """Demo: borrow against the bridged token. Allowed only if is_backed
        for exactly this pair and these tokens. Recorded either way; nothing is lent."""
        now = _epoch_from_iso(gl.message.raw.get("datetime", ""))
        pid = max(_as_int(pair_id, 0), 0)
        ans = gate_answer(self._latest(pid), now, int(self.max_age_s), int(self.max_tolerance_bps), source_token,
                          dest_chain, dest_token)
        amt = _as_int(amount, -1)
        if amt <= 0 or amt > 10 ** 30:
            ans = {"backed": False, "state": "BAD_AMOUNT", "reason": "BAD_AMOUNT", "check_id": 0}
        allowed = bool(ans["backed"])
        # --- writes
        aid = int(self.n) + 1
        clean = ""
        for ch in str(note):
            if " " <= ch <= "~" and ch not in "<>\"'`\\":
                clean += ch
        self.attempts[u64(aid)] = Attempt(attempt_id=u64(aid), sender=gl.message.sender_address.as_hex.lower(),
                                          pair_id=u64(pid), amount=str(max(amt, 0)), allowed=allowed,
                                          reason=str(ans["state"]), check_id=u64(int(ans.get("check_id", 0))),
                                          at=u64(max(now, 0)), note=" ".join(clean.split())[:MAX_NOTE],
                                          dest_chain=str(dest_chain)[:16], dest_token=_addr(dest_token))
        self.n = u64(aid)
        if allowed:
            self.allowed_n = u64(int(self.allowed_n) + 1)
        else:
            self.refused_n = u64(int(self.refused_n) + 1)
        return {"attempt_id": aid, "allowed": allowed, "state": ans["state"], "reason": ans["state"]}

    @gl.public.view
    def get_attempts(self, offset: int, limit: int) -> typing.Any:
        out = []
        i = int(self.n) - max(_as_int(offset, 0), 0)
        lim = min(max(_as_int(limit, 20), 0), MAX_PAGE)
        while i >= 1 and len(out) < lim:
            a = self.attempts.get(u64(i))
            if a is not None:
                out.append({"attempt_id": int(a.attempt_id), "sender": a.sender, "pair_id": int(a.pair_id),
                            "amount": a.amount, "allowed": bool(a.allowed), "reason": a.reason,
                            "check_id": int(a.check_id), "at": int(a.at), "note": a.note,
                            "dest_chain": a.dest_chain, "dest_token": a.dest_token})
            i -= 1
        return {"total": int(self.n), "allowed": int(self.allowed_n), "refused": int(self.refused_n), "attempts": out}

    @gl.public.view
    def get_config(self) -> typing.Any:
        return {"version": VERSION, "contract": "CollateralGate", "registry": self.registry.as_hex.lower(),
                "max_age_s": int(self.max_age_s), "max_tolerance_bps": int(self.max_tolerance_bps),
                "states": list(STATES), "favorable": list(FAVORABLE)}
