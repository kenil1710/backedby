# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import json
import typing

# CollateralGate - a consumer of BackedByRegistry: would a lending market
# accept this bridged token as collateral right now?
#
# is_backed(pair, now) is true only if the pair's latest ruling is FINAL and
# BACKED, and its pinned Ethereum block is no older than max_age_s. The demo
# borrow() asks it and records the answer either way: it refuses
# UNDER_BACKED, INCONCLUSIVE, stale, and never-checked pairs, with the reason.
# No value is held or moved. No owner, no setter.

VERSION = "1.0.0"
MAX_PAGE = 50
MAX_NOTE = 80

# INLINE:common


def gate_answer(latest: typing.Any, now: int, max_age: int) -> dict:
    """The whole rule, pure. latest: BackedByRegistry.get_latest(pair)."""
    if not isinstance(latest, dict):
        return {"backed": False, "reason": "REGISTRY_UNREADABLE"}
    if latest.get("pair") is not True:
        return {"backed": False, "reason": "NO_SUCH_PAIR"}
    if latest.get("found") is not True:
        return {"backed": False, "reason": "NEVER_CHECKED"}
    v = str(latest.get("verdict", ""))
    out = {"backed": False, "reason": "", "check_id": int(latest.get("check_id", 0)), "verdict": v,
           "source_time": int(latest.get("source_time", 0)), "age_s": now - int(latest.get("source_time", 0)),
           "ratio_bps": latest.get("ratio_bps", -1)}
    if latest.get("status") != "FINAL" and v != "INCONCLUSIVE":
        out["reason"] = "LATEST_RULING_NOT_FINAL"
        return out
    if v == "UNDER_BACKED":
        out["reason"] = "UNDER_BACKED"
        return out
    if v != "BACKED":
        out["reason"] = "INCONCLUSIVE"
        return out
    if now <= 0 or out["age_s"] > max_age:
        out["reason"] = "STALE_" + str(out["age_s"]) + "S_OVER_" + str(max_age) + "S"
        return out
    if out["age_s"] < 0:
        out["reason"] = "RULING_FROM_THE_FUTURE"
        return out
    out["backed"] = True
    out["reason"] = "BACKED"
    return out


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


class CollateralGate(gl.contract.Contract):
    registry: Address
    max_age_s: u64
    n: u64
    allowed_n: u64
    refused_n: u64
    attempts: gl.storage.TreeMap[u64, Attempt]

    def __init__(self, registry: str, max_age_s: int) -> None:
        r = _addr(registry)
        if r == "":
            raise gl.vm.UserError("registry must be a 0x address")
        m = _as_int(max_age_s, -1)
        if m < 60 or m > 30 * 86400:
            raise gl.vm.UserError("max_age_s must be 60..2592000")
        self.registry = Address(r)
        self.max_age_s = u64(m)
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
    def is_backed(self, pair_id: int, now: int) -> typing.Any:
        """`now`: the caller's clock (views have none). borrow() uses the transaction's."""
        out = gate_answer(self._latest(max(_as_int(pair_id, 0), 0)), _as_int(now, 0), int(self.max_age_s))
        out["max_age_s"] = int(self.max_age_s)
        return out

    @gl.public.write
    def borrow(self, pair_id: int, amount: str, note: str) -> typing.Any:
        """Demo: borrow against the bridged token. Allowed only if is_backed.
        Recorded either way; nothing is lent."""
        now = _epoch_from_iso(gl.message.raw.get("datetime", ""))
        pid = max(_as_int(pair_id, 0), 0)
        ans = gate_answer(self._latest(pid), now, int(self.max_age_s))
        amt = _as_int(amount, -1)
        if amt <= 0 or amt > 10 ** 30:
            ans = {"backed": False, "reason": "BAD_AMOUNT", "check_id": 0}
        allowed = bool(ans["backed"])
        # --- writes
        aid = int(self.n) + 1
        clean = ""
        for ch in str(note):
            if " " <= ch <= "~" and ch not in "<>\"'`\\":
                clean += ch
        self.attempts[u64(aid)] = Attempt(attempt_id=u64(aid), sender=gl.message.sender_address.as_hex.lower(),
                                          pair_id=u64(pid), amount=str(max(amt, 0)), allowed=allowed,
                                          reason=str(ans["reason"]), check_id=u64(int(ans.get("check_id", 0))),
                                          at=u64(max(now, 0)), note=" ".join(clean.split())[:MAX_NOTE])
        self.n = u64(aid)
        if allowed:
            self.allowed_n = u64(int(self.allowed_n) + 1)
        else:
            self.refused_n = u64(int(self.refused_n) + 1)
        return {"attempt_id": aid, "allowed": allowed, "reason": ans["reason"]}

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
                            "check_id": int(a.check_id), "at": int(a.at), "note": a.note})
            i -= 1
        return {"total": int(self.n), "allowed": int(self.allowed_n), "refused": int(self.refused_n), "attempts": out}

    @gl.public.view
    def get_config(self) -> typing.Any:
        return {"version": VERSION, "contract": "CollateralGate", "registry": self.registry.as_hex.lower(),
                "max_age_s": int(self.max_age_s)}
