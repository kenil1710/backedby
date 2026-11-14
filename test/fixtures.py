"""Builders for the offline suite: six mock chains (each served by its two
allowlisted RPC URLs), every bridge kind's on-chain mapping, tokens whose
balances and supplies can change per block, and a wired deployment
(ChainReader, a DEMO or CANONICAL registry, CollateralGate)."""
import hashlib

import stub
import world

CR = world.module("ChainReader")
RG = world.module("BackedByRegistry")
GT = world.module("CollateralGate")

NOW_ISO = "2026-10-17T12:00:00Z"
NOW = CR._epoch_from_iso(NOW_ISO)
GEN = 10 ** 18
REVERT = stub.MockChain.REVERT
BLOCK_TIME = {"ethereum": 12, "arbitrum": 1, "optimism": 2, "base": 2, "polygon": 2, "moonbeam": 6}
START = {"ethereum": 26_000_000, "arbitrum": 500_000_000, "optimism": 150_000_000, "base": 50_000_000,
         "polygon": 95_000_000, "moonbeam": 16_000_000}
for _c in CR.CHAINS:      # the chains that only carry USDT0: 2 s blocks
    BLOCK_TIME.setdefault(_c, 2)
    START.setdefault(_c, 10_000_000)


def addr(n):
    return "0x" + hashlib.sha256(b"addr%d" % n).hexdigest()[:40]


OPERATOR = addr(1)
CHALLENGER = addr(2)
CONTESTER = addr(3)
STRANGER = addr(4)
PATROL = addr(5)
DEPLOYER = "0x" + "d" * 40

# source tokens
USDC = addr(0x0dc0)
WBTC = addr(0xb7c)
DAI = addr(0xda1)
LINK = addr(0x11c)
USDT = addr(0x0d07)
# LayerZero OFT (USDT0-style): adapter on Ethereum, OFT contracts on the destinations
USDT0_ADAPTER = addr(0x0f7a)
POL_OFT = addr(0x0f7b)
ARB_OFT = addr(0x0f7c)
FAKE_ADAPTER = addr(0x0bad1)
FAKE_OFT = addr(0x0bad2)
# vaults / gateways
ARB_GW = "0xa3a7b6f88361f48403514059f1f16c8e78d60eec"      # the standard (escrow) gateway
ARB_DAI_GW = "0xd3b5b60020504bc3489d6949d545893982ba3011"  # L1DaiGateway
ARB_DAI_ESCROW = addr(0xab)
POL_PRED = addr(0x9e)
OP_DAI_ESCROW = addr(0xde)
NOMAD_ETH_REG = addr(0x9e9)
NOMAD_BEAM_REG = addr(0x9ea)
# destination tokens
ARB_USDC = addr(0x1001)
ARB_WBTC = addr(0x1002)
ARB_DAI = addr(0x1003)
OP_USDC = addr(0x2001)
OP_USDC2 = addr(0x2002)       # a second Standard Bridge representation of the same L1 token
OP_FAKE = addr(0x2003)        # claims remoteToken=USDC and bridge=L2StandardBridge, mints at will
OP_DAI = addr(0x2004)
BASE_USDC = addr(0x3001)
POL_USDC = addr(0x4001)
POL_USDT = addr(0x4002)
ARB_USDT0 = addr(0x1004)
POL_FAKE_USDT = addr(0x4003)
BEAM_USDC = addr(0x5001)
PRED_TYPE = "0x8ae85d849167ff996c04040c44924fd364217285e4cad818292c7ac37c0a345b"


def data_fault(chain, on=True):
    """Both RPCs of `chain` answer every eth_call with an empty result: a
    deterministic CALL_FAILED (about the pair, not the transport)."""
    for u in CR.CHAINS[chain][1]:
        if on:
            stub.WEB.tamper[u] = lambda req, ans: dict(ans, result="0x") if req["method"] == "eth_call" else ans
        else:
            stub.WEB.tamper.pop(u, None)


def w(n):
    return "0x" + ("%064x" % int(n))


def wa(a):
    return "0x" + "0" * 24 + a[2:].lower()


def F_wa(a):
    return wa(a)


def arg(data, i):
    """i-th 32-byte argument of calldata as an int."""
    h = data[10 + 64 * i: 10 + 64 * (i + 1)]
    return int(h, 16) if h else 0


def arg_addr(data, i):
    return "0x" + ("%040x" % arg(data, i))


class Net:
    """All six chains. `val(chain, key, block)` reads a value that may have
    been changed at a block via `set(chain, key, value, from_block)`."""

    def __init__(self, w_):
        self.w = w_
        self.mc = {}
        self.vals = {}
        stub.WEB.reset()
        for ch, (cid, urls) in CR.CHAINS.items():
            m = stub.MockChain(cid, START[ch], NOW - 900)
            m.batch_cap = 10
            self.mc[ch] = m
            for u in urls:
                stub.WEB.chains[u] = m
        self.head = {ch: START[ch] for ch in CR.CHAINS}

    # --- blocks -------------------------------------------------------------
    def mine_to(self, ts, finalize=True):
        """Every chain gets blocks up to timestamp ts (one per block time),
        and its finalized block moves to the newest."""
        for ch, m in self.mc.items():
            n = self.head[ch]
            t0 = m.blocks[n][1]
            while t0 + BLOCK_TIME[ch] <= ts:
                n += 1
                t0 += BLOCK_TIME[ch]
                m.set_block(n, t0)
            self.head[ch] = n
            if finalize:
                m.finalized = n

    def block_at(self, ch, ts):
        """The last block on ch with timestamp <= ts."""
        m = self.mc[ch]
        best = None
        for n, (_, t) in m.blocks.items():
            if t <= ts and (best is None or n > best):
                best = n
        return best

    def first_at(self, ch, ts):
        m = self.mc[ch]
        best = None
        for n, (_, t) in m.blocks.items():
            if t >= ts and (best is None or n < best):
                best = n
        return best

    def ts(self, ch, n):
        return self.mc[ch].blocks[n][1]

    # --- values ---------------------------------------------------------------
    def set(self, ch, key, value, from_block=0):
        self.vals.setdefault((ch, key), []).append((from_block, value))
        self.vals[(ch, key)].sort(key=lambda x: x[0])

    def val(self, ch, key, blk, default=None):
        best = default
        for b, v in self.vals.get((ch, key), []):
            if b <= blk:
                best = v
        return best

    def fn(self, ch, to, sel, f):
        self.mc[ch].fns[(to.lower(), sel)] = f
        if self.mc[ch].code.get(to.lower()) is None:
            self.mc[ch].code[to.lower()] = "0x6080"

    # --- tokens ---------------------------------------------------------------
    def token(self, ch, t, decimals, supply=0):
        self.set(ch, ("dec", t), decimals)
        self.set(ch, ("supply", t), supply)
        self.fn(ch, t, CR.S_DECIMALS, lambda d, b, ch=ch, t=t: w(self.val(ch, ("dec", t), b)))
        self.fn(ch, t, CR.S_SUPPLY, lambda d, b, ch=ch, t=t: w(self.val(ch, ("supply", t), b)))
        self.fn(ch, t, CR.S_BALANCE, lambda d, b, ch=ch, t=t: w(self.val(ch, ("bal", t, arg_addr(d, 0)), b, 0)))

    def balance(self, ch, t, holder, amount, from_block=0):
        self.set(ch, ("bal", t, holder.lower()), amount, from_block)

    def supply(self, ch, t, amount, from_block=0):
        self.set(ch, ("supply", t), amount, from_block)

    def decimals(self, ch, t, d, from_block=0):
        self.set(ch, ("dec", t), d, from_block)

    # --- bridges ----------------------------------------------------------------
    def arbitrum(self, l1, l2, gw=None, escrow=None, l2_router_says=None):
        gw = gw or ARB_GW
        prev_gw = getattr(self, "_arb_gw", {})
        prev_gw[l1.lower()] = (gw, l2, escrow, l2_router_says or l2)
        self._arb_gw = prev_gw
        g = self._arb_gw
        self.fn("ethereum", CR.ARB_L1_ROUTER, CR.S_GET_GATEWAY,
                lambda d, b: wa(g.get(arg_addr(d, 0), ("0x" + "0" * 40,))[0]))
        self.fn("ethereum", CR.ARB_L1_ROUTER, CR.S_CALC_L2,
                lambda d, b: wa(g[arg_addr(d, 0)][1]) if arg_addr(d, 0) in g else wa("0x" + "0" * 40))
        self.fn("arbitrum", CR.ARB_L2_ROUTER, CR.S_CALC_L2,
                lambda d, b: wa(g[arg_addr(d, 0)][3]) if arg_addr(d, 0) in g else wa("0x" + "0" * 40))
        if escrow:
            self.fn("ethereum", gw, CR.S_L1_ESCROW, lambda d, b: wa(escrow))
        else:
            self.fn("ethereum", gw, CR.S_L1_ESCROW, lambda d, b: REVERT)

    def opstack(self, kind, l1, l2, legacy=False, bridge=None, remote=None):
        ch = kind
        br = bridge or CR.L2_STD_BRIDGE
        rt = remote or l1
        if legacy:
            self.fn(ch, l2, CR.S_REMOTE_TOKEN, lambda d, b: REVERT)
            self.fn(ch, l2, CR.S_BRIDGE, lambda d, b: REVERT)
            self.fn(ch, l2, CR.S_L1_TOKEN, lambda d, b: wa(rt))
            self.fn(ch, l2, CR.S_L2_BRIDGE, lambda d, b: wa(br))
        else:
            self.fn(ch, l2, CR.S_REMOTE_TOKEN, lambda d, b: wa(rt))
            self.fn(ch, l2, CR.S_BRIDGE, lambda d, b: wa(br))
            self.fn(ch, l2, CR.S_L1_TOKEN, lambda d, b: wa(rt))
            self.fn(ch, l2, CR.S_L2_BRIDGE, lambda d, b: wa(br))
        vault = CR.OP_L1_BRIDGE if kind == "optimism" else CR.BASE_L1_BRIDGE
        self.fn("ethereum", vault, CR.S_DEPOSITS,
                lambda d, b, vault=vault: w(self.val("ethereum", ("dep", vault, arg_addr(d, 0), arg_addr(d, 1)), b, 0)))
        return vault

    def deposits(self, vault, l1, l2, amount, from_block=0):
        self.set("ethereum", ("dep", vault, l1.lower(), l2.lower()), amount, from_block)

    def op_dai(self, l1, l2, escrow=None):
        esc = escrow or OP_DAI_ESCROW
        self.fn("ethereum", CR.OP_DAI_L1_BRIDGE, CR.S_L1_TOKEN, lambda d, b: wa(l1))
        self.fn("ethereum", CR.OP_DAI_L1_BRIDGE, CR.S_L2_TOKEN, lambda d, b: wa(l2))
        self.fn("ethereum", CR.OP_DAI_L1_BRIDGE, CR.S_ESCROW, lambda d, b: wa(esc))
        self.fn("optimism", CR.OP_DAI_L2_BRIDGE, CR.S_L1_TOKEN, lambda d, b: wa(l1))
        self.fn("optimism", CR.OP_DAI_L2_BRIDGE, CR.S_L2_TOKEN, lambda d, b: wa(l2))
        self.fn("optimism", CR.OP_DAI_L2_BRIDGE, CR.S_L1_DAI_BRIDGE, lambda d, b: wa(CR.OP_DAI_L1_BRIDGE))
        return esc

    def polygon(self, l1, child, pred=None, child_says=None):
        pr = pred or POL_PRED
        m = getattr(self, "_pol", {})
        m[l1.lower()] = (child, child_says or l1)
        self._pol = m
        self.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_ROOT_TO_CHILD,
                lambda d, b: wa(m[arg_addr(d, 0)][0]) if arg_addr(d, 0) in m else wa("0x" + "0" * 40))
        self.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TOKEN_TO_TYPE,
                lambda d, b: PRED_TYPE if arg_addr(d, 0) in m else w(0))
        self.fn("ethereum", CR.POL_ROOT_MANAGER, CR.S_TYPE_TO_PRED, lambda d, b: wa(pr))
        rev = {}
        for k, v in m.items():
            rev[v[0].lower()] = v[1]
        self.fn("polygon", CR.POL_CHILD_MANAGER, CR.S_CHILD_TO_ROOT,
                lambda d, b: wa(rev[arg_addr(d, 0)]) if arg_addr(d, 0) in rev else wa("0x" + "0" * 40))
        return pr

    def oft(self, dest, l1, l2, adapter, oft, native=False, peer_back=None, endpoint=None, adapter_peer=None,
            via_adapter=False):
        """An OFT pair: l2.oftContract() = oft (unless native), oft.peers(eth) = adapter,
        adapter.token() = l1 and adapter.peers(dest) = oft, both on the endpoint.
        via_adapter: l2 has no oftContract(); only oft.token() = l2 links them
        (Hedera's HTS USDT0), so authentication is asked for the OFT."""
        ep = endpoint or CR.LZ_ENDPOINTS[dest]
        if via_adapter:
            self.fn(dest, oft, CR.S_OFT_CONTRACT, lambda d, b: REVERT)
            self.fn(dest, oft, CR.S_TOKEN, lambda d, b: F_wa(l2))
        elif not native:
            self.fn(dest, l2, CR.S_OFT_CONTRACT, lambda d, b: F_wa(oft))
            self.fn(dest, oft, CR.S_TOKEN, lambda d, b: F_wa(l2))
        else:
            self.fn(dest, l2, CR.S_OFT_CONTRACT, lambda d, b: REVERT)
            self.fn(dest, l2, CR.S_TOKEN, lambda d, b: F_wa(l2))
        o = l2 if native else oft
        back = peer_back or adapter
        self.fn(dest, o, CR.S_PEERS, lambda d, b: F_wa(back) if arg(d, 0) == CR.LZ_EID["ethereum"] else w(0))
        self.fn(dest, o, CR.S_ENDPOINT, lambda d, b: F_wa(ep))
        peers = getattr(self, "_oft_peers", {})
        peers.setdefault(adapter.lower(), {})[CR.LZ_EID[dest]] = adapter_peer or o
        self._oft_peers = peers
        self.fn("ethereum", adapter, CR.S_TOKEN, lambda d, b: F_wa(l1))
        self.fn("ethereum", adapter, CR.S_ENDPOINT, lambda d, b: F_wa(CR.LZ_ENDPOINT))
        self.fn("ethereum", adapter, CR.S_PEERS,
                lambda d, b, a=adapter.lower(): F_wa(peers[a].get(arg(d, 0), "0x" + "0" * 40)))
        return adapter

    def scan_rpcs(self):
        for u in CR.SCAN_RPCS:
            stub.WEB.chains[u] = self.mc["ethereum"]
        self.fn("ethereum", CR.MULTICALL3, CR.S_AGGREGATE3, lambda d, b: _mc_answer(self, d, b))
        self.lz_supported = set()
        self.fn("ethereum", CR.LZ_ENDPOINT, CR.S_IS_SUPPORTED_EID, lambda d, b: w(1 if arg(d, 0) in self.lz_supported else 0))

    def wormhole(self, dest, l1, l2, origin=None, wrapped_map=None, eth_registers=True, dest_registers=True,
                 is_wrapped=True):
        wid, tb = CR.WH_DESTS[dest]
        ethreg = getattr(self, "_wh_eth", {})
        ethreg[wid] = tb if eth_registers else "0x" + "0" * 40
        self._wh_eth = ethreg
        self.fn("ethereum", CR.WH_ETH_BRIDGE, CR.S_WH_BRIDGE_OF, lambda d, b: wa(ethreg.get(arg(d, 0), "0x" + "0" * 40)))
        self.fn("ethereum", CR.WH_ETH_BRIDGE, CR.S_WH_OUTSTANDING,
                lambda d, b: w(self.val("ethereum", ("whled", arg_addr(d, 0)), b, 0)))
        wm = getattr(self, "_wh_wrapped", {})
        wm[(dest, l1.lower())] = wrapped_map or l2
        self._wh_wrapped = wm
        self.fn(dest, tb, CR.S_WH_WRAPPED,
                lambda d, b, dest=dest: wa(wm.get((dest, arg_addr(d, 1)), "0x" + "0" * 40)) if arg(d, 0) == 2 else wa("0x" + "0" * 40))
        iw = getattr(self, "_wh_is", set())
        if is_wrapped:
            iw.add((dest, l2.lower()))
        self._wh_is = iw
        self.fn(dest, tb, CR.S_WH_IS_WRAPPED, lambda d, b, dest=dest: w(1 if (dest, arg_addr(d, 0)) in iw else 0))
        self.fn(dest, tb, CR.S_WH_BRIDGE_OF,
                lambda d, b: wa(CR.WH_ETH_BRIDGE if dest_registers and arg(d, 0) == 2 else "0x" + "0" * 40))
        o = origin or (2, l1)
        self.fn(dest, l2, CR.S_WH_CHAIN_ID, lambda d, b: w(o[0]))
        self.fn(dest, l2, CR.S_WH_NATIVE, lambda d, b: wa(o[1]))
        return CR.WH_ETH_BRIDGE

    def wh_ledger(self, l1, amount, from_block=0):
        self.set("ethereum", ("whled", l1.lower()), amount, from_block)

    def ccip(self, dest, l1, l2, pool, dpool, src_type="LockReleaseTokenPool 1.5.1", dst_type="BurnMintTokenPool 1.5.1",
             remote_token=None, back_token=None, src_names_dest=True, dest_names_src=True):
        dsel, dtar = CR.CCIP_DESTS[dest]
        es = CR.CCIP_ETH_SELECTOR
        pools = getattr(self, "_ccip_pools", {})
        pools[l1.lower()] = pool
        self._ccip_pools = pools
        self.fn("ethereum", CR.CCIP_ETH_TAR, CR.S_CCIP_GET_POOL, lambda d, b: wa(pools.get(arg_addr(d, 0), "0x" + "0" * 40)))
        self.fn("ethereum", pool, CR.S_CCIP_TYPE, lambda d, b: abi_string(src_type))
        self.fn("ethereum", pool, CR.S_CCIP_GET_TOKEN, lambda d, b: wa(l1))
        rt = getattr(self, "_ccip_rt", {})
        rt[(pool.lower(), dsel)] = remote_token or l2
        self._ccip_rt = rt
        self.fn("ethereum", pool, CR.S_CCIP_REMOTE_TOKEN,
                lambda d, b, pool=pool: abi_bytes(wa(rt[(pool.lower(), arg(d, 0))])) if (pool.lower(), arg(d, 0)) in rt else abi_bytes("0x"))
        rp = getattr(self, "_ccip_rp", set())
        if src_names_dest:
            rp.add(("ethereum", pool.lower(), dsel, dpool.lower()))
        if dest_names_src:
            rp.add((dest, dpool.lower(), es, pool.lower()))
        self._ccip_rp = rp
        self.fn("ethereum", pool, CR.S_CCIP_IS_REMOTE_POOL,
                lambda d, b, pool=pool: w(1 if ("ethereum", pool.lower(), arg(d, 0), "0x" + d[10 + 64 * 4 - 40:10 + 64 * 4]) in rp else 0))
        self.fn(dest, dpool, CR.S_CCIP_IS_REMOTE_POOL,
                lambda d, b, dest=dest, dpool=dpool: w(1 if (dest, dpool.lower(), arg(d, 0), "0x" + d[10 + 64 * 4 - 40:10 + 64 * 4]) in rp else 0))
        sup = getattr(self, "_ccip_sup", {})
        sup.setdefault(pool.lower(), [])
        if dsel not in sup[pool.lower()]:
            sup[pool.lower()].append(dsel)
        self._ccip_sup = sup
        self.fn("ethereum", pool, CR.S_CCIP_CHAINS, lambda d, b, pool=pool: abi_u64s(sup[pool.lower()]))
        dp = getattr(self, "_ccip_dp", {})
        dp[(dest, l2.lower())] = dpool
        self._ccip_dp = dp
        self.fn(dest, dtar, CR.S_CCIP_GET_POOL, lambda d, b, dest=dest: wa(dp.get((dest, arg_addr(d, 0)), "0x" + "0" * 40)))
        self.fn(dest, dpool, CR.S_CCIP_TYPE, lambda d, b: abi_string(dst_type))
        self.fn(dest, dpool, CR.S_CCIP_GET_TOKEN, lambda d, b: wa(l2))
        self.fn(dest, dpool, CR.S_CCIP_REMOTE_TOKEN,
                lambda d, b: abi_bytes(wa(back_token or l1)) if arg(d, 0) == es else abi_bytes("0x"))
        return pool

    def ccip_support(self, pool, selectors):
        self._ccip_sup[pool.lower()] = list(selectors)

    def por(self, l1, answer, updated_at, decimals=8, supply_token=None, feed=None):
        feed = feed or POR_FEED
        CR.POR_FEEDS[l1.lower()] = (feed, (supply_token or l1).lower())
        self.set("ethereum", ("por", feed), (answer, updated_at))
        self.fn("ethereum", feed, CR.S_LATEST_ROUND,
                lambda d, b: "0x" + "%064x" % 7 + "%064x" % self.val("ethereum", ("por", feed), b)[0] + "%064x" % 1
                + "%064x" % self.val("ethereum", ("por", feed), b)[1] + "%064x" % 7)
        self.fn("ethereum", feed, CR.S_DECIMALS, lambda d, b: w(decimals))

    def nomad(self, l1, rep, remote=None, domain=None):
        dom = domain or CR.NOMAD_ETH_DOMAIN
        rem = remote or CR.NOMAD_ETH_ROUTER
        self.fn("moonbeam", CR.NOMAD_BEAM_ROUTER, CR.S_TOKEN_REGISTRY, lambda d, b: wa(NOMAD_BEAM_REG))
        self.fn("moonbeam", CR.NOMAD_BEAM_ROUTER, CR.S_REMOTES, lambda d, b: wa(rem))
        self.fn("moonbeam", NOMAD_BEAM_REG, CR.S_GET_TOKEN_ID,
                lambda d, b: w(dom) + wa(l1)[2:] if arg_addr(d, 0) == rep.lower() else w(0) + w(0)[2:])
        self.fn("moonbeam", NOMAD_BEAM_REG, CR.S_GET_LOCAL,
                lambda d, b: wa(rep) if arg_addr(d, 1) == l1.lower() and arg(d, 0) == CR.NOMAD_ETH_DOMAIN else wa("0x" + "0" * 40))
        self.fn("ethereum", CR.NOMAD_ETH_ROUTER, CR.S_TOKEN_REGISTRY, lambda d, b: wa(NOMAD_ETH_REG))
        self.fn("ethereum", NOMAD_ETH_REG, CR.S_GET_TOKEN_ID,
                lambda d, b: w(CR.NOMAD_ETH_DOMAIN) + wa(arg_addr(d, 0))[2:])
        return CR.NOMAD_ETH_ROUTER


def abi_bytes(h):
    d = h[2:] if h.startswith("0x") else h
    return "0x" + "%064x" % 32 + "%064x" % (len(d) // 2) + d + "0" * ((64 - len(d) % 64) % 64)


def abi_string(s):
    return abi_bytes("0x" + s.encode().hex())


def abi_u64s(xs):
    return "0x" + "%064x" % 32 + "%064x" % len(xs) + "".join("%064x" % int(x) for x in xs)


# v2 fixtures: source tokens and their bridged tokens
GHO = addr(0x6e0)
ARB_GHO = addr(0x6e1)
BASE_GHO = addr(0x6e2)
GHO_POOL = addr(0x6e3)
ARB_GHO_POOL = addr(0x6e4)
BASE_GHO_POOL = addr(0x6e5)
WH_ARB_USDC = addr(0x7e1)
WH_POL_USDC = addr(0x7e2)
WH_ARB_WETH = addr(0x7e3)
WETH = addr(0x7e0)
POR_FEED = addr(0x9f0)


def _mc_answer(net, data, blk):
    """Multicall3.aggregate3 on the mock Ethereum: decode the calls, answer
    each from the chain itself, encode (bool, bytes)[]."""
    t = data[10:]
    base = int(t[0:64], 16) * 2
    n = int(t[base:base + 64], 16)
    start = base + 64
    res = []
    for i in range(n):
        o = start + int(t[start + 64 * i:start + 64 * (i + 1)], 16) * 2
        target = "0x" + t[o + 24:o + 64]
        bo = o + int(t[o + 128:o + 192], 16) * 2
        ln = int(t[bo:bo + 64], 16)
        cd = "0x" + t[bo + 64:bo + 64 + 2 * ln]
        a = net.mc["ethereum"].answer({"jsonrpc": "2.0", "id": 0, "method": "eth_call",
                                       "params": [{"to": target, "data": cd}, hex(blk)]})
        r = a.get("result")
        res.append((r is not None and "error" not in a, (r or "0x")[2:]))
    head = "%064x" % 32 + "%064x" % n
    offs = ""
    body = ""
    cur = n * 32
    for ok, r in res:
        offs += "%064x" % cur
        padded = r + "0" * ((64 - len(r) % 64) % 64)
        el = "%064x" % (1 if ok else 0) + "%064x" % 64 + "%064x" % (len(r) // 2) + padded
        body += el
        cur += len(el) // 2
    return "0x" + head + offs + body


class Setup:
    """A wired deployment on a fresh world with every bridge kind mapped."""

    def __init__(self, mode="DEMO", max_age=3600, max_tol=50):
        self.w = world.new_world(now_iso=NOW_ISO)
        self.net = Net(self.w)
        n = self.net
        self.reader = self.w.deploy("ChainReader", sender=DEPLOYER)
        self.reg = self.w.deploy("BackedByRegistry", mode, self.reader, sender=DEPLOYER)
        self.gate = self.w.deploy("CollateralGate", self.reg, max_age, max_tol, sender=DEPLOYER)
        self.mode = mode
        # tokens
        n.token("ethereum", USDC, 6)
        n.token("ethereum", WBTC, 8)
        n.token("ethereum", DAI, 18)
        n.token("ethereum", LINK, 18)
        n.token("arbitrum", ARB_USDC, 6, 1_000_000 * 10 ** 6)
        n.token("arbitrum", ARB_WBTC, 8, 100 * 10 ** 8)
        n.token("arbitrum", ARB_DAI, 18, 5_000 * GEN)
        n.token("optimism", OP_USDC, 6, 500_000 * 10 ** 6)
        n.token("optimism", OP_USDC2, 6, 0)
        n.token("optimism", OP_FAKE, 6, 10 ** 15)
        n.token("optimism", OP_DAI, 18, 1_000 * GEN)
        n.token("base", BASE_USDC, 6, 200_000 * 10 ** 6)
        n.token("polygon", POL_USDC, 6, 300_000 * 10 ** 6)
        n.token("moonbeam", BEAM_USDC, 6, 2_000_000 * 10 ** 6)
        n.token("ethereum", USDT, 6)
        n.token("polygon", POL_USDT, 6, 700_000 * 10 ** 6)
        n.token("arbitrum", ARB_USDT0, 6, 800_000 * 10 ** 6)
        n.token("polygon", POL_FAKE_USDT, 6, 0)
        # bridges
        n.arbitrum(USDC, ARB_USDC)
        n.arbitrum(WBTC, ARB_WBTC)
        n.arbitrum(DAI, ARB_DAI, gw=ARB_DAI_GW, escrow=ARB_DAI_ESCROW)
        n.opstack("optimism", USDC, OP_USDC)
        n.opstack("optimism", USDC, OP_USDC2)
        n.opstack("optimism", USDC, OP_FAKE)
        n.op_dai(DAI, OP_DAI)
        n.opstack("base", USDC, BASE_USDC, legacy=True)
        n.polygon(USDC, POL_USDC)
        n.polygon(USDT, POL_USDT)
        n.oft("polygon", USDT, POL_USDT, USDT0_ADAPTER, POL_OFT)
        n.oft("arbitrum", USDT, ARB_USDT0, USDT0_ADAPTER, ARB_OFT)
        n.nomad(USDC, BEAM_USDC)
        # vault balances: everything backed 1:1 except Nomad (drained)
        n.balance("ethereum", USDC, ARB_GW, 1_000_000 * 10 ** 6)
        n.balance("ethereum", WBTC, ARB_GW, 100 * 10 ** 8)
        n.balance("ethereum", DAI, ARB_DAI_ESCROW, 5_000 * GEN)
        n.balance("ethereum", USDC, CR.OP_L1_BRIDGE, 500_000 * 10 ** 6 + 1)   # + the 1 wei deposited for OP_FAKE
        n.deposits(CR.OP_L1_BRIDGE, USDC, OP_USDC, 500_000 * 10 ** 6)
        n.deposits(CR.OP_L1_BRIDGE, USDC, OP_FAKE, 1)
        n.balance("ethereum", DAI, OP_DAI_ESCROW, 1_000 * GEN)
        n.balance("ethereum", USDC, CR.BASE_L1_BRIDGE, 200_000 * 10 ** 6)
        n.deposits(CR.BASE_L1_BRIDGE, USDC, BASE_USDC, 200_000 * 10 ** 6)
        n.balance("ethereum", USDC, POL_PRED, 300_000 * 10 ** 6)
        n.balance("ethereum", USDC, CR.NOMAD_ETH_ROUTER, 3_720 * 10 ** 6)
        # USDT: the PoS predicate holds a sliver, the OFT adapter the rest of what Polygon + Arbitrum carry
        n.balance("ethereum", USDT, POL_PRED, 5_000 * 10 ** 6)
        n.balance("ethereum", USDT, USDT0_ADAPTER, 1_495_000 * 10 ** 6)
        n.mine_to(NOW - 900)

    # --- calls ------------------------------------------------------------------
    def call(self, c, m, *a, sender=OPERATOR, value=0):
        return self.w.call(c, m, *a, sender=sender, value=value)

    def view(self, c, m, *a):
        return self.w.view(c, m, *a)

    def auth(self, kind, l1, l2, sender=OPERATOR):
        return self.call(self.reader, "authenticate", kind, l1, l2, sender=sender)

    PAIRS = {"arb_usdc": ("arbitrum", USDC, ARB_USDC), "arb_wbtc": ("arbitrum", WBTC, ARB_WBTC),
             "arb_dai": ("arbitrum", DAI, ARB_DAI), "op_usdc": ("optimism", USDC, OP_USDC),
             "op_dai": ("op_dai", DAI, OP_DAI), "base_usdc": ("base", USDC, BASE_USDC),
             "pol_usdc": ("polygon", USDC, POL_USDC), "nomad_usdc": ("nomad", USDC, BEAM_USDC),
             "pol_usdt": ("polygon", USDT, POL_USDT), "oft_pol_usdt": ("oft_polygon", USDT, POL_USDT),
             "oft_arb_usdt": ("oft_arbitrum", USDT, ARB_USDT0)}

    def pair(self, name="arb_usdc", tol=0, label="test pair"):
        k, l1, l2 = self.PAIRS[name]
        a = self.auth(k, l1, l2)
        r = self.call(self.reg, "register_pair", str(a["auth_id"]), tol, label)
        return r["pair_id"]

    def dest_chain(self, pid):
        p = self.view(self.reg, "get_pair", pid)
        return [d["chain"] for d in p["dests"]]

    def blocks(self, pid, ts=None, gap=0, dest_ts=None):
        """Pins for pair pid: the source block at/after ts, each destination
        block the last at or before (source ts - gap)."""
        ts = ts if ts is not None else self.w.now() - 900
        sb = self.net.first_at("ethereum", ts)
        st = self.net.ts("ethereum", sb)
        out = {"ethereum": sb}
        for ch in self.dest_chain(pid):
            out[ch] = self.net.block_at(ch, dest_ts if dest_ts is not None else st - gap)
        return out

    def bond(self, pid, amount=GEN, sender=OPERATOR):
        return self.call(self.reg, "bond", pid, sender=sender, value=amount)

    def challenge(self, bid, blocks, stake=None, sender=CHALLENGER):
        import json
        st = stake if stake is not None else int(self.view(self.reg, "get_config")["min_stake"])
        return self.call(self.reg, "challenge", bid, json.dumps(blocks), sender=sender, value=st)

    def monitor(self, pid, blocks, sender=PATROL):
        import json
        return self.call(self.reg, "monitor", pid, json.dumps(blocks), sender=sender)

    def read(self, cid, rnd=1, sender=PATROL):
        return self.call(self.reader, "read_check", self.reg, cid, rnd, sender=sender)

    def rule(self, cid, sender=PATROL):
        return self.call(self.reg, "rule", cid, sender=sender)

    def check(self, cid):
        return self.view(self.reg, "get_check", cid)

    def bound(self, pid):
        """(source token, dest chain, dest token) of the pair's first destination."""
        p = self.view(self.reg, "get_pair", pid)
        if not p.get("found"):
            return (USDC, "arbitrum", ARB_USDC)
        return (p["source_token"], p["dests"][0]["chain"], p["dests"][0]["token"])

    def gate_ask(self, pid, now=None, gate=None):
        st, dc, dt = self.bound(pid)
        return self.view(gate or self.gate, "is_backed", pid, st, dc, dt, self.w.now() if now is None else now)

    def borrow(self, pid, amount="1000", note="test", sender=None):
        st, dc, dt = self.bound(pid)
        return self.call(self.gate, "borrow", pid, st, dc, dt, amount, note, sender=sender or addr(77))

    def cfg(self):
        return self.view(self.reg, "get_config")

    def ledger(self):
        return self.view(self.reg, "get_ledger")

    def claimable(self, who):
        return int(self.view(self.reg, "get_claimable", who)["claimable"])

    def after_bond(self, seconds=1200):
        """Move time forward and mine so that fresh finalized blocks exist after
        a bond's start (which is world time)."""
        self.w.advance(seconds)
        self.net.mine_to(self.w.now() - 60)

    def run_to_provisional(self, cid):
        self.read(cid)
        return self.rule(cid)

    def finalize_after_window(self, cid):
        self.w.advance(int(self.cfg()["window_s"]) + 1)
        return self.call(self.reg, "finalize", cid, sender=PATROL)
