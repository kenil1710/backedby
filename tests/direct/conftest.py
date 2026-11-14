"""Direct Mode (genlayer-test) helpers for BackedBy's ChainReader: the deployed
bytes (build/ChainReader.py) run on the official SDK; every allowlisted RPC is
answered by a mock chain keyed by its URL, so a test can take one RPC down,
make it lie, or let a validator see different data than the leader."""
import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "ChainReader.py"
SDK_VERSION = "v0.2.16"
# genlayer-test's Direct Mode runs contracts on the genvm v0.2 SDK; ChainReader is
# written for Studio's runner (pinned by a hash no published test release carries),
# so Direct Mode runs the deployed bytes with only these spellings changed in a
# temporary copy; every rule and read is the deployed code:
ADAPT = [
    ('"Depends": "py-genlayer:', None),
    ("@gl.storage.allow\n", "@gl.storage.allow_storage\n"),
    ("gl.contract.Contract", "gl.Contract"),
    ("gl.message.raw", "gl.message_raw"),
]


def _consts():
    tree = ast.parse(BUILD.read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:
                pass
    return out


C = _consts()
CHAINS = C["CHAINS"]
W = lambda n: "0x" + "%064x" % int(n)
A = lambda a: "0x" + "0" * 24 + a[2:].lower()
P = lambda a: a[2:].lower().rjust(64, "0")
U = lambda n: "%064x" % int(n)
NOW_ISO = "2026-11-14T12:00:00Z"
NOW_TS = 1_794_139_200


def abi_bytes(h):
    d = h[2:]
    return "0x" + U(32) + U(len(d) // 2) + d + "0" * ((64 - len(d) % 64) % 64)


def abi_string(s):
    return abi_bytes("0x" + s.encode().hex())


class Chain:
    """One chain as an RPC sees it: a finalized head, block timestamps, and
    eth_call answers keyed by (to, data) or by (to, selector) -> fn(data)."""

    def __init__(self, cid, fin):
        self.cid = cid
        self.fin = fin
        self.calls = {}
        self.fns = {}

    def answer(self, req):
        m, p, i = req["method"], req["params"], req["id"]
        if m == "eth_chainId":
            return {"jsonrpc": "2.0", "id": i, "result": hex(self.cid)}
        if m == "eth_getBlockByNumber":
            n = self.fin if p[0] == "finalized" else int(p[0], 16)
            return {"jsonrpc": "2.0", "id": i, "result": {"number": hex(n), "hash": "0x" + "%064x" % (n * 31 + self.cid),
                                                          "timestamp": hex(NOW_TS - 600 - (self.fin - n))}}
        if m == "eth_call":
            to, data = p[0]["to"].lower(), p[0]["data"]
            r = self.calls.get((to, data))
            if r is None and (to, data[:10]) in self.fns:
                r = self.fns[(to, data[:10])](data)
            if r is None:
                return {"jsonrpc": "2.0", "id": i, "error": {"code": 3, "message": "execution reverted"}}
            return {"jsonrpc": "2.0", "id": i, "result": r}
        return {"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "no"}}


class Net:
    def __init__(self):
        self.chains = {name: Chain(cid, 1000 + k * 10) for k, (name, (cid, _)) in enumerate(CHAINS.items())}
        self.by_url = {}
        for name, (cid, urls) in CHAINS.items():
            for u in urls:
                self.by_url[u] = name
        for u in C["SCAN_RPCS"]:
            self.by_url.setdefault(u, "ethereum")
        self.down = set()
        self.lie = {}             # url -> fn(req, answer) -> answer

    def handler(self, data):
        url = data.get("url", "")
        if url in self.down or url not in self.by_url:
            return {"ok": {"response": {"status": 503, "headers": {}, "body": b"down"}}}
        ch = self.chains[self.by_url[url]]
        body = data.get("body")
        req = json.loads(body.decode() if isinstance(body, (bytes, bytearray)) else body)
        fix = self.lie.get(url, lambda r, a: a)
        out = [fix(r, ch.answer(r)) for r in req] if isinstance(req, list) else fix(req, ch.answer(req))
        return {"ok": {"response": {"status": 200, "headers": {}, "body": json.dumps(out).encode()}}}

    def call(self, chain, to, data, result):
        self.chains[chain].calls[(to.lower(), data)] = result


def warp(vm, iso):
    vm.warp(iso)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and isinstance(getattr(gl, "message_raw", None), dict):
        gl.message_raw["datetime"] = iso


@pytest.fixture
def net(direct_vm):
    n = Net()
    direct_vm._live_web_handler = n.handler
    return n


@pytest.fixture
def reader(direct_vm, direct_deploy, direct_owner, tmp_path):
    text = BUILD.read_text()
    lines = text.split("\n")
    assert lines[0] == "# v0.3.0" and ADAPT[0][0] in lines[1]
    lines[1] = '# { "Depends": "py-genlayer:latest" }'
    text = "\n".join(lines)
    for old, new in ADAPT[1:]:
        assert old in text, old
        text = text.replace(old, new)
    path = tmp_path / "ChainReader.py"
    path.write_text(text)
    direct_vm.sender = direct_owner
    direct_vm.warp(NOW_ISO)
    c = direct_deploy(str(path), sdk_version=SDK_VERSION)
    warp(direct_vm, NOW_ISO)
    return c


# --- real addresses, mapped on the mock chains --------------------------------
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WH_ARB_USDC = "0xc96f2715e2a242d50d1b0bc923dbe1740b8ecf18"
GHO = "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f"
BASE_GHO = "0x6bb7a212910682dcfdbd5bcbb3e28fb4e8da10ee"
GHO_POOL = "0x06179f7c1be40863405f374e7f5f8806c728660a"
BASE_GHO_POOL = "0x98217a06721ebf727f2c8d9ad7718ec28b7aae34"


def map_wormhole(n):
    wid, tb = C["WH_DESTS"]["arbitrum"]
    eb = C["WH_ETH_BRIDGE"]
    n.call("ethereum", eb, C["S_WH_BRIDGE_OF"] + U(wid), A(tb))
    n.call("ethereum", eb, C["S_WH_OUTSTANDING"] + P(USDC), W(10 ** 12))
    n.call("ethereum", USDC, C["S_DECIMALS"], W(6))
    n.call("arbitrum", tb, C["S_WH_WRAPPED"] + U(2) + P(USDC), A(WH_ARB_USDC))
    n.call("arbitrum", tb, C["S_WH_IS_WRAPPED"] + P(WH_ARB_USDC), W(1))
    n.call("arbitrum", WH_ARB_USDC, C["S_WH_CHAIN_ID"], W(2))
    n.call("arbitrum", WH_ARB_USDC, C["S_WH_NATIVE"], A(USDC))
    n.call("arbitrum", tb, C["S_WH_BRIDGE_OF"] + U(2), A(eb))
    n.call("arbitrum", WH_ARB_USDC, C["S_DECIMALS"], W(6))


def map_ccip(n):
    dsel, dtar = C["CCIP_DESTS"]["base"]
    es = C["CCIP_ETH_SELECTOR"]
    rp = lambda s, pool: C["S_CCIP_IS_REMOTE_POOL"] + U(s) + U(64) + U(32) + P(pool)
    n.call("ethereum", C["CCIP_ETH_TAR"], C["S_CCIP_GET_POOL"] + P(GHO), A(GHO_POOL))
    n.call("ethereum", GHO, C["S_DECIMALS"], W(18))
    n.call("ethereum", GHO_POOL, C["S_CCIP_TYPE"], abi_string("LockReleaseTokenPool 1.5.1"))
    n.call("ethereum", GHO_POOL, C["S_CCIP_GET_TOKEN"], A(GHO))
    n.call("ethereum", GHO_POOL, C["S_CCIP_REMOTE_TOKEN"] + U(dsel), abi_bytes(A(BASE_GHO)))
    n.call("ethereum", GHO_POOL, rp(dsel, BASE_GHO_POOL), W(1))
    n.call("base", dtar, C["S_CCIP_GET_POOL"] + P(BASE_GHO), A(BASE_GHO_POOL))
    n.call("base", BASE_GHO, C["S_DECIMALS"], W(18))
    n.call("base", BASE_GHO_POOL, C["S_CCIP_TYPE"], abi_string("BurnMintTokenPool 1.5.1"))
    n.call("base", BASE_GHO_POOL, C["S_CCIP_GET_TOKEN"], A(BASE_GHO))
    n.call("base", BASE_GHO_POOL, C["S_CCIP_REMOTE_TOKEN"] + U(es), abi_bytes(A(GHO)))
    n.call("base", BASE_GHO_POOL, rp(es, GHO_POOL), W(1))
