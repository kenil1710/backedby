# v0.3.0
# { "Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import json
import typing


@gl.storage.allow
@dataclass
class Rec:
    rid: u64
    big: str
    other: str
    small: u64


class StrProbe(gl.contract.Contract):
    recs: gl.storage.TreeMap[u64, Rec]
    last: str

    def __init__(self) -> None:
        self.last = ""

    @gl.public.write
    def put(self, rid: int, n: int) -> typing.Any:
        items = [{"k": i, "v": "0x" + ("%064x" % (i * 7919))} for i in range(n)]
        s = json.dumps(items, sort_keys=True, separators=(",", ":"))
        self.recs[u64(rid)] = Rec(rid=u64(rid), big=s, other=s[::-1], small=u64(n))
        return {"len": len(s)}

    @gl.public.write
    def twice(self, rid: int, other_rid: int) -> typing.Any:
        r = self.recs[u64(rid)]
        a = r.big
        o = self.recs[u64(other_rid)]
        _ = o.small
        b = r.big
        c = r.big
        first = -1
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                first = i
                break
        ok_parse = True
        try:
            json.loads(b)
        except Exception:
            ok_parse = False
        self.last = json.dumps({"len_a": len(a), "len_b": len(b), "len_c": len(c), "ab": a == b, "ac": a == c, "first_diff": first, "parse_b": ok_parse})
        return json.loads(self.last)

    @gl.public.write
    def cross(self, rid: int, peer: str, peer_rid: int) -> typing.Any:
        r = self.recs[u64(rid)]
        a = r.big
        raw = gl.contract.get_at(Address(peer)).view().get_big(peer_rid)
        b = r.big
        first = -1
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                first = i
                break
        ok_parse = True
        try:
            json.loads(b)
        except Exception:
            ok_parse = False
        self.last = json.dumps({"len_a": len(a), "len_b": len(b), "ab": a == b, "first_diff": first, "parse_b": ok_parse, "peer_len": len(str(raw))})
        return json.loads(self.last)

    @gl.public.view
    def get_big(self, rid: int) -> str:
        return self.recs[u64(rid)].big

    @gl.public.view
    def get_last(self) -> str:
        return self.last
