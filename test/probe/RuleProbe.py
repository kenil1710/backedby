# v0.3.0
# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import hashlib
import json
import typing


def _canon(obj: typing.Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha(text: typing.Any) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


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
    vaults_json: str
    anchors_json: str
    registered_by: str
    registered_at: u64
    open_check: u64
    latest_check: u64
    latest_time: u64
    last_bad_time: u64
    last_monitor_at: u64
    checks_csv: str
    bonds_csv: str
    hist_n: u64


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


class RuleProbe(gl.contract.Contract):
    pairs: gl.storage.TreeMap[u64, Pair]
    checks: gl.storage.TreeMap[u64, Check]
    big: gl.storage.TreeMap[u64, str]
    last: str

    def __init__(self) -> None:
        self.last = ""

    @gl.public.write
    def put_check(self, cid: int, request_json: str, pair_json: str) -> typing.Any:
        pj = json.loads(pair_json)
        self.pairs[u64(1)] = Pair(pair_id=u64(1), key="k", kind="polygon", source_chain="ethereum", vault="v", source_token="t",
            source_decimals=u64(6), tolerance_bps=u64(0), max_gap_s=u64(120), label="l", dests_json=_canon(pj["dests"]),
            vaults_json=_canon(pj["vaults"]), anchors_json=_canon(pj["anchors"]), registered_by="r", registered_at=u64(1),
            open_check=u64(cid), latest_check=u64(0), latest_time=u64(0), last_bad_time=u64(0), last_monitor_at=u64(0),
            checks_csv="", bonds_csv="", hist_n=u64(0))
        self.checks[u64(cid)] = Check(check_id=u64(cid), pair_id=u64(1), purpose="MONITOR", bond_id=u64(0), filer="f", stake=u256(0),
            request_json=request_json, filed_at=u64(1), read_deadline=u64(9), status="OPEN", round=u64(1), verdict1="", ruling1_json="",
            ruled_at=u64(0), contest_deadline=u64(0), contester="", contest_stake=u256(0), contested_at=u64(0),
            contest_read_deadline=u64(0), ruling2_json="", verdict="", reason="", how="", final_at=u64(0), source_time=u64(0), payouts_json="")
        return {"len": len(request_json)}

    @gl.public.write
    def put_big(self, k: int, text: str) -> typing.Any:
        self.big[u64(k)] = text
        return {"len": len(text)}

    @gl.public.view
    def get_big(self, k: int) -> typing.Any:
        return json.loads(self.big[u64(k)])

    def _req(self, c: Check) -> dict:
        req = json.loads(c.request_json)
        req["ok"] = True
        return req

    @gl.public.write
    def rule_like(self, cid: int, peer: str, fix: int) -> typing.Any:
        c = self.checks[u64(cid)]
        out = {"fix": fix}
        if fix == 1:
            text = c.request_json
            req0 = json.loads(text)
        r = gl.contract.get_at(Address(peer)).view().get_big(1)
        out["peer"] = len(_canon(r))
        try:
            a = self._req(c) if fix != 1 else dict(req0, ok=True)
            out["sha"] = _sha(_canon(a))[:12]
        except Exception as e:
            out["first"] = "ERR " + str(e)[:80]
        p = self.pairs[c.pair_id]
        try:
            req = json.loads(c.request_json) if fix != 1 else req0
            out["second"] = len(req["terms_dests"])
        except Exception as e:
            out["second"] = "ERR " + str(e)[:80]
        out["tol"] = int(p.tolerance_bps)
        self.last = _canon(out)
        return out

    @gl.public.write
    def characterize(self, cid: int) -> typing.Any:
        out = {}
        c = self.checks[u64(cid)]
        rj1 = c.request_json
        p = self.pairs[c.pair_id]
        out["c_small_after_p"] = [int(c.read_deadline), c.status, c.purpose, int(c.pair_id)]
        rj2 = c.request_json
        out["c_req_after_p_same"] = rj1 == rj2
        out["c_req_after_p_diff_at"] = next((i for i in range(min(len(rj1), len(rj2))) if rj1[i] != rj2[i]), -1)
        a1 = p.anchors_json
        d1 = p.dests_json
        c2 = self.checks[u64(cid)]
        a2 = p.anchors_json
        d2 = p.dests_json
        out["p_strings_after_c_same"] = [a1 == a2, d1 == d2, len(a1), len(d1)]
        rj3 = c2.request_json
        out["fresh_ref_same"] = rj3 == rj1
        out["p_small_after_c"] = [int(p.tolerance_bps), int(p.open_check), p.kind]
        self.last = _canon(out)
        return out

    @gl.public.write
    def writes(self, cid: int, n: int) -> typing.Any:
        text = _canon([{"i": i, "h": _sha(i)} for i in range(n)])
        c = self.checks[u64(cid)]
        p = self.pairs[c.pair_id]
        _ = p.anchors_json
        c.ruling1_json = text
        c2 = self.checks[u64(cid)]
        p.checks_csv = text
        self.last = _canon({"len": len(text), "written_via_old_ref_ok": self.checks[u64(cid)].ruling1_json == text,
                            "pair_write_ok": self.pairs[u64(1)].checks_csv == text, "c2_read_ok": c2.ruling1_json == text})
        return json.loads(self.last)

    @gl.public.view
    def check_stored(self, cid: int, n: int) -> typing.Any:
        text = _canon([{"i": i, "h": _sha(i)} for i in range(n)])
        return {"ruling1_ok": self.checks[u64(cid)].ruling1_json == text, "csv_ok": self.pairs[u64(1)].checks_csv == text}

    @gl.public.view
    def get_last(self) -> str:
        return self.last
