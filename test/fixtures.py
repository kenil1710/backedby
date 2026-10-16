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
# vaults / gateways
ARB_GW = addr(0xa9)
ARB_DAI_GW = addr(0xaa)
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
BEAM_USDC = addr(0x5001)
PRED_TYPE = "0x8ae85d849167ff996c04040c44924fd364217285e4cad818292c7ac37c0a345b"


def w(n):
    return "0x" + ("%064x" % int(n))


def wa(a):
    return "0x" + "0" * 24 + a[2:].lower()


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


class Setup:
    """A wired deployment on a fresh world with every bridge kind mapped."""

    def __init__(self, mode="DEMO", max_age=3600):
        self.w = world.new_world(now_iso=NOW_ISO)
        self.net = Net(self.w)
        n = self.net
        self.reader = self.w.deploy("ChainReader", sender=DEPLOYER)
        self.reg = self.w.deploy("BackedByRegistry", mode, self.reader, sender=DEPLOYER)
        self.gate = self.w.deploy("CollateralGate", self.reg, max_age, sender=DEPLOYER)
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
             "pol_usdc": ("polygon", USDC, POL_USDC), "nomad_usdc": ("nomad", USDC, BEAM_USDC)}

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
