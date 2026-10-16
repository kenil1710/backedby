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

# ==== shared helpers: generated from contracts/shared/common.py by tools/inline_shared.py; edit there ====
# The runner rejects the str replace method; slice around find() instead.

# chain -> (chain id, (RPC A, RPC B)). Every node reads BOTH RPCs of a chain
# and refuses unless they answer identically. The two are run by different
# operators, and both serve archive state, JSON-RPC batches and the
# "finalized" tag (docs/FEASIBILITY.md).
CHAINS = {
    "ethereum": (1, ("https://eth-pokt.nodies.app", "https://rpc.mevblocker.io")),
    "arbitrum": (42161, ("https://arb-pokt.nodies.app", "https://arbitrum.gateway.tenderly.co")),
    "optimism": (10, ("https://mainnet.optimism.io", "https://optimism.drpc.org")),
    "base": (8453, ("https://mainnet.base.org", "https://base.drpc.org")),
    "polygon": (137, ("https://polygon.drpc.org", "https://polygon.gateway.tenderly.co")),
    "moonbeam": (1284, ("https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public")),
}
# Largest JSON-RPC batch each endpoint accepts (measured: dRPC's free tier
# refuses a batch of more than 3).
RPC_BATCH = {"https://optimism.drpc.org": 3, "https://base.drpc.org": 3, "https://polygon.drpc.org": 3,
             "https://moonbeam.drpc.org": 3}
RPC_TRIES = 3
LEADER_LAG_S = 1800       # a leader-named block may be this much older than a validator's own finalized block
ZERO = "0x" + "0" * 40


def _as_int(v: typing.Any, default: int = -1) -> int:
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        t = v.strip()
        if t != "" and t.isdigit() and len(t) <= 78:
            return int(t)
    return default


def _is_hex(s: typing.Any, n: int = -1) -> bool:
    if not isinstance(s, str) or (n >= 0 and len(s) != n):
        return False
    for ch in s:
        if ch not in "0123456789abcdef":
            return False
    return True


def _addr(v: typing.Any) -> str:
    """A lowercase 0x address, or "" if v is not one."""
    t = str(v).strip().lower()
    if len(t) != 42 or not t.startswith("0x"):
        return ""
    return t if _is_hex(t[2:], 40) else ""


def _hash32(v: typing.Any) -> str:
    t = str(v).strip().lower()
    if len(t) != 66 or not t.startswith("0x") or not _is_hex(t[2:], 64):
        return ""
    return t


def _sha(text: typing.Any) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _canon(obj: typing.Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _days_from_civil(y: int, m: int, d: int) -> int:
    y -= 1 if m <= 2 else 0
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z: int) -> tuple:
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + (1 if m <= 2 else 0), m, d)


def _epoch_from_iso(value: typing.Any) -> int:
    """Seconds since the epoch from gl.message.raw["datetime"]
    ("2026-10-07T12:00:00Z"), identical on every validator."""
    if not isinstance(value, str) or len(value) < 19:
        return 0
    try:
        year = int(value[0:4])
        month = int(value[5:7])
        day = int(value[8:10])
        hour = int(value[11:13])
        minute = int(value[14:16])
        second = int(value[17:19])
    except Exception:
        return 0
    if month < 1 or month > 12 or day < 1 or day > 31 or hour > 23 or minute > 59 or second > 60:
        return 0
    return _days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second


def _two(n: int) -> str:
    return ("0" + str(n))[-2:]


def iso_date(epoch: int) -> str:
    y, m, d = _civil_from_days(int(epoch) // 86400)
    return str(y) + "-" + _two(m) + "-" + _two(d)


def iso_minute(epoch: int) -> str:
    s = int(epoch) % 86400
    return iso_date(epoch) + " " + _two(s // 3600) + ":" + _two((s % 3600) // 60) + " UTC"
# ==== end shared ====


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
