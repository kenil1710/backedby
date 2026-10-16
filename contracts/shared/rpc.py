# ==== shared rpc helpers: generated from contracts/shared/rpc.py by tools/inline_shared.py; edit there ====
# --- HTTP / JSON-RPC ----------------------------------------------------------

class ReadFailed(Exception):
    """An endpoint did not answer, or answered something that is not a
    JSON-RPC result or a revert. Transport-class: nothing is guessed."""


class Disagree(Exception):
    """The two RPCs of a chain answered differently."""


def _status(res: typing.Any) -> int:
    s = getattr(res, "status_code", None)
    if s is None:
        s = getattr(res, "status", None)
    return 0 if s is None else int(s)


def _raw(res: typing.Any) -> bytes:
    b = getattr(res, "body", None)
    if b is None:
        return b""
    if isinstance(b, bytes):
        return b
    return str(b).encode("utf-8")


def rpc_url_allowed(url: str) -> bool:
    for ch in CHAINS:
        if url in CHAINS[ch][1]:
            return True
    return False


def parse_batch(doc: typing.Any, n: int) -> list:
    """A JSON-RPC batch answer -> [["ok", result] | ["revert", None]] in call
    order. An error that is not an EVM revert raises ReadFailed."""
    if isinstance(doc, dict):
        doc = [doc]
    if not isinstance(doc, list):
        raise ReadFailed("batch")
    by_id = {}
    for item in doc:
        if isinstance(item, dict) and isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool):
            by_id[item["id"]] = item
    out = []
    for i in range(n):
        item = by_id.get(i)
        if item is None:
            raise ReadFailed("missing id")
        if "error" in item and item["error"] is not None:
            err = item["error"]
            msg = str(err.get("message", "")).lower() if isinstance(err, dict) else ""
            code = err.get("code") if isinstance(err, dict) else None
            if code == 3 or msg.find("revert") >= 0:
                out.append(["revert", None])
                continue
            raise ReadFailed("rpc error " + msg[:40])
        if "result" not in item:
            raise ReadFailed("no result")
        out.append(["ok", item["result"]])
    return out


def rpc_send(url: str, calls: list) -> list:
    """One endpoint, every call, in chunks of the endpoint's batch size. A
    chunk is retried (up to RPC_TRIES) on a transport failure, a 429 or 5xx,
    and on an answer that is not a usable JSON-RPC batch - free tiers answer
    a burst with HTTP 200 and a JSON-RPC error. An EVM revert is an answer,
    not a failure, and is never retried."""
    if not rpc_url_allowed(url):
        raise ReadFailed("rpc not allowed")
    cap = RPC_BATCH.get(url, 10)
    out = []
    i = 0
    while i < len(calls):
        chunk = calls[i:i + cap]
        body = json.dumps([{"jsonrpc": "2.0", "id": j, "method": chunk[j][0], "params": chunk[j][1]}
                           for j in range(len(chunk))])
        got = None
        why = ""
        for _ in range(RPC_TRIES):
            try:
                res = gl.nondet.web.request(url, method="POST", body=body,
                                            headers={"Content-Type": "application/json"})
            except Exception:
                why = "transport"
                continue
            st = _status(res)
            if st != 200:
                why = "http " + str(st)
                if st != 429 and st < 500:
                    break
                continue
            try:
                got = parse_batch(json.loads(_raw(res).decode("utf-8", errors="replace")), len(chunk))
                break
            except ReadFailed as e:
                why = str(e)
            except Exception:
                why = "json"
        if got is None:
            raise ReadFailed(why)
        out = out + got
        i += cap
    return out


def _block_of(r: typing.Any) -> typing.Any:
    if not isinstance(r, list) or r[0] != "ok" or not isinstance(r[1], dict):
        return None
    blk = r[1]
    try:
        num = int(str(blk.get("number")), 16)
        ts = int(str(blk.get("timestamp")), 16)
    except Exception:
        return None
    hsh = _hash32(blk.get("hash", ""))
    if hsh == "":
        return None
    return {"number": num, "hash": hsh, "timestamp": ts}


def _proj(call: list, r: typing.Any) -> typing.Any:
    """Only the fields this contract uses, so two honest RPCs compare equal."""
    if call[0] == "eth_getBlockByNumber":
        return _block_of(r)
    if call[0] == "eth_chainId":
        if isinstance(r, list) and r[0] == "ok" and isinstance(r[1], str):
            try:
                return int(r[1], 16)
            except Exception:
                return None
        return None
    if call[0] == "eth_call":
        if isinstance(r, list) and r[0] == "ok" and isinstance(r[1], str):
            t = r[1].lower()
            if t.startswith("0x") and _is_hex(t[2:]) and len(t) % 2 == 0:
                return ["ok", t]
            return ["bad", None]
        return ["revert", None]
    return r


def dual_read(chain: str, calls: list) -> list:
    """The same calls against BOTH RPCs of the chain; the projected answers
    must be identical, or Disagree is raised."""
    urls = CHAINS[chain][1]
    a = rpc_send(urls[0], calls)
    b = rpc_send(urls[1], calls)
    pa = [_proj(calls[i], a[i]) for i in range(len(calls))]
    pb = [_proj(calls[i], b[i]) for i in range(len(calls))]
    if _canon(pa) != _canon(pb):
        raise Disagree("rpc answers differ")
    return pa


def finalized_low(chain: str) -> typing.Any:
    """The LOWER of the two RPCs' finalized blocks, after checking both report
    the right chain id. None if either is unreadable or on the wrong chain.
    The two may legitimately differ by a block or two, so they are not
    compared with each other."""
    low = None
    for url in CHAINS[chain][1]:
        got = rpc_send(url, [["eth_getBlockByNumber", ["finalized", False]], ["eth_chainId", []]])
        blk = _block_of(got[0])
        cid = _proj(["eth_chainId", []], got[1])
        if blk is None or cid != CHAINS[chain][0]:
            return None
        if low is None or blk["number"] < low["number"]:
            low = blk
    return low


def eth_call(to: str, data: str, block: int) -> list:
    return ["eth_call", [{"to": to, "data": data}, hex(block)]]


def get_block(block: int) -> list:
    return ["eth_getBlockByNumber", [hex(block), False]]
# ==== end shared rpc ====
