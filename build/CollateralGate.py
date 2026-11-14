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

# ==== shared helpers: generated from contracts/shared/common.py by tools/inline_shared.py; edit there ====
# The runner rejects the str replace method; slice around find() instead.

# chain -> (chain id, (RPC A, RPC B)). Every node reads BOTH RPCs of a chain
# and refuses unless they answer identically. The two are run by different
# operators, and both serve archive state, JSON-RPC batches and the
# "finalized" tag (docs/FEASIBILITY.md).
CHAINS = {
    "ethereum": (1, ("https://eth-pokt.nodies.app", "https://rpc.mevblocker.io")),
    "arbitrum": (42161, ("https://arb-pokt.nodies.app", "https://arbitrum-one.public.blastapi.io")),
    "optimism": (10, ("https://mainnet.optimism.io", "https://op-pokt.nodies.app")),
    "base": (8453, ("https://base-pokt.nodies.app", "https://base.drpc.org")),
    "polygon": (137, ("https://polygon.drpc.org", "https://rpc-mainnet.matic.quiknode.pro")),
    "moonbeam": (1284, ("https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public")),
    "mantle": (5000, ("https://rpc.mantle.xyz", "https://mantle.drpc.org")),
    "xlayer": (196, ("https://xlayerrpc.okx.com", "https://xlayer.drpc.org")),
    "sei": (1329, ("https://evm-rpc.sei-apis.com", "https://sei.api.pocket.network")),
    "flare": (14, ("https://rpc.ankr.com/flare", "https://flare.public-rpc.com")),
    "hedera": (295, ("https://mainnet.hashio.io/api", "https://hedera.linkpool.pro")),
    "unichain": (130, ("https://mainnet.unichain.org", "https://unichain.drpc.org")),
    "morph": (2818, ("https://rpc.morphl2.io", "https://rpc-quicknode.morphl2.io")),
    "ink": (57073, ("https://rpc-gel.inkonchain.com", "https://rpc-qnd.inkonchain.com")),
    "berachain": (80094, ("https://rpc.berachain.com", "https://berachain-rpc.publicnode.com")),
    "hyperevm": (999, ("https://rpc.hyperliquid.xyz/evm", "https://hyperliquid-json-rpc.stakely.io")),
    "monad": (143, ("https://rpc.monad.xyz", "https://monad-mainnet-rpc.spidernode.net")),
}
# Largest JSON-RPC batch each endpoint accepts (measured: dRPC's free tier
# refuses a batch of more than 3).
RPC_BATCH = {"https://base.drpc.org": 3, "https://polygon.drpc.org": 3, "https://moonbeam.drpc.org": 3,
             "https://mantle.drpc.org": 3, "https://xlayer.drpc.org": 3, "https://unichain.drpc.org": 3}
RPC_TRIES = 4
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
