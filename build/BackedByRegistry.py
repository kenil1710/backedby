# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import hashlib
import json
import typing

# BackedByRegistry - is a bridged token actually backed?
#
# A PAIR is one bridge vault on Ethereum holding a source token, and the
# 1..n destination tokens that bridge minted against it. A pair exists only
# if ChainReader proved it from the bridge's own on-chain mapping, and anyone
# can add a missing destination with the same proof.
#
# A CHECK pins one finalized block per chain. ChainReader reads the vault's
# balance and every destination's supply there, from two RPCs per chain.
# This contract then decides, in code and nothing else:
#   - source block timestamp >= every destination block timestamp,
#     and source - oldest destination <= the pair's max gap (600 s; 300 s Polygon);
#   - decimals as frozen at registration;
#   - normalized locked >= normalized supply * (1 - tolerance_bps / 10000)
#     -> BACKED, else UNDER_BACKED. Anything unreadable -> INCONCLUSIVE.
# No model is ever asked anything.
#
# BONDS: an operator bonds "this pair stays BACKED" for every block from the
# bond's start until it asks to unbond. Anyone may challenge with a stake at
# blocks inside that span. Final UNDER_BACKED: the bond is slashed, the
# challenger gets the stake back plus half the slash, the treasury the other
# half. Final BACKED: the stake goes into the operator's bond. INCONCLUSIVE:
# the stake is refunded.
#
# RULINGS: OPEN -> PROVISIONAL (contestable for the window) -> FINAL. A contest
# re-reads the same pinned blocks; the same verdict makes it FINAL, a different
# one INCONCLUSIVE. Every state has a deadline and a permissionless exit
# (rule / finalize / expire), so every check reaches FINAL or INCONCLUSIVE.
#
# RULES
#   1. Payable methods never raise: a refusal credits the value back as a
#      claimable balance and returns {"ok": false, ...}.
#   2. Every check runs before the first write; counters move only after.
#   3. Payouts are pull-only (claim), zeroed before the transfer is posted.
#   4. Ledger: received = bonds + open stakes + claimable + claimed, always.
#   5. No owner, no setter, no pause.

VERSION = "1.0.0"
SOURCE_CHAIN = "ethereum"

V_BACKED = "BACKED"
V_UNDER = "UNDER_BACKED"
V_INC = "INCONCLUSIVE"

ST_OPEN = "OPEN"
ST_PROV = "PROVISIONAL"
ST_CONT = "CONTESTED"
ST_FINAL = "FINAL"
ST_INC = "INCONCLUSIVE"

P_CHALLENGE = "CHALLENGE"
P_MONITOR = "MONITOR"

B_ACTIVE = "ACTIVE"
B_UNBONDING = "UNBONDING"
B_WITHDRAWN = "WITHDRAWN"
B_SLASHED = "SLASHED"

KINDS = {"arbitrum": "arbitrum", "optimism": "optimism", "base": "base", "op_dai": "optimism",
         "polygon": "polygon", "nomad": "moonbeam"}
DEPOSIT_KINDS = ("optimism", "base")
MAX_GAP_S = 600
KIND_MAX_GAP_S = {"polygon": 300}
MAX_TOLERANCE_BPS = 1000
BOUNTY_BPS = 5000             # share of a slash paid to the challenger; the rest to the treasury
MAX_DESTS = 8
MAX_DECIMALS = 36
MAX_LABEL = 48
MAX_AMOUNT = 10 ** 30
MAX_PAGE = 50

# the inconclusive reasons that say something about the pair itself (and so
# become its latest ruling); the rest are about the filing or the transport
DATA_REASONS = ("RPC_DISAGREE", "CALL_FAILED", "MALFORMED_ANSWER", "DECIMALS_MISMATCH", "CONTEST_DISAGREES",
                "CONTEST_REREAD_INCONCLUSIVE")

HOWS = ("WINDOW_PASSED", "CONTEST_UPHELD_RULING", "CONTEST_DISAGREES", "CONTEST_REREAD_INCONCLUSIVE",
        "TIMEOUT_UNREAD", "TIMEOUT_CONTEST_UNREAD", "SUPERSEDED", "READ_DATA", "READ_PIN", "READ_TRANSPORT")
COUNT_KEYS = ["pairs", "bonds", "bonds_withdrawn", "destinations_added", "contests", "refused_payable",
              "filed:CHALLENGE", "filed:MONITOR", "provisional:BACKED", "provisional:UNDER_BACKED",
              "status:FINAL", "status:INCONCLUSIVE", "verdict:BACKED", "verdict:UNDER_BACKED",
              "verdict:INCONCLUSIVE"] + ["how:" + h for h in HOWS]

MODES = {
    # contest window, read timeout, contest-read timeout, unbond delay, monitor interval, min stake, min bond, auth max age
    "CANONICAL": (21600, 7200, 7200, 86400, 3600, 10 ** 17, 10 ** 18, 3600),
    "DEMO": (90, 300, 300, 120, 30, 10 ** 16, 5 * 10 ** 16, 3600),
}

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


# --- pure rules (no storage, no self): tests drive these directly -------------

def reason_class(reason: str) -> str:
    """DATA (about the pair), PIN (about the filing) or TRANSPORT."""
    r = str(reason)
    for d in DATA_REASONS:
        if r == d or r.startswith(d + ":"):
            return "DATA"
    if r == "RPC_UNREADABLE":
        return "TRANSPORT"
    return "PIN"


def parse_blocks(text: typing.Any, chains: list) -> typing.Any:
    """{"ethereum": n, "<dest chain>": n, ...} with exactly `chains` -> dict, or a reason string."""
    try:
        b = json.loads(text) if isinstance(text, str) else text
    except Exception:
        return "BLOCKS_NOT_JSON"
    if not isinstance(b, dict):
        return "BLOCKS_NOT_AN_OBJECT"
    if sorted(list(b.keys())) != sorted(chains):
        return "BLOCKS_MUST_NAME_EXACTLY_" + ",".join(sorted(chains))
    out = {}
    for c in b:
        n = _as_int(b[c], -1)
        if n <= 0 or n > 10 ** 12:
            return "BAD_BLOCK_NUMBER_FOR_" + str(c)
        out[c] = n
    return out


def check_pins(blocks: dict, max_gap: int) -> str:
    """Rule 2: source at or after every destination, gap within max_gap.
    blocks: chain -> {"timestamp": ...}. "" if fine."""
    if SOURCE_CHAIN not in blocks:
        return "SOURCE_BLOCK_MISSING"
    s = int(blocks[SOURCE_CHAIN]["timestamp"])
    oldest = s
    for c in blocks:
        if c == SOURCE_CHAIN:
            continue
        t = int(blocks[c]["timestamp"])
        if t > s:
            return "SOURCE_BLOCK_OLDER_THAN_" + c.upper() + "_BLOCK"
        if t < oldest:
            oldest = t
    if s - oldest > max_gap:
        return "GAP_" + str(s - oldest) + "S_OVER_" + str(max_gap) + "S"
    return ""


def compute(reading: dict, terms: dict, cover: typing.Any) -> dict:
    """The whole decision for one reading. terms: source_decimals,
    tolerance_bps, max_gap_s, dests [{chain, token, decimals}]. cover:
    None for a monitoring check, else [since, until] (until 0 = open-ended)."""
    out = {"verdict": V_INC, "reason": "", "cls": "", "source_time": 0, "locked_norm": "", "supply_norm": "",
           "ratio_bps": -1, "scale_decimals": -1, "counted": []}
    if not isinstance(reading, dict) or reading.get("status") not in ("OK", "INCONCLUSIVE"):
        out["reason"] = "MALFORMED_ANSWER"
        out["cls"] = "DATA"
        return out
    blocks = reading.get("blocks") or {}
    if SOURCE_CHAIN in blocks:
        out["source_time"] = int(blocks[SOURCE_CHAIN]["timestamp"])
    if reading["status"] != "OK":
        out["reason"] = str(reading.get("reason", ""))
        out["cls"] = reason_class(out["reason"])
        return out
    bad = check_pins(blocks, int(terms["max_gap_s"]))
    if bad != "":
        out["reason"] = bad
        out["cls"] = "PIN"
        return out
    s = int(blocks[SOURCE_CHAIN]["timestamp"])
    if cover is not None:
        if s < int(cover[0]):
            out["reason"] = "SOURCE_BLOCK_BEFORE_THE_BOND_STARTED"
            out["cls"] = "PIN"
            return out
        if int(cover[1]) > 0 and s > int(cover[1]):
            out["reason"] = "SOURCE_BLOCK_AFTER_THE_BOND_STOPPED"
            out["cls"] = "PIN"
            return out
    dests = reading.get("dests") or []
    tdests = terms["dests"]
    if len(dests) != len(tdests):
        out["reason"] = "MALFORMED_ANSWER"
        out["cls"] = "DATA"
        return out
    sd = int(reading.get("source_decimals", -1))
    if sd != int(terms["source_decimals"]):
        out["reason"] = "DECIMALS_MISMATCH:source " + str(sd) + "!=" + str(int(terms["source_decimals"]))
        out["cls"] = "DATA"
        return out
    big = sd
    for i in range(len(dests)):
        d = dests[i]
        if d.get("chain") != tdests[i]["chain"] or _addr(d.get("token", "")) != tdests[i]["token"]:
            out["reason"] = "MALFORMED_ANSWER"
            out["cls"] = "DATA"
            return out
        if int(d.get("decimals", -1)) != int(tdests[i]["decimals"]):
            out["reason"] = "DECIMALS_MISMATCH:" + tdests[i]["token"]
            out["cls"] = "DATA"
            return out
        if int(d["decimals"]) > big:
            big = int(d["decimals"])
    locked = _as_int(reading.get("locked", ""), -1)
    if locked < 0 or big > MAX_DECIMALS:
        out["reason"] = "MALFORMED_ANSWER"
        out["cls"] = "DATA"
        return out
    locked_n = locked * (10 ** (big - sd))
    supply_n = 0
    counted = []
    for i in range(len(dests)):
        d = dests[i]
        sup = _as_int(d.get("supply", ""), -1)
        if sup < 0:
            out["reason"] = "MALFORMED_ANSWER"
            out["cls"] = "DATA"
            return out
        c = sup
        dep = str(d.get("deposits", ""))
        if dep != "":
            dv = _as_int(dep, -1)
            if dv < 0:
                out["reason"] = "MALFORMED_ANSWER"
                out["cls"] = "DATA"
                return out
            if dv < c:
                c = dv
        counted.append(str(c))
        supply_n += c * (10 ** (big - int(d["decimals"])))
    tol = int(terms["tolerance_bps"])
    backed = locked_n * 10000 >= supply_n * (10000 - tol)
    out["verdict"] = V_BACKED if backed else V_UNDER
    out["reason"] = "LOCKED_COVERS_SUPPLY" if backed else "LOCKED_BELOW_SUPPLY"
    out["cls"] = "RULING"
    out["locked_norm"] = str(locked_n)
    out["supply_norm"] = str(supply_n)
    out["ratio_bps"] = (locked_n * 10000) // supply_n if supply_n > 0 else -1
    out["scale_decimals"] = big
    out["counted"] = counted
    return out


def slash_split(bond: int) -> list:
    """[slash, bounty, treasury]: the whole bond is slashed; the bounty is
    BOUNTY_BPS of it, floored, so the parts always sum to the slash."""
    slash = max(int(bond), 0)
    bounty = (slash // 10000) * BOUNTY_BPS + ((slash % 10000) * BOUNTY_BPS) // 10000
    return [slash, bounty, slash - bounty]


def clean_label(text: typing.Any) -> str:
    out = ""
    for ch in str(text):
        if " " <= ch <= "~" and ch not in "<>\"'`\\":
            out += ch
    return " ".join(out.split())[:MAX_LABEL]


# =============================================================================
# storage
# =============================================================================

@gl.storage.allow
@dataclass
class Pair:
    pair_id: u64
    key: str
    kind: str
    source_chain: str
    vault: str
    source_token: str
    source_decimals: u64
    tolerance_bps: u64
    max_gap_s: u64
    label: str
    dests_json: str
    registered_by: str
    registered_at: u64
    open_check: u64
    latest_check: u64
    latest_time: u64
    last_monitor_at: u64
    checks_csv: str
    bonds_csv: str


@gl.storage.allow
@dataclass
class Bond:
    bond_id: u64
    pair_id: u64
    operator: str
    amount: u256
    deposited: u256
    won: u256
    slashed: u256
    since: u64
    unbond_at: u64
    status: str
    open_check: u64
    closed_at: u64


@gl.storage.allow
@dataclass
class Check:
    check_id: u64
    pair_id: u64
    purpose: str
    bond_id: u64
    filer: str
    stake: u256
    request_json: str
    filed_at: u64
    read_deadline: u64
    status: str
    round: u64
    verdict1: str
    ruling1_json: str
    ruled_at: u64
    contest_deadline: u64
    contester: str
    contest_stake: u256
    contested_at: u64
    contest_read_deadline: u64
    ruling2_json: str
    verdict: str
    reason: str
    how: str
    final_at: u64
    source_time: u64
    payouts_json: str


class BackedByRegistry(gl.contract.Contract):
    mode: str
    reader: Address
    treasury: str
    window_s: u64
    read_timeout_s: u64
    contest_timeout_s: u64
    unbond_delay_s: u64
    monitor_interval_s: u64
    min_stake: u256
    min_bond: u256
    auth_max_age_s: u64
    n_pairs: u64
    n_bonds: u64
    n_checks: u64
    pairs: gl.storage.TreeMap[u64, Pair]
    pair_by_key: gl.storage.TreeMap[str, u64]
    dest_owner: gl.storage.TreeMap[str, u64]
    bonds: gl.storage.TreeMap[u64, Bond]
    checks: gl.storage.TreeMap[u64, Check]
    counts: gl.storage.TreeMap[str, u64]
    claimable: gl.storage.TreeMap[str, u256]
    claimed: gl.storage.TreeMap[str, u256]
    received_total: u256
    bonds_total: u256
    open_total: u256
    claimable_total: u256
    claimed_total: u256
    slashed_total: u256
    bounty_total: u256

    def __init__(self, mode: str, reader: str) -> None:
        m = str(mode).strip().upper()
        if m not in MODES:
            raise gl.vm.UserError("mode must be CANONICAL or DEMO")
        r = _addr(reader)
        if r == "":
            raise gl.vm.UserError("reader must be a 0x address")
        p = MODES[m]
        self.mode = m
        self.reader = Address(r)
        self.treasury = gl.message.sender_address.as_hex.lower()
        self.window_s = u64(p[0])
        self.read_timeout_s = u64(p[1])
        self.contest_timeout_s = u64(p[2])
        self.unbond_delay_s = u64(p[3])
        self.monitor_interval_s = u64(p[4])
        self.min_stake = u256(p[5])
        self.min_bond = u256(p[6])
        self.auth_max_age_s = u64(p[7])
        self.n_pairs = u64(0)
        self.n_bonds = u64(0)
        self.n_checks = u64(0)

    # --- helpers --------------------------------------------------------------

    def _now(self) -> int:
        return _epoch_from_iso(gl.message.raw.get("datetime", ""))

    def _sender(self) -> str:
        return gl.message.sender_address.as_hex.lower()

    def _ext(self, fn: str, args: list) -> typing.Any:
        try:
            v = gl.contract.get_at(self.reader).view()
            raw = getattr(v, fn)(*args)
        except Exception:
            return None
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None
        return raw

    def _bump(self, key: str, by: int = 1) -> None:
        self.counts[key] = u64(int(self.counts.get(key, u64(0))) + by)

    def _credit(self, who: str, amount: int) -> None:
        if amount <= 0:
            return
        self.claimable[who] = u256(int(self.claimable.get(who, u256(0))) + amount)
        self.claimable_total = u256(int(self.claimable_total) + amount)

    def _reject(self, value: int, reason: str) -> dict:
        """A payable refusal: the value is credited back, never kept, never raised on."""
        if value > 0:
            self.received_total = u256(int(self.received_total) + value)
            self._credit(self._sender(), value)
            self._bump("refused_payable")
        return {"ok": False, "reason": reason, "refunded": str(value)}

    def _dests(self, p: Pair) -> list:
        return json.loads(p.dests_json)

    def _chains(self, p: Pair) -> list:
        out = [SOURCE_CHAIN]
        for d in self._dests(p):
            if d["chain"] not in out:
                out.append(d["chain"])
        return out

    def _auth(self, aid: int, now: int) -> typing.Any:
        a = self._ext("get_auth", [aid])
        if not isinstance(a, dict) or a.get("found") is not True:
            return "AUTH_" + str(aid) + "_NOT_FOUND"
        if int(a.get("read_at", 0)) + int(self.auth_max_age_s) < now:
            return "AUTH_" + str(aid) + "_TOO_OLD_REAUTHENTICATE"
        if a.get("kind") not in KINDS or a.get("source_chain") != SOURCE_CHAIN:
            return "AUTH_" + str(aid) + "_UNSUPPORTED"
        if KINDS[a["kind"]] != a.get("dest_chain"):
            return "AUTH_" + str(aid) + "_WRONG_DEST_CHAIN"
        if _addr(a.get("vault", "")) == "" or _addr(a.get("source_token", "")) == "" or _addr(a.get("dest_token", "")) == "":
            return "AUTH_" + str(aid) + "_MALFORMED"
        return a

    def _request(self, c: Check, rnd: int) -> dict:
        req = json.loads(c.request_json)
        req["ok"] = True
        req["round"] = rnd
        req["check_id"] = int(c.check_id)
        return req

    def _terms(self, p: Pair, c: Check) -> dict:
        req = json.loads(c.request_json)
        return {"source_decimals": int(p.source_decimals), "tolerance_bps": int(p.tolerance_bps),
                "max_gap_s": int(p.max_gap_s), "dests": req["terms_dests"]}

    def _cover(self, c: Check) -> typing.Any:
        if c.purpose != P_CHALLENGE:
            return None
        b = self.bonds[c.bond_id]
        return [int(b.since), int(b.unbond_at)]

    def _new_check(self, p: Pair, purpose: str, bond_id: int, stake: int, blocks: dict, now: int) -> int:
        dests = self._dests(p)
        req = {"source_chain": SOURCE_CHAIN, "vault": p.vault, "source_token": p.source_token,
               "dests": [{"chain": d["chain"], "token": d["token"], "deposits": p.kind in DEPOSIT_KINDS} for d in dests],
               "blocks": blocks,
               "terms_dests": [{"chain": d["chain"], "token": d["token"], "decimals": int(d["decimals"])} for d in dests]}
        cid = int(self.n_checks) + 1
        self.checks[u64(cid)] = Check(
            check_id=u64(cid), pair_id=p.pair_id, purpose=purpose, bond_id=u64(bond_id), filer=self._sender(),
            stake=u256(stake), request_json=_canon(req), filed_at=u64(now),
            read_deadline=u64(now + int(self.read_timeout_s)), status=ST_OPEN, round=u64(1), verdict1="",
            ruling1_json="", ruled_at=u64(0), contest_deadline=u64(0), contester="", contest_stake=u256(0),
            contested_at=u64(0), contest_read_deadline=u64(0), ruling2_json="", verdict="", reason="", how="",
            final_at=u64(0), source_time=u64(0), payouts_json="")
        self.n_checks = u64(cid)
        p.open_check = u64(cid)
        p.checks_csv = (p.checks_csv + "," if p.checks_csv != "" else "") + str(cid)
        self._bump("filed:" + purpose)
        return cid

    def _close(self, c: Check, p: Pair, status: str, verdict: str, reason: str, how: str, now: int,
               payouts: dict, update_latest: bool) -> None:
        """Terminal transition. All money for it has already been moved by the caller."""
        c.status = status
        c.verdict = verdict
        c.reason = reason
        c.how = how
        c.final_at = u64(now)
        c.payouts_json = _canon(payouts)
        if int(p.open_check) == int(c.check_id):
            p.open_check = u64(0)
        if c.purpose == P_CHALLENGE:
            b = self.bonds[c.bond_id]
            if int(b.open_check) == int(c.check_id):
                b.open_check = u64(0)
        st = int(c.source_time)
        if update_latest and st > 0 and (st > int(p.latest_time) or (st == int(p.latest_time) and int(c.check_id) > int(p.latest_check))):
            p.latest_check = c.check_id
            p.latest_time = u64(st)
        self._bump("status:" + status)
        self._bump("verdict:" + verdict)
        self._bump("how:" + how)

    def _settle(self, c: Check, p: Pair, verdict: str, now: int, how: str, reason: str,
                contest_to: str) -> dict:
        """Moves the money for a FINAL verdict. contest_to: who receives a lost
        contest stake ("" = refund it to the contester)."""
        stake = int(c.stake)
        cst = int(c.contest_stake)
        pay = {"challenger": "0", "bond_in": "0", "slash": "0", "bounty": "0", "treasury": "0", "contest_refund": "0",
               "contest_lost": "0"}
        if c.purpose == P_CHALLENGE:
            b = self.bonds[c.bond_id]
            if verdict == V_UNDER:
                parts = slash_split(int(b.amount))
                b.amount = u256(0)
                b.slashed = u256(int(b.slashed) + parts[0])
                b.status = B_SLASHED
                b.closed_at = u64(now)
                self.bonds_total = u256(int(self.bonds_total) - parts[0])
                self.open_total = u256(int(self.open_total) - stake)
                self._credit(c.filer, stake + parts[1])
                self._credit(self.treasury, parts[2])
                self.slashed_total = u256(int(self.slashed_total) + parts[0])
                self.bounty_total = u256(int(self.bounty_total) + parts[1])
                pay["challenger"] = str(stake + parts[1])
                pay["slash"] = str(parts[0])
                pay["bounty"] = str(parts[1])
                pay["treasury"] = str(parts[2])
            else:
                b.amount = u256(int(b.amount) + stake)
                b.won = u256(int(b.won) + stake)
                self.open_total = u256(int(self.open_total) - stake)
                self.bonds_total = u256(int(self.bonds_total) + stake)
                pay["bond_in"] = str(stake)
        if cst > 0:
            self.open_total = u256(int(self.open_total) - cst)
            if contest_to == "":
                self._credit(c.contester, cst)
                pay["contest_refund"] = str(cst)
            elif contest_to == "bond":
                b2 = self.bonds[c.bond_id]
                b2.amount = u256(int(b2.amount) + cst)
                b2.won = u256(int(b2.won) + cst)
                self.bonds_total = u256(int(self.bonds_total) + cst)
                pay["contest_lost"] = str(cst)
                pay["bond_in"] = str(int(pay["bond_in"]) + cst)
            else:
                self._credit(contest_to, cst)
                pay["contest_lost"] = str(cst)
        self._close(c, p, ST_FINAL, verdict, reason, how, now, pay, True)
        return pay

    def _refund_all(self, c: Check, p: Pair, reason: str, how: str, now: int, update_latest: bool) -> dict:
        stake = int(c.stake)
        cst = int(c.contest_stake)
        if stake > 0:
            self.open_total = u256(int(self.open_total) - stake)
            self._credit(c.filer, stake)
        if cst > 0:
            self.open_total = u256(int(self.open_total) - cst)
            self._credit(c.contester, cst)
        pay = {"stake_refund": str(stake), "contest_refund": str(cst)}
        self._close(c, p, ST_INC, V_INC, reason, how, now, pay, update_latest)
        return pay

    def _lost_contest_to(self, c: Check, verdict: str) -> str:
        if c.purpose == P_CHALLENGE:
            return "bond" if verdict == V_BACKED else c.filer
        return self.treasury

    # --- pairs ----------------------------------------------------------------

    @gl.public.write
    def register_pair(self, auth_ids: str, tolerance_bps: int, label: str) -> typing.Any:
        """Register a pair from ChainReader authentications (comma-separated
        ids, one per destination token, all of the same vault and source token)."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        ids = []
        for part in str(auth_ids).split(","):
            v = _as_int(part, -1)
            if v <= 0:
                raise gl.vm.UserError("REFUSED: AUTH_IDS_MUST_BE_POSITIVE_INTEGERS")
            if v in ids:
                raise gl.vm.UserError("REFUSED: DUPLICATE_AUTH_ID")
            ids.append(v)
        if len(ids) < 1 or len(ids) > MAX_DESTS:
            raise gl.vm.UserError("REFUSED: ONE_TO_" + str(MAX_DESTS) + "_DESTINATIONS")
        tol = _as_int(tolerance_bps, -1)
        if tol < 0 or tol > MAX_TOLERANCE_BPS:
            raise gl.vm.UserError("REFUSED: TOLERANCE_OUT_OF_RANGE_0_" + str(MAX_TOLERANCE_BPS))
        auths = []
        seen = []
        for aid in ids:
            a = self._auth(aid, now)
            if isinstance(a, str):
                raise gl.vm.UserError("REFUSED: " + a)
            if len(auths) > 0:
                f = auths[0]
                if a["kind"] != f["kind"] or a["vault"] != f["vault"] or a["source_token"] != f["source_token"] \
                        or int(a["source_decimals"]) != int(f["source_decimals"]):
                    raise gl.vm.UserError("REFUSED: AUTHS_ARE_NOT_ONE_PAIR")
            dk = a["dest_chain"] + "|" + a["dest_token"]
            if dk in seen:
                raise gl.vm.UserError("REFUSED: DUPLICATE_DESTINATION")
            if int(self.dest_owner.get(dk, u64(0))) != 0:
                raise gl.vm.UserError("REFUSED: DESTINATION_ALREADY_IN_PAIR_" + str(int(self.dest_owner.get(dk, u64(0)))))
            seen.append(dk)
            auths.append(a)
        f = auths[0]
        key = SOURCE_CHAIN + "|" + f["vault"] + "|" + f["source_token"]
        if int(self.pair_by_key.get(key, u64(0))) != 0:
            raise gl.vm.UserError("REFUSED: PAIR_EXISTS_AS_" + str(int(self.pair_by_key.get(key, u64(0)))) + "_ADD_A_DESTINATION_INSTEAD")
        dests = [{"chain": a["dest_chain"], "token": a["dest_token"], "decimals": int(a["dest_decimals"]),
                  "auth_id": int(a["auth_id"]), "added_by": self._sender(), "added_at": now} for a in auths]
        # --- writes
        pid = int(self.n_pairs) + 1
        self.pairs[u64(pid)] = Pair(
            pair_id=u64(pid), key=key, kind=f["kind"], source_chain=SOURCE_CHAIN, vault=f["vault"],
            source_token=f["source_token"], source_decimals=u64(int(f["source_decimals"])), tolerance_bps=u64(tol),
            max_gap_s=u64(KIND_MAX_GAP_S.get(f["kind"], MAX_GAP_S)), label=clean_label(label),
            dests_json=_canon(dests), registered_by=self._sender(), registered_at=u64(now), open_check=u64(0),
            latest_check=u64(0), latest_time=u64(0), last_monitor_at=u64(0), checks_csv="", bonds_csv="")
        self.pair_by_key[key] = u64(pid)
        for dk in seen:
            self.dest_owner[dk] = u64(pid)
        self.n_pairs = u64(pid)
        self._bump("pairs")
        return {"ok": True, "pair_id": pid, "destinations": len(dests)}

    @gl.public.write
    def add_destination(self, pair_id: int, auth_id: int) -> typing.Any:
        """Anyone: add a destination token the pair is missing, with the same
        on-chain proof. Checks already filed keep the destinations they had."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        p = self.pairs.get(u64(max(_as_int(pair_id, 0), 0)))
        if p is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_PAIR")
        a = self._auth(_as_int(auth_id, -1), now)
        if isinstance(a, str):
            raise gl.vm.UserError("REFUSED: " + a)
        if a["kind"] != p.kind or a["vault"] != p.vault or a["source_token"] != p.source_token \
                or int(a["source_decimals"]) != int(p.source_decimals):
            raise gl.vm.UserError("REFUSED: AUTH_IS_FOR_ANOTHER_PAIR")
        dk = a["dest_chain"] + "|" + a["dest_token"]
        if int(self.dest_owner.get(dk, u64(0))) != 0:
            raise gl.vm.UserError("REFUSED: DESTINATION_ALREADY_IN_PAIR_" + str(int(self.dest_owner.get(dk, u64(0)))))
        dests = self._dests(p)
        if len(dests) >= MAX_DESTS:
            raise gl.vm.UserError("REFUSED: PAIR_HAS_" + str(MAX_DESTS) + "_DESTINATIONS")
        dests.append({"chain": a["dest_chain"], "token": a["dest_token"], "decimals": int(a["dest_decimals"]),
                      "auth_id": int(a["auth_id"]), "added_by": self._sender(), "added_at": now})
        # --- writes
        p.dests_json = _canon(dests)
        self.dest_owner[dk] = p.pair_id
        self._bump("destinations_added")
        return {"ok": True, "pair_id": int(p.pair_id), "destinations": len(dests)}

    # --- bonds ----------------------------------------------------------------

    @gl.public.write.payable
    def bond(self, pair_id: int) -> typing.Any:
        """Bond that the pair stays BACKED from now until you request to unbond."""
        value = int(gl.message.value)
        now = self._now()
        if now <= 0:
            return self._reject(value, "NO_CLOCK")
        p = self.pairs.get(u64(max(_as_int(pair_id, 0), 0)))
        if p is None:
            return self._reject(value, "NO_SUCH_PAIR")
        if value < int(self.min_bond):
            return self._reject(value, "BOND_BELOW_MINIMUM_" + str(int(self.min_bond)))
        if value > MAX_AMOUNT:
            return self._reject(value, "BOND_TOO_LARGE")
        # --- writes
        bid = int(self.n_bonds) + 1
        self.bonds[u64(bid)] = Bond(bond_id=u64(bid), pair_id=p.pair_id, operator=self._sender(), amount=u256(value),
                                    deposited=u256(value), won=u256(0), slashed=u256(0), since=u64(now),
                                    unbond_at=u64(0), status=B_ACTIVE, open_check=u64(0), closed_at=u64(0))
        self.n_bonds = u64(bid)
        p.bonds_csv = (p.bonds_csv + "," if p.bonds_csv != "" else "") + str(bid)
        self.received_total = u256(int(self.received_total) + value)
        self.bonds_total = u256(int(self.bonds_total) + value)
        self._bump("bonds")
        return {"ok": True, "bond_id": bid, "amount": str(value), "since": now}

    @gl.public.write.payable
    def top_up(self, bond_id: int) -> typing.Any:
        value = int(gl.message.value)
        b = self.bonds.get(u64(max(_as_int(bond_id, 0), 0)))
        if b is None:
            return self._reject(value, "NO_SUCH_BOND")
        if b.operator != self._sender():
            return self._reject(value, "ONLY_THE_OPERATOR")
        if b.status != B_ACTIVE:
            return self._reject(value, "BOND_IS_" + b.status)
        if value <= 0 or int(b.amount) + value > MAX_AMOUNT:
            return self._reject(value, "AMOUNT_OUT_OF_RANGE")
        # --- writes
        b.amount = u256(int(b.amount) + value)
        b.deposited = u256(int(b.deposited) + value)
        self.received_total = u256(int(self.received_total) + value)
        self.bonds_total = u256(int(self.bonds_total) + value)
        return {"ok": True, "bond_id": int(b.bond_id), "amount": str(int(b.amount))}

    @gl.public.write
    def request_unbond(self, bond_id: int) -> typing.Any:
        """Stops the bond's promise now; the bond can be withdrawn after the
        delay, once no check on it is open. Blocks after now are not covered."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        b = self.bonds.get(u64(max(_as_int(bond_id, 0), 0)))
        if b is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_BOND")
        if b.operator != self._sender():
            raise gl.vm.UserError("REFUSED: ONLY_THE_OPERATOR")
        if b.status != B_ACTIVE:
            raise gl.vm.UserError("REFUSED: BOND_IS_" + b.status)
        # --- writes
        b.status = B_UNBONDING
        b.unbond_at = u64(now)
        return {"ok": True, "bond_id": int(b.bond_id), "withdrawable_at": now + int(self.unbond_delay_s)}

    @gl.public.write
    def withdraw_bond(self, bond_id: int) -> typing.Any:
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        b = self.bonds.get(u64(max(_as_int(bond_id, 0), 0)))
        if b is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_BOND")
        if b.operator != self._sender():
            raise gl.vm.UserError("REFUSED: ONLY_THE_OPERATOR")
        if b.status != B_UNBONDING:
            raise gl.vm.UserError("REFUSED: REQUEST_UNBOND_FIRST" if b.status == B_ACTIVE else "REFUSED: BOND_IS_" + b.status)
        if now < int(b.unbond_at) + int(self.unbond_delay_s):
            raise gl.vm.UserError("REFUSED: WITHDRAWABLE_AT_" + str(int(b.unbond_at) + int(self.unbond_delay_s)))
        if int(b.open_check) != 0:
            raise gl.vm.UserError("REFUSED: CHECK_" + str(int(b.open_check)) + "_IS_OPEN_ON_THIS_BOND")
        amount = int(b.amount)
        # --- writes
        b.amount = u256(0)
        b.status = B_WITHDRAWN
        b.closed_at = u64(now)
        self.bonds_total = u256(int(self.bonds_total) - amount)
        self._credit(b.operator, amount)
        self._bump("bonds_withdrawn")
        return {"ok": True, "bond_id": int(b.bond_id), "credited": str(amount)}

    # --- checks ---------------------------------------------------------------

    @gl.public.write.payable
    def challenge(self, bond_id: int, blocks: str) -> typing.Any:
        """Stake that the bonded pair was NOT backed at these blocks
        ({"ethereum": n, "<dest chain>": n}). Supersedes an open monitoring check."""
        value = int(gl.message.value)
        now = self._now()
        if now <= 0:
            return self._reject(value, "NO_CLOCK")
        b = self.bonds.get(u64(max(_as_int(bond_id, 0), 0)))
        if b is None:
            return self._reject(value, "NO_SUCH_BOND")
        if b.status != B_ACTIVE and b.status != B_UNBONDING:
            return self._reject(value, "BOND_IS_" + b.status)
        if int(b.amount) <= 0:
            return self._reject(value, "BOND_IS_EMPTY")
        if b.operator == self._sender():
            return self._reject(value, "OPERATOR_CANNOT_CHALLENGE_OWN_BOND")
        if value < int(self.min_stake):
            return self._reject(value, "STAKE_BELOW_MINIMUM_" + str(int(self.min_stake)))
        if value > MAX_AMOUNT:
            return self._reject(value, "STAKE_TOO_LARGE")
        p = self.pairs[b.pair_id]
        bl = parse_blocks(blocks, self._chains(p))
        if isinstance(bl, str):
            return self._reject(value, bl)
        sup = None
        if int(p.open_check) != 0:
            o = self.checks[p.open_check]
            if o.purpose != P_MONITOR:
                return self._reject(value, "CHECK_" + str(int(o.check_id)) + "_IS_OPEN_ON_THIS_PAIR")
            sup = o
        # --- writes
        if sup is not None:
            self._refund_all(sup, p, "SUPERSEDED_BY_A_CHALLENGE", "SUPERSEDED", now, False)
        self.received_total = u256(int(self.received_total) + value)
        self.open_total = u256(int(self.open_total) + value)
        cid = self._new_check(p, P_CHALLENGE, int(b.bond_id), value, bl, now)
        b.open_check = u64(cid)
        return {"ok": True, "check_id": cid, "stake": str(value),
                "superseded": int(sup.check_id) if sup is not None else 0}

    @gl.public.write
    def monitor(self, pair_id: int, blocks: str) -> typing.Any:
        """A monitoring check: no stake, no bond, at most one per pair per
        monitor interval, and only while no other check is open on the pair."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        p = self.pairs.get(u64(max(_as_int(pair_id, 0), 0)))
        if p is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_PAIR")
        if int(p.open_check) != 0:
            raise gl.vm.UserError("REFUSED: CHECK_" + str(int(p.open_check)) + "_IS_OPEN_ON_THIS_PAIR")
        if int(p.last_monitor_at) > 0 and now < int(p.last_monitor_at) + int(self.monitor_interval_s):
            raise gl.vm.UserError("REFUSED: RATE_LIMITED_UNTIL_" + str(int(p.last_monitor_at) + int(self.monitor_interval_s)))
        bl = parse_blocks(blocks, self._chains(p))
        if isinstance(bl, str):
            raise gl.vm.UserError("REFUSED: " + bl)
        # --- writes
        p.last_monitor_at = u64(now)
        cid = self._new_check(p, P_MONITOR, 0, 0, bl, now)
        return {"ok": True, "check_id": cid}

    @gl.public.view
    def get_check_request(self, check_id: int) -> typing.Any:
        """What ChainReader must read for this check's current round."""
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            return {"ok": False, "why": "NO_SUCH_CHECK"}
        if c.status == ST_OPEN:
            return self._request(c, 1)
        if c.status == ST_CONT:
            return self._request(c, 2)
        return {"ok": False, "why": "CHECK_IS_" + c.status}

    @gl.public.write
    def rule(self, check_id: int) -> typing.Any:
        """Rule on the reading ChainReader recorded for this round. Anyone."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_CHECK")
        if c.status != ST_OPEN and c.status != ST_CONT:
            raise gl.vm.UserError("REFUSED: NOTHING_TO_RULE_ON_IN_" + c.status)
        rnd = 1 if c.status == ST_OPEN else 2
        me = gl.message.contract_address.as_hex.lower()
        r = self._ext("get_reading", [me, int(c.check_id), rnd])
        if not isinstance(r, dict) or r.get("found") is not True:
            raise gl.vm.UserError("REFUSED: NOT_READ_YET_CALL_CHAINREADER_READ_CHECK")
        if r.get("request_sha") != _sha(_canon(self._request(c, rnd))):
            raise gl.vm.UserError("REFUSED: READING_IS_FOR_ANOTHER_REQUEST")
        p = self.pairs[c.pair_id]
        out = compute(r.get("reading"), self._terms(p, c), self._cover(c))
        # --- writes (nothing below can refuse)
        if rnd == 1:
            c.ruling1_json = _canon(out)
            c.ruled_at = u64(now)
            c.source_time = u64(int(out["source_time"]))
            if out["verdict"] == V_INC:
                pay = self._refund_all(c, p, out["reason"], "READ_" + out["cls"], now, out["cls"] == "DATA")
                return {"ok": True, "check_id": int(c.check_id), "status": ST_INC, "reason": out["reason"], "payouts": pay}
            c.verdict1 = out["verdict"]
            c.status = ST_PROV
            c.contest_deadline = u64(now + int(self.window_s))
            self._bump("provisional:" + out["verdict"])
            return {"ok": True, "check_id": int(c.check_id), "status": ST_PROV, "verdict": out["verdict"],
                    "ratio_bps": out["ratio_bps"], "contestable_until": int(c.contest_deadline)}
        c.ruling2_json = _canon(out)
        if out["verdict"] == V_INC:
            pay = self._refund_all(c, p, "CONTEST_REREAD_INCONCLUSIVE:" + out["reason"], "CONTEST_REREAD_INCONCLUSIVE",
                                   now, True)
            return {"ok": True, "check_id": int(c.check_id), "status": ST_INC, "payouts": pay}
        if out["verdict"] != c.verdict1:
            pay = self._refund_all(c, p, "CONTEST_DISAGREES", "CONTEST_DISAGREES", now, True)
            return {"ok": True, "check_id": int(c.check_id), "status": ST_INC, "payouts": pay}
        pay = self._settle(c, p, c.verdict1, now, "CONTEST_UPHELD_RULING", json.loads(c.ruling1_json)["reason"],
                           self._lost_contest_to(c, c.verdict1))
        return {"ok": True, "check_id": int(c.check_id), "status": ST_FINAL, "verdict": c.verdict1, "payouts": pay}

    @gl.public.write.payable
    def contest(self, check_id: int) -> typing.Any:
        """Contest a PROVISIONAL ruling inside its window: the same pinned
        blocks are read again. Same verdict: FINAL, and the contest stake goes
        to the side the ruling favoured. Different: INCONCLUSIVE, all refunded."""
        value = int(gl.message.value)
        now = self._now()
        if now <= 0:
            return self._reject(value, "NO_CLOCK")
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            return self._reject(value, "NO_SUCH_CHECK")
        if c.status != ST_PROV:
            return self._reject(value, "NOT_PROVISIONAL_" + c.status)
        if now >= int(c.contest_deadline):
            return self._reject(value, "CONTEST_WINDOW_CLOSED_AT_" + str(int(c.contest_deadline)))
        if value < int(self.min_stake):
            return self._reject(value, "STAKE_BELOW_MINIMUM_" + str(int(self.min_stake)))
        if value > MAX_AMOUNT:
            return self._reject(value, "STAKE_TOO_LARGE")
        # --- writes
        self.received_total = u256(int(self.received_total) + value)
        self.open_total = u256(int(self.open_total) + value)
        c.status = ST_CONT
        c.round = u64(2)
        c.contester = self._sender()
        c.contest_stake = u256(value)
        c.contested_at = u64(now)
        c.contest_read_deadline = u64(now + int(self.contest_timeout_s))
        self._bump("contests")
        return {"ok": True, "check_id": int(c.check_id), "reread_by": int(c.contest_read_deadline)}

    @gl.public.write
    def finalize(self, check_id: int) -> typing.Any:
        """A PROVISIONAL ruling whose window has passed becomes FINAL. Anyone."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_CHECK")
        if c.status != ST_PROV:
            raise gl.vm.UserError("REFUSED: NOT_PROVISIONAL_" + c.status)
        if now < int(c.contest_deadline):
            raise gl.vm.UserError("REFUSED: CONTESTABLE_UNTIL_" + str(int(c.contest_deadline)))
        p = self.pairs[c.pair_id]
        # --- writes
        pay = self._settle(c, p, c.verdict1, now, "WINDOW_PASSED", json.loads(c.ruling1_json)["reason"], "")
        return {"ok": True, "check_id": int(c.check_id), "status": ST_FINAL, "verdict": c.verdict1, "payouts": pay}

    @gl.public.write
    def expire(self, check_id: int) -> typing.Any:
        """The timeout exit. OPEN past its read deadline with no reading:
        INCONCLUSIVE, stake refunded. CONTESTED past its re-read deadline with no
        re-reading: the first ruling stands (FINAL) and the contest stake is
        refunded. Anyone."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            raise gl.vm.UserError("REFUSED: NO_SUCH_CHECK")
        me = gl.message.contract_address.as_hex.lower()
        p = self.pairs[c.pair_id]
        if c.status == ST_OPEN:
            if now < int(c.read_deadline):
                raise gl.vm.UserError("REFUSED: READ_DEADLINE_AT_" + str(int(c.read_deadline)))
            r = self._ext("get_reading", [me, int(c.check_id), 1])
            if isinstance(r, dict) and r.get("found") is True:
                raise gl.vm.UserError("REFUSED: A_READING_EXISTS_CALL_RULE")
            pay = self._refund_all(c, p, "NO_READING_BEFORE_DEADLINE", "TIMEOUT_UNREAD", now, False)
            return {"ok": True, "check_id": int(c.check_id), "status": ST_INC, "payouts": pay}
        if c.status == ST_CONT:
            if now < int(c.contest_read_deadline):
                raise gl.vm.UserError("REFUSED: REREAD_DEADLINE_AT_" + str(int(c.contest_read_deadline)))
            r = self._ext("get_reading", [me, int(c.check_id), 2])
            if isinstance(r, dict) and r.get("found") is True:
                raise gl.vm.UserError("REFUSED: A_READING_EXISTS_CALL_RULE")
            pay = self._settle(c, p, c.verdict1, now, "TIMEOUT_CONTEST_UNREAD", json.loads(c.ruling1_json)["reason"], "")
            return {"ok": True, "check_id": int(c.check_id), "status": ST_FINAL, "verdict": c.verdict1, "payouts": pay}
        raise gl.vm.UserError("REFUSED: NOTHING_TO_EXPIRE_IN_" + c.status)

    @gl.public.write
    def claim(self) -> typing.Any:
        """Pull everything credited to the caller. Zeroed before the transfer."""
        who = self._sender()
        owed = int(self.claimable.get(who, u256(0)))
        if owed <= 0:
            raise gl.vm.UserError("REFUSED: NOTHING_TO_CLAIM")
        # --- writes
        self.claimable[who] = u256(0)
        self.claimable_total = u256(int(self.claimable_total) - owed)
        self.claimed[who] = u256(int(self.claimed.get(who, u256(0))) + owed)
        self.claimed_total = u256(int(self.claimed_total) + owed)
        gl.chain.Account(Address(who)).emit_transfer(u256(owed))
        return {"ok": True, "claimed": str(owed)}

    # --- views (storage only) -------------------------------------------------

    def _pair_view(self, p: Pair) -> dict:
        return {"pair_id": int(p.pair_id), "key": p.key, "kind": p.kind, "source_chain": p.source_chain,
                "vault": p.vault, "source_token": p.source_token, "source_decimals": int(p.source_decimals),
                "tolerance_bps": int(p.tolerance_bps), "max_gap_s": int(p.max_gap_s), "label": p.label,
                "dests": self._dests(p), "registered_by": p.registered_by, "registered_at": int(p.registered_at),
                "open_check": int(p.open_check), "latest_check": int(p.latest_check), "latest_time": int(p.latest_time),
                "last_monitor_at": int(p.last_monitor_at),
                "checks": [int(x) for x in p.checks_csv.split(",")] if p.checks_csv != "" else [],
                "bonds": [int(x) for x in p.bonds_csv.split(",")] if p.bonds_csv != "" else []}

    def _bond_view(self, b: Bond) -> dict:
        return {"bond_id": int(b.bond_id), "pair_id": int(b.pair_id), "operator": b.operator,
                "amount": str(int(b.amount)), "deposited": str(int(b.deposited)), "won": str(int(b.won)),
                "slashed": str(int(b.slashed)), "since": int(b.since), "unbond_at": int(b.unbond_at),
                "withdrawable_at": (int(b.unbond_at) + int(self.unbond_delay_s)) if int(b.unbond_at) > 0 else 0,
                "status": b.status, "open_check": int(b.open_check), "closed_at": int(b.closed_at)}

    def _check_view(self, c: Check) -> dict:
        req = json.loads(c.request_json)
        return {"check_id": int(c.check_id), "pair_id": int(c.pair_id), "purpose": c.purpose,
                "bond_id": int(c.bond_id), "filer": c.filer, "stake": str(int(c.stake)), "blocks": req["blocks"],
                "dests": req["terms_dests"], "filed_at": int(c.filed_at), "read_deadline": int(c.read_deadline),
                "status": c.status, "round": int(c.round), "verdict1": c.verdict1,
                "ruling1": json.loads(c.ruling1_json) if c.ruling1_json != "" else None, "ruled_at": int(c.ruled_at),
                "contest_deadline": int(c.contest_deadline), "contester": c.contester,
                "contest_stake": str(int(c.contest_stake)), "contested_at": int(c.contested_at),
                "contest_read_deadline": int(c.contest_read_deadline),
                "ruling2": json.loads(c.ruling2_json) if c.ruling2_json != "" else None, "verdict": c.verdict,
                "reason": c.reason, "how": c.how, "final_at": int(c.final_at), "source_time": int(c.source_time),
                "payouts": json.loads(c.payouts_json) if c.payouts_json != "" else None}

    @gl.public.view
    def get_pair(self, pair_id: int) -> typing.Any:
        p = self.pairs.get(u64(max(_as_int(pair_id, 0), 0)))
        if p is None:
            return {"found": False}
        out = self._pair_view(p)
        out["found"] = True
        return out

    @gl.public.view
    def get_pairs(self, offset: int, limit: int) -> typing.Any:
        o = max(_as_int(offset, 0), 0)
        lim = min(max(_as_int(limit, 20), 0), MAX_PAGE)
        out = []
        i = o + 1
        while i <= int(self.n_pairs) and len(out) < lim:
            p = self.pairs.get(u64(i))
            if p is not None:
                v = self._pair_view(p)
                lc = int(p.latest_check)
                v["latest"] = self._check_view(self.checks[u64(lc)]) if lc > 0 else None
                oc = int(p.open_check)
                v["open"] = self._check_view(self.checks[u64(oc)]) if oc > 0 else None
                out.append(v)
            i += 1
        return {"total": int(self.n_pairs), "pairs": out}

    @gl.public.view
    def get_latest(self, pair_id: int) -> typing.Any:
        """The pair's latest ruling (FINAL, or an INCONCLUSIVE that says something
        about the pair), by pinned source-block time. CollateralGate reads this."""
        p = self.pairs.get(u64(max(_as_int(pair_id, 0), 0)))
        if p is None:
            return {"found": False, "pair": False}
        lc = int(p.latest_check)
        if lc == 0:
            return {"found": False, "pair": True}
        c = self.checks[u64(lc)]
        r = json.loads(c.ruling1_json) if c.ruling1_json != "" else {}
        return {"found": True, "pair": True, "check_id": lc, "verdict": c.verdict, "status": c.status,
                "source_time": int(c.source_time), "final_at": int(c.final_at), "ratio_bps": r.get("ratio_bps", -1),
                "reason": c.reason}

    @gl.public.view
    def get_bond(self, bond_id: int) -> typing.Any:
        b = self.bonds.get(u64(max(_as_int(bond_id, 0), 0)))
        if b is None:
            return {"found": False}
        out = self._bond_view(b)
        out["found"] = True
        return out

    @gl.public.view
    def get_bonds(self, offset: int, limit: int) -> typing.Any:
        o = max(_as_int(offset, 0), 0)
        lim = min(max(_as_int(limit, 20), 0), MAX_PAGE)
        out = []
        i = o + 1
        while i <= int(self.n_bonds) and len(out) < lim:
            b = self.bonds.get(u64(i))
            if b is not None:
                out.append(self._bond_view(b))
            i += 1
        return {"total": int(self.n_bonds), "bonds": out}

    @gl.public.view
    def get_check(self, check_id: int) -> typing.Any:
        c = self.checks.get(u64(max(_as_int(check_id, 0), 0)))
        if c is None:
            return {"found": False}
        out = self._check_view(c)
        out["found"] = True
        return out

    @gl.public.view
    def get_checks(self, offset: int, limit: int) -> typing.Any:
        """Newest first."""
        o = max(_as_int(offset, 0), 0)
        lim = min(max(_as_int(limit, 20), 0), MAX_PAGE)
        out = []
        i = int(self.n_checks) - o
        while i >= 1 and len(out) < lim:
            c = self.checks.get(u64(i))
            if c is not None:
                out.append(self._check_view(c))
            i -= 1
        return {"total": int(self.n_checks), "checks": out}

    @gl.public.view
    def get_claimable(self, who: str) -> typing.Any:
        a = _addr(who)
        return {"address": a, "claimable": str(int(self.claimable.get(a, u256(0)))),
                "claimed": str(int(self.claimed.get(a, u256(0))))}

    @gl.public.view
    def get_ledger(self) -> typing.Any:
        received = int(self.received_total)
        held = int(self.bonds_total) + int(self.open_total) + int(self.claimable_total)
        books = held + int(self.claimed_total)
        bonds = 0
        i = 1
        while i <= int(self.n_bonds):
            bonds += int(self.bonds[u64(i)].amount)
            i += 1
        opens = 0
        i = 1
        while i <= int(self.n_checks):
            c = self.checks[u64(i)]
            if c.status == ST_OPEN or c.status == ST_PROV or c.status == ST_CONT:
                opens += int(c.stake) + int(c.contest_stake)
            i += 1
        return {"received": str(received), "bonds": str(int(self.bonds_total)), "open_stakes": str(int(self.open_total)),
                "claimable": str(int(self.claimable_total)), "claimed": str(int(self.claimed_total)),
                "held_now": str(held), "invariant_holds": received == books,
                "bonds_recomputed_match": bonds == int(self.bonds_total),
                "open_recomputed_match": opens == int(self.open_total),
                "slashed": str(int(self.slashed_total)), "bounties": str(int(self.bounty_total)),
                "on_chain_balance": str(int(self.balance))}

    @gl.public.view
    def get_stats(self) -> typing.Any:
        out = {}
        for k in COUNT_KEYS:
            out[k] = int(self.counts.get(k, u64(0)))
        return {"pairs": int(self.n_pairs), "bonds": int(self.n_bonds), "checks": int(self.n_checks), "counts": out}

    @gl.public.view
    def get_config(self) -> typing.Any:
        return {"version": VERSION, "contract": "BackedByRegistry", "mode": self.mode,
                "reader": self.reader.as_hex.lower(), "treasury": self.treasury, "window_s": int(self.window_s),
                "read_timeout_s": int(self.read_timeout_s), "contest_timeout_s": int(self.contest_timeout_s),
                "unbond_delay_s": int(self.unbond_delay_s), "monitor_interval_s": int(self.monitor_interval_s),
                "min_stake": str(int(self.min_stake)), "min_bond": str(int(self.min_bond)),
                "auth_max_age_s": int(self.auth_max_age_s), "max_gap_s": MAX_GAP_S, "kind_max_gap_s": KIND_MAX_GAP_S,
                "max_tolerance_bps": MAX_TOLERANCE_BPS, "bounty_bps": BOUNTY_BPS, "kinds": KINDS,
                "deposit_kinds": list(DEPOSIT_KINDS), "data_reasons": list(DATA_REASONS)}
