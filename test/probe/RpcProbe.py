# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
import hashlib
import json
import typing

# Throwaway diagnostics (never part of BackedBy): what each allowlisted RPC
# answers from GenVM, a few times in a row. Validators always agree.

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
    "base": (8453, ("https://base-pokt.nodies.app", "https://base.drpc.org")),
    "polygon": (137, ("https://polygon.drpc.org", "https://polygon.gateway.tenderly.co")),
    "moonbeam": (1284, ("https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public")),
}
# Largest JSON-RPC batch each endpoint accepts (measured: dRPC's free tier
# refuses a batch of more than 3).
RPC_BATCH = {"https://optimism.drpc.org": 3, "https://base.drpc.org": 3, "https://polygon.drpc.org": 3,
             "https://moonbeam.drpc.org": 3}
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


EXTRA = []


def _one(url: str) -> str:
    body = json.dumps([{"jsonrpc": "2.0", "id": 0, "method": "eth_getBlockByNumber", "params": ["finalized", False]},
                       {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}])
    try:
        res = gl.nondet.web.request(url, method="POST", body=body, headers={"Content-Type": "application/json"})
    except Exception as e:
        return "EXC:" + str(e)[:60]
    st = getattr(res, "status_code", None) or getattr(res, "status", None)
    b = getattr(res, "body", b"") or b""
    t = b.decode("utf-8", errors="replace") if isinstance(b, bytes) else str(b)
    return str(st) + ":" + t[:50]


class RpcProbe(gl.contract.Contract):
    last: str

    def __init__(self) -> None:
        self.last = ""

    @gl.public.write
    def probe(self, rounds: int) -> typing.Any:
        urls = []
        for ch in CHAINS:
            for u in CHAINS[ch][1]:
                urls.append(u)
        for u in EXTRA:
            urls.append(u)
        n = int(rounds)

        def leader() -> typing.Any:
            out = {}
            for u in urls:
                out[u] = [_one(u) for _ in range(n)]
            return out

        def validator(res: gl.vm.Result) -> bool:
            return True

        r = gl.vm.run_nondet(leader, validator)
        self.last = json.dumps(r)
        return r

    @gl.public.view
    def get_last(self) -> str:
        return self.last
