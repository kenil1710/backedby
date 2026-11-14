# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import hashlib
import json
import typing

# ChainReader - reads both sides of a bridge at pinned blocks, from two RPCs
# per chain, and records what they agreed on. It decides nothing about
# backing: BackedByRegistry computes every number and every verdict from the
# readings recorded here.
#
# authenticate(kind, source_token, dest_token)
#   Every validator pins the latest finalized block of Ethereum and of the
#   destination chain (the leader names the lower of the two RPCs' finalized
#   blocks; a validator accepts it only if it is final on both of its own RPCs
#   and not more than LEADER_LAG_S older than its own) and reads the bridge's
#   OWN mapping there, from both RPCs, and records (vault, destination) only if
#   the mapping proves it; otherwise the call is refused. The vault is always
#   derived from the mapping, never supplied. What proves it, per bridge
#   (Arbitrum gateways, OP Stack, OP DAI, Polygon PoS, Nomad, LayerZero OFT),
#   is in `_auth_*` below and in docs/RULES.md.
#
# read_check(registry, check_id, round)
#   Reads the check request from the registry (a view), then every validator
#   reads, at the blocks the filer pinned: the block headers, every vault's
#   balance of the source token, each destination token's totalSupply, every
#   token's decimals, the per-token ledger (deposits) of OP Stack bridges, and
#   every anchor (the bridge-mapping calls recorded at authentication). Each
#   value from both RPCs, identical or INCONCLUSIVE. A block above either RPC's
#   finalized block is INCONCLUSIVE. The reading is stored under
#   (registry, check, round), once.
#
# RULES
#   1. Allowlisted RPCs only, matched exactly (CHAINS). No URL comes from calldata.
#   2. Validators accept the leader's result only if it is identical to their own.
#   3. Nothing is written before the last check that can refuse.
#   4. Records are immutable. No owner, no setter, no payable method.

VERSION = "2.0.0"
SOURCE_CHAIN = "ethereum"

S_BALANCE = "0x70a08231"
S_SUPPLY = "0x18160ddd"
S_DECIMALS = "0x313ce567"
S_GET_GATEWAY = "0xbda009fe"      # getGateway(address)
S_CALC_L2 = "0xa7e28d48"          # calculateL2TokenAddress(address)
S_L1_ESCROW = "0x000cc9e6"        # l1Escrow()
S_REMOTE_TOKEN = "0xd6c0b2c4"     # remoteToken()
S_L1_TOKEN = "0xc01e1bd6"         # l1Token()
S_BRIDGE = "0xe78cea92"           # bridge()
S_L2_BRIDGE = "0xae1f6aaf"        # l2Bridge()
S_L2_TOKEN = "0x56eff267"         # l2Token()
S_ESCROW = "0xe2fdcc17"           # escrow()
S_L1_DAI_BRIDGE = "0x092d0ce3"    # l1DAITokenBridge()
S_DEPOSITS = "0x8f601f66"         # deposits(address,address)
S_ROOT_TO_CHILD = "0xea60c7c4"    # rootToChildToken(address)
S_TOKEN_TO_TYPE = "0xe43009a6"    # tokenToType(address)
S_TYPE_TO_PRED = "0xe66f9603"     # typeToPredicate(bytes32)
S_CHILD_TO_ROOT = "0x6e86b770"    # childToRootToken(address)
S_TOKEN_REGISTRY = "0x9d23c4c7"   # tokenRegistry()
S_GET_TOKEN_ID = "0xf1537686"     # getTokenId(address)
S_GET_LOCAL = "0x589b3c64"        # getLocalAddress(uint32,bytes32)
S_REMOTES = "0x83bbb806"          # remotes(uint32)
S_TOKEN = "0xfc0c546a"            # token()
S_ENDPOINT = "0x5e280f11"         # endpoint()
S_PEERS = "0xbb0b6a53"            # peers(uint32)
S_OFT_CONTRACT = "0x232849c3"     # oftContract()

# v2: Wormhole token bridge, Chainlink CCIP token pools, Multicall3 coverage scans, Proof of Reserve
S_WH_BRIDGE_OF = "0xad66a5f1"     # bridgeContracts(uint16)
S_WH_WRAPPED = "0x1ff1e286"       # wrappedAsset(uint16,bytes32)
S_WH_IS_WRAPPED = "0x1a2be4da"    # isWrappedAsset(address)
S_WH_CHAIN_ID = "0x9a8a0592"      # chainId()
S_WH_NATIVE = "0x3d6c043b"        # nativeContract()
S_WH_OUTSTANDING = "0xb96c7e4d"   # outstandingBridged(address)
S_CCIP_GET_POOL = "0xbbe4f6db"    # getPool(address)
S_CCIP_TYPE = "0x181f5a77"        # typeAndVersion()
S_CCIP_GET_TOKEN = "0x21df0da7"   # getToken()
S_CCIP_REMOTE_TOKEN = "0xb7946580"   # getRemoteToken(uint64)
S_CCIP_IS_REMOTE_POOL = "0x4c5ef0ed"  # isRemotePool(uint64,bytes)
S_CCIP_CHAINS = "0xc4bffe2b"      # getSupportedChains()
S_LATEST_ROUND = "0xfeaf968c"     # latestRoundData()
S_AGGREGATE3 = "0x82ad56cb"       # aggregate3((address,bool,bytes)[])

MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
# Coverage scans of LayerZero adapters ask for every eid in LZ_SCAN in ONE
# Multicall3 call at the pinned Ethereum block; the check RPCs refuse a body
# that large, so scans use their own pair (two operators), answers identical.
SCAN_RPCS = ("https://rpc.mevblocker.io", "https://eth-mainnet.public.blastapi.io")
LZ_SCAN = (30101, 30700)
WH_ETH_BRIDGE = "0x3ee18b2214aff97000d974cf647e7c347e8fa585"
WH_ETH_ID = 2
# chain -> (wormhole chain id, token bridge on that chain)
WH_DESTS = {"polygon": (5, "0x5a58505a96d1dbf8df91cb21b54419fc36e93fde"),
            "arbitrum": (23, "0x0b2402144bb366a632d14b83f244d2e0e21bd39c"),
            "optimism": (24, "0x1d68124e65fafc907325e3edbf8c4d84499daa8b"),
            "base": (30, "0x8d2de8d2f73f1f4cab472ac9a881c9b123c79627")}
CCIP_ETH_SELECTOR = 5009297550715157269
CCIP_ETH_TAR = "0xb22764f98dd05c789929716d677382df22c05cb6"
# chain -> (CCIP chain selector, TokenAdminRegistry on that chain)
CCIP_DESTS = {"arbitrum": (4949039107694359620, "0x39ae1032cf4b334a1ed41cdd0833bdd7c7e7751e"),
              "base": (15971525489660198786, "0x6f6c373d09c07425baae72317863d7f6bb731e37"),
              "optimism": (3734403246176062136, "0x657c42abe4cd8aa731aec322f871b5b90cf6274f"),
              "polygon": (4051577828743386545, "0x00f027ea6d0fb03256a15e9182b2b9227a4931d8"),
              "mantle": (1556008542357238666, "0x000a744940eb5d857c0d61d97015dfc83107404f"),
              "xlayer": (3016212468291539606, "0xecf1eaee01e82f3388decd7f4c3792374f3f72f3"),
              "monad": (8481857512324358265, "0x11acd984dd680363117b310f6ebdf78fd6c0195f"),
              "ink": (3461204551265785888, "0xeb062d21c713a3d940bb0faecfdc387d6ea23697"),
              "unichain": (1923510103922296319, "0xab3ee2e897cf23c10e76d26ab4674fefa376bc0d"),
              "sei": (9027416829622342829, "0x910a46ca93e8086bf1d7d65190ee6aee5256bd61"),
              "berachain": (1294465214383781161, "0x0944c3fb1db7d165336569221995b31cbe6c8a55"),
              "hyperevm": (2442541497099098535, "0xce44363496abc3a9e53b3f404a740f992d977bdf")}
CCIP_SOURCE_POOLS = ("LockReleaseTokenPool ",)
CCIP_DEST_POOLS = ("BurnMintTokenPool ", "BurnFromMintTokenPool ", "BurnWithFromMintTokenPool ")
# Chainlink Proof of Reserve on Ethereum: source token -> (feed, token whose supply the feed covers)
POR_FEEDS = {"0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ("0xa81fe04086865e63e12dd3776978e49deea2ea4e", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"),
             "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": ("0xad410e655c0fe4741f573152592eeb766e686ce7", "0xae7ab96520de3a18e5e111b5eaab095312d7fe84"),
             "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee": ("0xc8cd82067ea907ea4af81b625d2bb653e21b5156", "0x35fa164735182de50811e8e2e824cfb9b6118ac2")}
# transport-class reasons: never stored as a reading; the check stays OPEN (PENDING) until its fixed deadline
TRANSIENT = ("RPC_UNREADABLE", "RPC_DISAGREE")
MAX_SCAN_IDS = 64

ARB_L1_ROUTER = "0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef"
ARB_L2_ROUTER = "0x5288c571fd7ad117bea99bf60fe0846c4e84f933"
OP_L1_BRIDGE = "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1"
BASE_L1_BRIDGE = "0x3154cf16ccdb4c6d922629664174b904d80f2c35"
L2_STD_BRIDGE = "0x4200000000000000000000000000000000000010"
OP_DAI_L1_BRIDGE = "0x10e6593cdda8c58a1d0f14c5164b376352a55f2f"
OP_DAI_L2_BRIDGE = "0x467194771dae2967aef3ecbedd3bf9a310c76c65"
POL_ROOT_MANAGER = "0xa0c68c638235ee32657e8f720a23cec1bfc77c77"
POL_CHILD_MANAGER = "0xa6fa4fb5f76172d178d61b04b0ecd319c5d1c0aa"
NOMAD_ETH_ROUTER = "0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3"
NOMAD_BEAM_ROUTER = "0xd3dfd3ede74e0dcebc1aa685e151332857efce2d"
NOMAD_ETH_DOMAIN = 6648936        # "eth"
LZ_ENDPOINT = "0x1a44076050125825900e736c501f859c50fe728c"   # LayerZero EndpointV2 on Ethereum and most chains
# chain -> its LayerZero EndpointV2 (read from each USDT0 OFT's endpoint(), docs/FEASIBILITY.md)
LZ_ENDPOINTS = {"ethereum": LZ_ENDPOINT, "polygon": LZ_ENDPOINT, "arbitrum": LZ_ENDPOINT, "optimism": LZ_ENDPOINT,
               "base": LZ_ENDPOINT,
               "mantle": "0x1a44076050125825900e736c501f859c50fe728c",
               "xlayer": "0x1a44076050125825900e736c501f859c50fe728c",
               "sei": "0x1a44076050125825900e736c501f859c50fe728c",
               "flare": "0x1a44076050125825900e736c501f859c50fe728c",
               "hedera": "0x3a73033c0b1407574c76bdbac67f126f6b4a9aa9",
               "unichain": "0x6f475642a6e85809b1c36fa62763669b1b48dd5b",
               "morph": "0x6f475642a6e85809b1c36fa62763669b1b48dd5b",
               "ink": "0xca29f3a6f966cb2fc0de625f8f325c0c46dbe958",
               "berachain": "0x6f475642a6e85809b1c36fa62763669b1b48dd5b",
               "hyperevm": "0x3a73033c0b1407574c76bdbac67f126f6b4a9aa9",
               "monad": "0x6f475642a6e85809b1c36fa62763669b1b48dd5b"}
LZ_EID = {"ethereum": 30101, "polygon": 30109, "arbitrum": 30110, "optimism": 30111, "base": 30184, "mantle": 30181, "xlayer": 30274, "sei": 30280, "flare": 30295, "hedera": 30316, "unichain": 30320, "morph": 30322, "ink": 30339, "berachain": 30362, "hyperevm": 30367, "monad": 30390}
POL_ERC20_TYPE = "0x8ae85d849167ff996c04040c44924fd364217285e4cad818292c7ac37c0a345b"   # keccak256("ERC20")
# Arbitrum gateways that ESCROW the L1 token (measured: each holds >= the L2
# supply, docs/FEASIBILITY.md). A gateway that mints on L1 instead of
# releasing from escrow would read as under-backed when it is not, so any
# other gateway is refused.
ARB_ESCROW_GATEWAYS = {
    "0xa3a7b6f88361f48403514059f1f16c8e78d60eec": "L1ERC20Gateway (standard)",
    "0xd3b5b60020504bc3489d6949d545893982ba3011": "L1DaiGateway",
    "0xcee284f754e854890e311e3280b767f80797180d": "L1USDCGateway",
    "0x0f25c1dc2a9922304f2eac71dca9b07e310e8e5a": "Lido wstETH L1 gateway",
}
MAX_ANCHORS = 96

# kind -> destination chain. The source chain is always Ethereum.
KINDS = {"arbitrum": "arbitrum", "optimism": "optimism", "base": "base", "op_dai": "optimism",
         "polygon": "polygon", "nomad": "moonbeam", "oft_polygon": "polygon", "oft_arbitrum": "arbitrum",
         "oft_optimism": "optimism", "oft_base": "base", "oft_mantle": "mantle", "oft_xlayer": "xlayer", "oft_sei": "sei", "oft_flare": "flare", "oft_hedera": "hedera", "oft_unichain": "unichain", "oft_morph": "morph", "oft_ink": "ink", "oft_berachain": "berachain", "oft_hyperevm": "hyperevm", "oft_monad": "monad"}
for _c in WH_DESTS:
    KINDS["wh_" + _c] = _c
for _c in CCIP_DESTS:
    KINDS["ccip_" + _c] = _c


def family(kind: str) -> str:
    """How a vault of this kind proves it backs nothing unlisted:
    MAPPING  the bridge maps the source token to exactly one destination token
    LEDGER   the bridge keeps its own total owed across every chain (Wormhole)
    LZ       every LayerZero eid in LZ_SCAN is scanned for a peer (Multicall3)
    CCIP     the pool lists its supported chains (getSupportedChains)
    OPEN     no on-chain enumeration exists (OP/Base escrows, Nomad's router)"""
    k = str(kind)
    if k.startswith("oft_"):
        return "LZ"
    if k.startswith("wh_"):
        return "LEDGER"
    if k.startswith("ccip_"):
        return "CCIP"
    if k in ("arbitrum", "polygon", "op_dai"):
        return "MAPPING"
    return "OPEN"


def remote_id(kind: str) -> str:
    """The id under which the vault's own config names this destination."""
    k = str(kind)
    dest = KINDS.get(k, "")
    if k.startswith("oft_"):
        return "lz:" + str(LZ_EID[dest])
    if k.startswith("ccip_"):
        return "ccip:" + str(CCIP_DESTS[dest][0])
    if k.startswith("wh_"):
        return "wh:" + str(WH_DESTS[dest][0])
    return k + ":" + dest
# kinds whose L1 bridge keeps a per-token ledger (deposits(l1, l2)); a
# destination's supply is counted as max(totalSupply, deposits) - see RULES.md
DEPOSIT_KINDS = ("optimism", "base")
MAX_DESTS = 16
MAX_VAULTS = 8
MAX_DECIMALS = 36

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
    if url in SCAN_RPCS:
        return True
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


def heads_at(chain: str, block: int) -> typing.Any:
    """One batch per RPC: [finalized, chainId, header(block)]. Returns
    {"header": {...}} when the header is identical on both RPCs and at or
    below both RPCs' finalized blocks, else {"reason": ...}. ReadFailed and
    Disagree propagate."""
    calls = [["eth_getBlockByNumber", ["finalized", False]], ["eth_chainId", []], ["eth_getBlockByNumber", [hex(block), False]]]
    heads = []
    for url in CHAINS[chain][1]:
        got = rpc_send(url, calls)
        fin = _block_of(got[0])
        cid = _proj(["eth_chainId", []], got[1])
        if fin is None or cid != CHAINS[chain][0]:
            return {"reason": "RPC_UNREADABLE"}
        if block > fin["number"]:
            return {"reason": "BLOCK_NOT_FINALIZED:" + chain}
        heads.append(_block_of(got[2]))
    if _canon(heads[0]) != _canon(heads[1]):
        raise Disagree("headers differ")
    if heads[0] is None or heads[0]["number"] != block:
        return {"reason": "BLOCK_MISSING:" + chain}
    return {"header": heads[0]}


def eth_call(to: str, data: str, block: int) -> list:
    return ["eth_call", [{"to": to, "data": data}, hex(block)]]


def get_block(block: int) -> list:
    return ["eth_getBlockByNumber", [hex(block), False]]
# ==== end shared rpc ====


# --- pure helpers (no storage, no self) ---------------------------------------

def _pad(a: str) -> str:
    t = str(a).lower()
    if t.startswith("0x"):
        t = t[2:]
    return ("0" * 64 + t)[-64:]


def _word(r: typing.Any) -> int:
    """First 32-byte word of an ["ok", hex] call result, or -1."""
    if not isinstance(r, list) or r[0] != "ok" or not isinstance(r[1], str) or len(r[1]) < 66:
        return -1
    return int(r[1][2:66], 16)


def _addr_w(r: typing.Any) -> str:
    v = _word(r)
    if v < 0 or v >> 160 != 0:
        return ""
    return "0x" + ("0" * 40 + hex(v)[2:])[-40:]


def _nonzero(a: str) -> bool:
    return a != "" and a != ZERO


def _w32(r: typing.Any) -> str:
    """The first 32-byte word of a call result as 0x + 64 hex, or ""."""
    if not isinstance(r, list) or r[0] != "ok" or not isinstance(r[1], str) or len(r[1]) < 66:
        return ""
    return r[1][0:66]


def _aw(a: str) -> str:
    return "0x" + _pad(a)


def _q(chain: str, block: int, items: list) -> list:
    """eth_call every (to, data) at `block` on both RPCs; identical or Disagree."""
    return dual_read(chain, [eth_call(it[0], it[1], block) for it in items])


class Refuse(Exception):
    """A deterministic refusal every honest validator reaches too."""


def _decimals(r: typing.Any) -> int:
    d = _word(r)
    if d < 0 or d > MAX_DECIMALS:
        raise Refuse("DECIMALS_UNREADABLE")
    return d


def _auth_arbitrum(l1: str, l2: str, be: int, bd: int) -> dict:
    r = _q(SOURCE_CHAIN, be, [[ARB_L1_ROUTER, S_GET_GATEWAY + _pad(l1)], [ARB_L1_ROUTER, S_CALC_L2 + _pad(l1)],
                             [l1, S_DECIMALS]])
    gw = _addr_w(r[0])
    mapped = _addr_w(r[1])
    sd = _decimals(r[2])
    if not _nonzero(gw):
        raise Refuse("ROUTER_HAS_NO_GATEWAY_FOR_TOKEN")
    if mapped != l2:
        raise Refuse("L1_ROUTER_MAPS_TOKEN_TO_" + mapped)
    if gw not in ARB_ESCROW_GATEWAYS:
        raise Refuse("GATEWAY_" + gw + "_IS_NOT_AN_ESCROW_GATEWAY")
    e = _q(SOURCE_CHAIN, be, [[gw, S_L1_ESCROW]])
    esc = _addr_w(e[0])
    vault = esc if _nonzero(esc) else gw
    d = _q("arbitrum", bd, [[ARB_L2_ROUTER, S_CALC_L2 + _pad(l1)], [l2, S_DECIMALS]])
    if _addr_w(d[0]) != l2:
        raise Refuse("L2_ROUTER_DISAGREES_WITH_L1_ROUTER")
    dd = _decimals(d[1])
    proof = ["L1GatewayRouter.getGateway(l1)=" + gw, "L1GatewayRouter.calculateL2TokenAddress(l1)=" + mapped,
             "L2GatewayRouter.calculateL2TokenAddress(l1)=" + l2,
             ("gateway.l1Escrow()=" + esc) if _nonzero(esc) else "gateway holds the escrow",
             "gateway is " + ARB_ESCROW_GATEWAYS[gw]]
    anchors = [[SOURCE_CHAIN, ARB_L1_ROUTER, S_GET_GATEWAY + _pad(l1), _aw(gw)],
               [SOURCE_CHAIN, ARB_L1_ROUTER, S_CALC_L2 + _pad(l1), _aw(l2)],
               ["arbitrum", ARB_L2_ROUTER, S_CALC_L2 + _pad(l1), _aw(l2)]]
    if _nonzero(esc):
        anchors.append([SOURCE_CHAIN, gw, S_L1_ESCROW, _aw(esc)])
    return {"vault": vault, "source_decimals": sd, "dest_decimals": dd, "proof": proof, "anchors": anchors}


def _auth_opstack(kind: str, l1: str, l2: str, be: int, bd: int) -> dict:
    d = _q(kind, bd, [[l2, S_REMOTE_TOKEN], [l2, S_L1_TOKEN], [l2, S_BRIDGE], [l2, S_L2_BRIDGE], [l2, S_DECIMALS]])
    rt = _addr_w(d[0])
    rsel = S_REMOTE_TOKEN
    if rt == "":
        rt = _addr_w(d[1])
        rsel = S_L1_TOKEN
    br = _addr_w(d[2])
    bsel = S_BRIDGE
    if br == "":
        br = _addr_w(d[3])
        bsel = S_L2_BRIDGE
    if rt != l1:
        raise Refuse("REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN")
    if br != L2_STD_BRIDGE:
        raise Refuse("NOT_MINTED_BY_THE_L2_STANDARD_BRIDGE")
    dd = _decimals(d[4])
    vault = OP_L1_BRIDGE if kind == "optimism" else BASE_L1_BRIDGE
    s = _q(SOURCE_CHAIN, be, [[l1, S_DECIMALS], [vault, S_DEPOSITS + _pad(l1) + _pad(l2)]])
    sd = _decimals(s[0])
    dep = _word(s[1])
    if dep < 0:
        raise Refuse("L1_BRIDGE_HAS_NO_DEPOSITS_MAPPING")
    proof = ["l2token.remoteToken()=" + rt, "l2token.bridge()=" + br, "L1StandardBridge=" + vault,
             "L1StandardBridge.deposits(l1,l2)=" + str(dep)]
    anchors = [[kind, l2, rsel, _aw(l1)], [kind, l2, bsel, _aw(L2_STD_BRIDGE)]]
    return {"vault": vault, "source_decimals": sd, "dest_decimals": dd, "proof": proof, "anchors": anchors}


def _auth_op_dai(l1: str, l2: str, be: int, bd: int) -> dict:
    s = _q(SOURCE_CHAIN, be, [[OP_DAI_L1_BRIDGE, S_L1_TOKEN], [OP_DAI_L1_BRIDGE, S_L2_TOKEN],
                             [OP_DAI_L1_BRIDGE, S_ESCROW], [l1, S_DECIMALS]])
    d = _q("optimism", bd, [[OP_DAI_L2_BRIDGE, S_L1_TOKEN], [OP_DAI_L2_BRIDGE, S_L2_TOKEN],
                           [OP_DAI_L2_BRIDGE, S_L1_DAI_BRIDGE], [l2, S_DECIMALS]])
    esc = _addr_w(s[2])
    if _addr_w(s[0]) != l1 or _addr_w(d[0]) != l1:
        raise Refuse("DAI_BRIDGE_L1_TOKEN_MISMATCH")
    if _addr_w(s[1]) != l2 or _addr_w(d[1]) != l2:
        raise Refuse("DAI_BRIDGE_L2_TOKEN_MISMATCH")
    if _addr_w(d[2]) != OP_DAI_L1_BRIDGE:
        raise Refuse("L2_DAI_BRIDGE_POINTS_ELSEWHERE")
    if not _nonzero(esc):
        raise Refuse("DAI_BRIDGE_HAS_NO_ESCROW")
    proof = ["L1DAITokenBridge.l1Token()=" + l1, "L1DAITokenBridge.l2Token()=" + l2, "L1DAITokenBridge.escrow()=" + esc,
             "L2DAITokenBridge.l1DAITokenBridge()=" + OP_DAI_L1_BRIDGE]
    anchors = [[SOURCE_CHAIN, OP_DAI_L1_BRIDGE, S_L1_TOKEN, _aw(l1)], [SOURCE_CHAIN, OP_DAI_L1_BRIDGE, S_L2_TOKEN, _aw(l2)],
               [SOURCE_CHAIN, OP_DAI_L1_BRIDGE, S_ESCROW, _aw(esc)], ["optimism", OP_DAI_L2_BRIDGE, S_L2_TOKEN, _aw(l2)]]
    return {"vault": esc, "source_decimals": _decimals(s[3]), "dest_decimals": _decimals(d[3]), "proof": proof,
            "anchors": anchors}


def _auth_polygon(l1: str, l2: str, be: int, bd: int) -> dict:
    s = _q(SOURCE_CHAIN, be, [[POL_ROOT_MANAGER, S_ROOT_TO_CHILD + _pad(l1)], [POL_ROOT_MANAGER, S_TOKEN_TO_TYPE + _pad(l1)],
                             [l1, S_DECIMALS]])
    child = _addr_w(s[0])
    typ = s[1][1] if isinstance(s[1], list) and s[1][0] == "ok" and isinstance(s[1][1], str) and len(s[1][1]) >= 66 else ""
    if child != l2:
        raise Refuse("ROOT_CHAIN_MANAGER_MAPS_TOKEN_TO_" + child)
    if typ == "" or int(typ[2:66], 16) == 0:
        raise Refuse("TOKEN_HAS_NO_TYPE")
    if typ[0:66].lower() != POL_ERC20_TYPE:
        raise Refuse("TOKEN_TYPE_IS_NOT_ERC20_ESCROW")
    p = _q(SOURCE_CHAIN, be, [[POL_ROOT_MANAGER, S_TYPE_TO_PRED + typ[2:66]]])
    pred = _addr_w(p[0])
    if not _nonzero(pred):
        raise Refuse("TYPE_HAS_NO_PREDICATE")
    d = _q("polygon", bd, [[POL_CHILD_MANAGER, S_CHILD_TO_ROOT + _pad(l2)], [l2, S_DECIMALS]])
    if _addr_w(d[0]) != l1:
        raise Refuse("CHILD_CHAIN_MANAGER_DISAGREES")
    proof = ["RootChainManager.rootToChildToken(l1)=" + child, "RootChainManager.typeToPredicate(tokenToType(l1))=" + pred,
             "ChildChainManager.childToRootToken(child)=" + l1]
    anchors = [[SOURCE_CHAIN, POL_ROOT_MANAGER, S_ROOT_TO_CHILD + _pad(l1), _aw(l2)],
               [SOURCE_CHAIN, POL_ROOT_MANAGER, S_TOKEN_TO_TYPE + _pad(l1), POL_ERC20_TYPE],
               [SOURCE_CHAIN, POL_ROOT_MANAGER, S_TYPE_TO_PRED + POL_ERC20_TYPE[2:], _aw(pred)],
               ["polygon", POL_CHILD_MANAGER, S_CHILD_TO_ROOT + _pad(l2), _aw(l1)]]
    return {"vault": pred, "source_decimals": _decimals(s[2]), "dest_decimals": _decimals(d[1]), "proof": proof,
            "anchors": anchors}


def _auth_nomad(l1: str, l2: str, be: int, bd: int) -> dict:
    dom = _pad(hex(NOMAD_ETH_DOMAIN))
    d = _q("moonbeam", bd, [[NOMAD_BEAM_ROUTER, S_TOKEN_REGISTRY], [NOMAD_BEAM_ROUTER, S_REMOTES + dom], [l2, S_DECIMALS]])
    reg = _addr_w(d[0])
    remote = _addr_w(d[1])
    if not _nonzero(reg):
        raise Refuse("NO_TOKEN_REGISTRY")
    if remote != NOMAD_ETH_ROUTER:
        raise Refuse("MOONBEAM_ROUTER_REMOTE_IS_NOT_THE_ETHEREUM_ROUTER")
    t = _q("moonbeam", bd, [[reg, S_GET_TOKEN_ID + _pad(l2)], [reg, S_GET_LOCAL + dom + _pad(l1)]])
    tid = t[0][1] if isinstance(t[0], list) and t[0][0] == "ok" and isinstance(t[0][1], str) else ""
    if len(tid) < 130 or int(tid[2:66], 16) != NOMAD_ETH_DOMAIN or "0x" + tid[-40:] != l1:
        raise Refuse("TOKEN_REGISTRY_DOES_NOT_MAP_TOKEN_TO_ETHEREUM_SOURCE")
    if _addr_w(t[1]) != l2:
        raise Refuse("TOKEN_REGISTRY_LOCAL_ADDRESS_MISMATCH")
    e = _q(SOURCE_CHAIN, be, [[NOMAD_ETH_ROUTER, S_TOKEN_REGISTRY], [l1, S_DECIMALS]])
    ereg = _addr_w(e[0])
    if not _nonzero(ereg):
        raise Refuse("NO_ETHEREUM_TOKEN_REGISTRY")
    x = _q(SOURCE_CHAIN, be, [[ereg, S_GET_TOKEN_ID + _pad(l1)]])
    etid = x[0][1] if isinstance(x[0], list) and x[0][0] == "ok" and isinstance(x[0][1], str) else ""
    if len(etid) < 130 or int(etid[2:66], 16) != NOMAD_ETH_DOMAIN or "0x" + etid[-40:] != l1:
        raise Refuse("SOURCE_TOKEN_IS_NOT_LOCAL_ON_ETHEREUM")
    proof = ["Moonbeam BridgeRouter.tokenRegistry()=" + reg, "Moonbeam BridgeRouter.remotes(eth)=" + remote,
             "TokenRegistry.getTokenId(rep)=(eth," + l1 + ")", "TokenRegistry.getLocalAddress(eth,l1)=" + l2,
             "Ethereum TokenRegistry.getTokenId(l1)=(eth,local)"]
    anchors = [["moonbeam", NOMAD_BEAM_ROUTER, S_TOKEN_REGISTRY, _aw(reg)],
               ["moonbeam", NOMAD_BEAM_ROUTER, S_REMOTES + dom, _aw(NOMAD_ETH_ROUTER)],
               ["moonbeam", reg, S_GET_LOCAL + dom + _pad(l1), _aw(l2)]]
    return {"vault": NOMAD_ETH_ROUTER, "source_decimals": _decimals(e[1]), "dest_decimals": _decimals(d[2]), "proof": proof,
            "anchors": anchors}


def _auth_oft(dest: str, l1: str, l2: str, be: int, bd: int) -> dict:
    """LayerZero OFT: the destination token's OFT (its oftContract(), or the
    token itself) has the Ethereum adapter as its peer; the adapter's token()
    is the source token and its peer for this chain is that OFT; both sit on
    their chain's LayerZero endpoint. The vault is the adapter, derived, never
    supplied. l2 may also name an OFT adapter whose token() is another
    contract (Hedera's USDT0 is a native HTS token): that token() is the
    destination token."""
    d = _q(dest, bd, [[l2, S_OFT_CONTRACT], [l2, S_TOKEN]])
    oc = _addr_w(d[0])
    tk = _addr_w(d[1])
    if _nonzero(oc):
        oft = oc
        token = l2
    elif _nonzero(tk) and tk != l2:
        oft = l2
        token = tk
    else:
        oft = l2
        token = l2
    ep = LZ_ENDPOINTS[dest]
    p = _q(dest, bd, [[oft, S_PEERS + _pad(hex(LZ_EID["ethereum"]))], [oft, S_ENDPOINT], [oft, S_TOKEN], [token, S_DECIMALS]])
    adapter = _addr_w(p[0])
    if not _nonzero(adapter):
        raise Refuse("OFT_HAS_NO_ETHEREUM_PEER")
    if _addr_w(p[1]) != ep:
        raise Refuse("OFT_NOT_ON_THE_LAYERZERO_ENDPOINT")
    if oft != token and _addr_w(p[2]) != token:
        raise Refuse("OFT_TOKEN_IS_NOT_THE_DESTINATION_TOKEN")
    dd = _decimals(p[3])
    e = _q(SOURCE_CHAIN, be, [[adapter, S_TOKEN], [adapter, S_ENDPOINT], [adapter, S_PEERS + _pad(hex(LZ_EID[dest]))],
                             [l1, S_DECIMALS]])
    if _addr_w(e[0]) != l1:
        raise Refuse("ADAPTER_TOKEN_IS_NOT_THE_SOURCE_TOKEN")
    if _addr_w(e[1]) != LZ_ENDPOINT:
        raise Refuse("ADAPTER_NOT_ON_THE_LAYERZERO_ENDPOINT")
    if _addr_w(e[2]) != oft:
        raise Refuse("ADAPTER_PEER_IS_NOT_THE_DESTINATION_OFT")
    proof = ["destination OFT=" + oft, "OFT.peers(Ethereum)=" + adapter, "OFT.endpoint()=" + ep,
             "adapter.token()=" + l1, "adapter.peers(" + dest + ")=" + oft]
    if oft != token:
        proof.append("OFT.token()=" + token)
    anchors = [[SOURCE_CHAIN, adapter, S_TOKEN, _aw(l1)],
               [SOURCE_CHAIN, adapter, S_PEERS + _pad(hex(LZ_EID[dest])), _aw(oft)],
               [dest, oft, S_PEERS + _pad(hex(LZ_EID["ethereum"])), _aw(adapter)]]
    if oft != token:
        if _nonzero(oc):
            anchors.append([dest, token, S_OFT_CONTRACT, _aw(oft)])
        anchors.append([dest, oft, S_TOKEN, _aw(token)])
    return {"vault": adapter, "source_decimals": _decimals(e[3]), "dest_decimals": dd, "proof": proof,
            "anchors": anchors, "dest_token": token}


def _u(n: int) -> str:
    return ("0" * 64 + hex(int(n))[2:])[-64:]


def _abi_bytes(r: typing.Any) -> str:
    """An ABI-encoded `bytes` return value as lowercase 0x hex, or ""."""
    if not isinstance(r, list) or r[0] != "ok" or not isinstance(r[1], str) or len(r[1]) < 130:
        return ""
    h = r[1][2:]
    off = int(h[0:64], 16) * 2
    if off + 64 > len(h):
        return ""
    n = int(h[off:off + 64], 16) * 2
    if off + 64 + n > len(h) or n > 4096:
        return ""
    return "0x" + h[off + 64:off + 64 + n]


def _abi_string(r: typing.Any) -> str:
    b = _abi_bytes(r)
    if b == "":
        return ""
    try:
        return bytes.fromhex(b[2:]).decode("utf-8", errors="replace")[:80]
    except Exception:
        return ""


def _abi_u64s(r: typing.Any) -> typing.Any:
    """An ABI-encoded uint64[] -> [int], or None."""
    if not isinstance(r, list) or r[0] != "ok" or not isinstance(r[1], str) or len(r[1]) < 130:
        return None
    h = r[1][2:]
    off = int(h[0:64], 16) * 2
    if off + 64 > len(h):
        return None
    n = int(h[off:off + 64], 16)
    if n > MAX_SCAN_IDS or off + 64 + 64 * n > len(h):
        return None
    return [int(h[off + 64 + 64 * i:off + 128 + 64 * i], 16) for i in range(n)]


def _auth_wormhole(dest: str, l1: str, l2: str, be: int, bd: int) -> dict:
    """Wormhole token bridge: Ethereum's bridge registers this chain's bridge;
    this chain's bridge maps (Ethereum, l1) to l2, which is one of its wrapped
    assets and whose origin is (Ethereum, l1); this chain's bridge registers
    Ethereum's. The vault is Ethereum's token bridge; its ledger
    outstandingBridged(l1) is what it owes across every chain."""
    wid = WH_DESTS[dest][0]
    tb = WH_DESTS[dest][1]
    e = _q(SOURCE_CHAIN, be, [[WH_ETH_BRIDGE, S_WH_BRIDGE_OF + _u(wid)], [l1, S_DECIMALS],
                             [WH_ETH_BRIDGE, S_WH_OUTSTANDING + _pad(l1)]])
    if _w32(e[0]) != _aw(tb):
        raise Refuse("ETH_TOKEN_BRIDGE_DOES_NOT_REGISTER_" + dest.upper())
    if _word(e[2]) < 0:
        raise Refuse("ETH_TOKEN_BRIDGE_HAS_NO_LEDGER")
    d = _q(dest, bd, [[tb, S_WH_WRAPPED + _u(WH_ETH_ID) + _pad(l1)], [tb, S_WH_IS_WRAPPED + _pad(l2)],
                      [l2, S_WH_CHAIN_ID], [l2, S_WH_NATIVE], [tb, S_WH_BRIDGE_OF + _u(WH_ETH_ID)], [l2, S_DECIMALS]])
    if _addr_w(d[0]) != l2:
        raise Refuse("WRAPPED_ASSET_OF_SOURCE_IS_" + _addr_w(d[0]))
    if _word(d[1]) != 1:
        raise Refuse("NOT_A_WRAPPED_ASSET_OF_THE_BRIDGE")
    if _word(d[2]) != WH_ETH_ID or _w32(d[3]) != _aw(l1):
        raise Refuse("WRAPPED_ORIGIN_IS_NOT_THE_SOURCE_TOKEN")
    if _w32(d[4]) != _aw(WH_ETH_BRIDGE):
        raise Refuse("DEST_BRIDGE_DOES_NOT_REGISTER_ETHEREUM")
    proof = ["Ethereum TokenBridge.bridgeContracts(" + str(wid) + ")=" + tb,
             "TokenBridge.wrappedAsset(2,l1)=" + l2, "TokenBridge.isWrappedAsset(l2)=true",
             "l2.chainId()=2", "l2.nativeContract()=" + l1, "TokenBridge.bridgeContracts(2)=" + WH_ETH_BRIDGE,
             "Ethereum TokenBridge.outstandingBridged(l1)=" + str(_word(e[2]))]
    anchors = [[SOURCE_CHAIN, WH_ETH_BRIDGE, S_WH_BRIDGE_OF + _u(wid), _aw(tb)],
               [dest, tb, S_WH_WRAPPED + _u(WH_ETH_ID) + _pad(l1), _aw(l2)],
               [dest, l2, S_WH_NATIVE, _aw(l1)],
               [dest, tb, S_WH_BRIDGE_OF + _u(WH_ETH_ID), _aw(WH_ETH_BRIDGE)]]
    return {"vault": WH_ETH_BRIDGE, "source_decimals": _decimals(e[1]), "dest_decimals": _decimals(d[5]),
            "proof": proof, "anchors": anchors}


def _remote_pool_call(sel_id: int, pool: str) -> str:
    return S_CCIP_IS_REMOTE_POOL + _u(sel_id) + _u(64) + _u(32) + _pad(pool)


def _auth_ccip(dest: str, l1: str, l2: str, be: int, bd: int) -> dict:
    """Chainlink CCIP: Ethereum's TokenAdminRegistry names l1's pool, a
    lock-release pool whose token is l1, whose remote token for this chain is
    l2 and whose remote pools include this chain's pool; this chain's registry
    names l2's pool, a burn-mint pool whose token is l2, whose remote token for
    Ethereum is l1 and whose remote pools include Ethereum's. The vault is the
    lock-release pool."""
    dsel = CCIP_DESTS[dest][0]
    dtar = CCIP_DESTS[dest][1]
    e = _q(SOURCE_CHAIN, be, [[CCIP_ETH_TAR, S_CCIP_GET_POOL + _pad(l1)], [l1, S_DECIMALS]])
    pool = _addr_w(e[0])
    if not _nonzero(pool):
        raise Refuse("NO_CCIP_POOL_FOR_SOURCE_TOKEN")
    p = _q(SOURCE_CHAIN, be, [[pool, S_CCIP_TYPE], [pool, S_CCIP_GET_TOKEN], [pool, S_CCIP_REMOTE_TOKEN + _u(dsel)]])
    tv = _abi_string(p[0])
    ok = False
    for pre in CCIP_SOURCE_POOLS:
        if tv.startswith(pre):
            ok = True
    if not ok:
        raise Refuse("SOURCE_POOL_IS_NOT_LOCK_RELEASE")
    if _addr_w(p[1]) != l1:
        raise Refuse("SOURCE_POOL_TOKEN_IS_NOT_THE_SOURCE_TOKEN")
    if _abi_bytes(p[2]) != _aw(l2):
        raise Refuse("SOURCE_POOL_REMOTE_TOKEN_IS_NOT_THE_DEST_TOKEN")
    d = _q(dest, bd, [[dtar, S_CCIP_GET_POOL + _pad(l2)], [l2, S_DECIMALS]])
    dp = _addr_w(d[0])
    if not _nonzero(dp):
        raise Refuse("NO_CCIP_POOL_FOR_DEST_TOKEN")
    x = _q(dest, bd, [[dp, S_CCIP_TYPE], [dp, S_CCIP_GET_TOKEN], [dp, S_CCIP_REMOTE_TOKEN + _u(CCIP_ETH_SELECTOR)],
                      [dp, _remote_pool_call(CCIP_ETH_SELECTOR, pool)]])
    dtv = _abi_string(x[0])
    ok = False
    for pre in CCIP_DEST_POOLS:
        if dtv.startswith(pre):
            ok = True
    if not ok:
        raise Refuse("DEST_POOL_IS_NOT_BURN_MINT")
    if _addr_w(x[1]) != l2:
        raise Refuse("DEST_POOL_TOKEN_IS_NOT_THE_DEST_TOKEN")
    if _abi_bytes(x[2]) != _aw(l1):
        raise Refuse("DEST_POOL_REMOTE_TOKEN_IS_NOT_THE_SOURCE_TOKEN")
    if _word(x[3]) != 1:
        raise Refuse("DEST_POOL_DOES_NOT_NAME_THE_SOURCE_POOL")
    back = _q(SOURCE_CHAIN, be, [[pool, _remote_pool_call(dsel, dp)]])
    if _word(back[0]) != 1:
        raise Refuse("SOURCE_POOL_DOES_NOT_NAME_THE_DEST_POOL")
    proof = ["Ethereum TokenAdminRegistry.getPool(l1)=" + pool, "pool.typeAndVersion()=" + tv,
             "pool.getRemoteToken(" + str(dsel) + ")=" + l2, "pool.isRemotePool(" + str(dsel) + "," + dp + ")=true",
             dest + " TokenAdminRegistry.getPool(l2)=" + dp, "dest pool.typeAndVersion()=" + dtv,
             "dest pool.getRemoteToken(Ethereum)=" + l1, "dest pool.isRemotePool(Ethereum," + pool + ")=true"]
    anchors = [[SOURCE_CHAIN, CCIP_ETH_TAR, S_CCIP_GET_POOL + _pad(l1), _aw(pool)],
               [SOURCE_CHAIN, pool, S_CCIP_GET_TOKEN, _aw(l1)],
               [SOURCE_CHAIN, pool, _remote_pool_call(dsel, dp), _aw("0x1")],
               [dest, dtar, S_CCIP_GET_POOL + _pad(l2), _aw(dp)],
               [dest, dp, S_CCIP_GET_TOKEN, _aw(l2)],
               [dest, dp, _remote_pool_call(CCIP_ETH_SELECTOR, pool), _aw("0x1")]]
    return {"vault": pool, "source_decimals": _decimals(e[1]), "dest_decimals": _decimals(d[1]), "proof": proof,
            "anchors": anchors}


def mc_encode(target: str, datas: list) -> str:
    """Multicall3.aggregate3 calldata: one (target, allowFailure=true, data)
    per entry; every data is exactly 36 bytes (a selector and one word)."""
    n = len(datas)
    head = _u(32) + _u(n)
    offs = ""
    body = ""
    for i in range(n):
        offs += _u(n * 32 + i * 192)
        d = datas[i][2:]
        body += _pad(target) + _u(1) + _u(96) + _u(len(d) // 2) + (d + "0" * 128)[0:128]
    return S_AGGREGATE3 + head + offs + body


def mc_decode(h: str, n: int) -> typing.Any:
    """aggregate3's (bool success, bytes returnData)[] -> [first word as int,
    or -1 for a failed or empty call], or None if malformed."""
    if not isinstance(h, str) or not h.startswith("0x"):
        return None
    t = h[2:]
    try:
        base = int(t[0:64], 16) * 2
        cnt = int(t[base:base + 64], 16)
        if cnt != n:
            return None
        start = base + 64
        out = []
        for i in range(n):
            o = start + int(t[start + 64 * i:start + 64 * (i + 1)], 16) * 2
            ok = int(t[o:o + 64], 16)
            bo = o + int(t[o + 64:o + 128], 16) * 2
            ln = int(t[bo:bo + 64], 16)
            if ok != 1 or ln < 32:
                out.append(-1)
            else:
                out.append(int(t[bo + 64:bo + 128], 16))
        return out
    except Exception:
        return None


def lz_scan(adapter: str, block: int) -> typing.Any:
    """Every eid in LZ_SCAN whose peer on the adapter is set, at `block`, from
    both scan RPCs, identical. -> sorted [eid] or a reason string."""
    eids = list(range(LZ_SCAN[0], LZ_SCAN[1]))
    data = mc_encode(adapter, [S_PEERS + _u(e) for e in eids])
    got = []
    for url in SCAN_RPCS:
        try:
            r = rpc_send(url, [eth_call(MULTICALL3, data, block)])
        except ReadFailed:
            return "SCAN_UNREADABLE"
        if r[0][0] != "ok":
            return "SCAN_REVERTED"
        dec = mc_decode(r[0][1], len(eids))
        if dec is None:
            return "SCAN_MALFORMED"
        got.append([eids[i] for i in range(len(eids)) if dec[i] > 0])
    if _canon(got[0]) != _canon(got[1]):
        return "SCAN_RPCS_DISAGREE"
    if len(got[0]) > MAX_SCAN_IDS:
        return "SCAN_TOO_MANY"
    return got[0]


def ccip_scan(pool: str, block: int) -> typing.Any:
    try:
        r = dual_read(SOURCE_CHAIN, [eth_call(pool, S_CCIP_CHAINS, block)])
    except ReadFailed:
        return "SCAN_UNREADABLE"
    except Disagree:
        return "SCAN_RPCS_DISAGREE"
    ids = _abi_u64s(r[0])
    if ids is None:
        return "SCAN_MALFORMED"
    return sorted(ids)


def por_read(source_token: str, block: int) -> typing.Any:
    """Chainlink PoR for the source token at the pinned Ethereum block, from
    both RPCs: {feed, answer, decimals, updated_at, supply, supply_decimals},
    None if the token has no feed, or a reason string."""
    f = POR_FEEDS.get(source_token)
    if f is None:
        return None
    try:
        r = dual_read(SOURCE_CHAIN, [eth_call(f[0], S_LATEST_ROUND, block), eth_call(f[0], S_DECIMALS, block),
                                     eth_call(f[1], S_SUPPLY, block), eth_call(f[1], S_DECIMALS, block)])
    except ReadFailed:
        return "POR_UNREADABLE"
    except Disagree:
        return "POR_RPCS_DISAGREE"
    if not isinstance(r[0], list) or r[0][0] != "ok" or len(r[0][1]) < 2 + 64 * 5:
        return "POR_MALFORMED"
    h = r[0][1][2:]
    ans = int(h[64:128], 16)
    if ans >= 2 ** 255:
        return "POR_NEGATIVE"
    upd = int(h[192:256], 16)
    dec = _word(r[1])
    sup = _word(r[2])
    sdec = _word(r[3])
    if dec < 0 or dec > MAX_DECIMALS or sup < 0 or sdec < 0 or sdec > MAX_DECIMALS:
        return "POR_MALFORMED"
    return {"feed": f[0], "token": f[1], "answer": str(ans), "decimals": dec, "updated_at": upd, "supply": str(sup),
            "supply_decimals": sdec}


def pin_final(chain: str, block: int) -> dict:
    """Leader (block < 0): the lower of the two RPCs' finalized blocks.
    Validator: the leader's block, if final on both of its own RPCs and not
    more than LEADER_LAG_S older than its own finalized block."""
    try:
        low = finalized_low(chain)
    except ReadFailed:
        return {"refused": "RPC_UNREADABLE"}
    if low is None:
        return {"refused": "RPC_WRONG_CHAIN_OR_UNREADABLE"}
    n = low["number"] if block < 0 else block
    if n > low["number"]:
        return {"reject": "BLOCK_NOT_FINALIZED_FOR_VALIDATOR"}
    try:
        got = dual_read(chain, [get_block(n)])
    except ReadFailed:
        return {"refused": "RPC_UNREADABLE"}
    except Disagree:
        return {"refused": "RPC_DISAGREE_ON_PINNED_BLOCK"}
    blk = got[0]
    if blk is None or blk["number"] != n:
        return {"refused": "RPC_UNREADABLE"}
    if block >= 0 and blk["timestamp"] < low["timestamp"] - LEADER_LAG_S:
        return {"reject": "LEADER_BLOCK_TOO_OLD"}
    return {"block": blk}


def authenticate_at(p: dict, be: int, bd: int) -> dict:
    """The whole authentication at pinned blocks (be, bd < 0: leader picks)."""
    kind = p["kind"]
    dest = KINDS[kind]
    pe = pin_final(SOURCE_CHAIN, be)
    if "block" not in pe:
        return pe
    pd = pin_final(dest, bd)
    if "block" not in pd:
        return pd
    ne = pe["block"]["number"]
    nd = pd["block"]["number"]
    try:
        if kind == "arbitrum":
            a = _auth_arbitrum(p["source_token"], p["dest_token"], ne, nd)
        elif kind == "optimism" or kind == "base":
            a = _auth_opstack(kind, p["source_token"], p["dest_token"], ne, nd)
        elif kind == "op_dai":
            a = _auth_op_dai(p["source_token"], p["dest_token"], ne, nd)
        elif kind == "polygon":
            a = _auth_polygon(p["source_token"], p["dest_token"], ne, nd)
        elif kind.startswith("oft_"):
            a = _auth_oft(dest, p["source_token"], p["dest_token"], ne, nd)
        elif kind.startswith("wh_"):
            a = _auth_wormhole(dest, p["source_token"], p["dest_token"], ne, nd)
        elif kind.startswith("ccip_"):
            a = _auth_ccip(dest, p["source_token"], p["dest_token"], ne, nd)
        else:
            a = _auth_nomad(p["source_token"], p["dest_token"], ne, nd)
    except Refuse as e:
        return {"refused": "NOT_AUTHENTICATED: " + str(e)[:90], "blocks": [pe["block"], pd["block"]]}
    except ReadFailed:
        return {"refused": "RPC_UNREADABLE"}
    except Disagree:
        return {"refused": "RPC_DISAGREE"}
    except Exception:
        return {"refused": "MALFORMED_ANSWER"}
    a["source_block"] = pe["block"]
    a["dest_block"] = pd["block"]
    return a


def _req_ok(req: typing.Any) -> str:
    """Shape check of a registry's check request; "" if usable."""
    if not isinstance(req, dict) or req.get("ok") is not True:
        return "NOT_READABLE"
    if req.get("source_chain") != SOURCE_CHAIN:
        return "BAD_SOURCE_CHAIN"
    if _addr(req.get("source_token", "")) == "":
        return "BAD_ADDRESSES"
    vaults = req.get("vaults")
    if not isinstance(vaults, list) or len(vaults) < 1 or len(vaults) > MAX_VAULTS:
        return "BAD_VAULTS"
    for v in vaults:
        if _addr(v) == "" or vaults.count(v) != 1:
            return "BAD_VAULTS"
    dests = req.get("dests")
    blocks = req.get("blocks")
    if not isinstance(dests, list) or len(dests) < 1 or len(dests) > MAX_DESTS or not isinstance(blocks, dict):
        return "BAD_DESTS"
    for d in dests:
        if not isinstance(d, dict) or d.get("chain") not in CHAINS or _addr(d.get("token", "")) == "":
            return "BAD_DEST"
        dv = d.get("deposits_vault", "")
        if dv != "" and dv not in vaults:
            return "BAD_DEST"
    need = [SOURCE_CHAIN]
    for d in dests:
        if d["chain"] not in need:
            need.append(d["chain"])
    if sorted(need) != sorted(list(blocks.keys())):
        return "BLOCKS_DO_NOT_MATCH_CHAINS"
    for c in blocks:
        b = _as_int(blocks[c], -1)
        if b <= 0 or b > 10 ** 12:
            return "BAD_BLOCK_NUMBER"
    scans = req.get("scans", [])
    if not isinstance(scans, list) or len(scans) > MAX_VAULTS:
        return "BAD_SCANS"
    for s in scans:
        if not isinstance(s, list) or len(s) != 2 or s[0] not in vaults or s[1] not in ("LZ", "CCIP"):
            return "BAD_SCANS"
    ledgers = req.get("ledgers", [])
    if not isinstance(ledgers, list) or len(ledgers) > MAX_VAULTS:
        return "BAD_LEDGERS"
    for v in ledgers:
        if v != WH_ETH_BRIDGE or v not in vaults or ledgers.count(v) != 1:
            return "BAD_LEDGERS"
    anchors = req.get("anchors", [])
    if not isinstance(anchors, list) or len(anchors) > MAX_ANCHORS:
        return "BAD_ANCHORS"
    for a in anchors:
        if not isinstance(a, list) or len(a) != 3 or a[0] not in blocks or _addr(a[1]) == "":
            return "BAD_ANCHOR"
        if not isinstance(a[2], str) or not a[2].startswith("0x") or len(a[2]) > 330 or not _is_hex(a[2][2:]):
            return "BAD_ANCHOR_DATA"
    return ""


def read_at(req: dict) -> dict:
    """Everything a check needs, at the pinned blocks, from both RPCs.
    Always returns a record; INCONCLUSIVE carries the reason. Block headers
    are read first and kept when a later read fails, so an INCONCLUSIVE that
    is about the pair still says WHEN it was observed."""
    blocks = {}
    for c in req["blocks"]:
        blocks[c] = _as_int(req["blocks"][c], -1)
    out = {"status": "INCONCLUSIVE", "reason": "", "blocks": {}, "locked_by_vault": [], "source_decimals": -1,
           "dests": [], "anchors": []}
    names = sorted(list(blocks.keys()))
    anchors = req.get("anchors", [])
    # phase 1: finality, chain id and the pinned header, one batch per RPC per chain
    try:
        heads = {}
        for c in names:
            h = heads_at(c, blocks[c])
            if "header" not in h:
                out["reason"] = h["reason"]
                return out
            heads[c] = h["header"]
    except ReadFailed:
        return {"status": "PENDING"}
    except Disagree:
        return {"status": "PENDING"}
    except Exception:
        out["reason"] = "MALFORMED_ANSWER"
        return out
    out["blocks"] = heads
    # phase 2: balances, supplies, decimals, deposits at those blocks
    try:
        src = req["source_chain"]
        be = blocks[src]
        nv = len(req["vaults"])
        calls = [eth_call(req["source_token"], S_DECIMALS, be)]
        for v in req["vaults"]:
            calls.append(eth_call(req["source_token"], S_BALANCE + _pad(v), be))
        for d in req["dests"]:
            if d.get("deposits_vault", "") != "":
                calls.append(eth_call(d["deposits_vault"], S_DEPOSITS + _pad(req["source_token"]) + _pad(d["token"]), be))
        ledgers = req.get("ledgers", [])
        for v in ledgers:
            calls.append(eth_call(v, S_WH_OUTSTANDING + _pad(req["source_token"]), be))
        n_src = len(calls)
        for a in anchors:
            if a[0] == src:
                calls.append(eth_call(a[1], a[2], be))
        r = dual_read(src, calls)
        got = {}
        k = n_src
        for i in range(len(anchors)):
            if anchors[i][0] == src:
                got[i] = _w32(r[k])
                k += 1
        sdec = _word(r[0])
        held = []
        for j in range(nv):
            v = _word(r[1 + j])
            if v < 0:
                out["reason"] = "CALL_FAILED:" + src
                return out
            held.append(str(v))
        if sdec < 0 or sdec > MAX_DECIMALS:
            out["reason"] = "CALL_FAILED:" + src
            return out
        deps = []
        k = 1 + nv
        for d in req["dests"]:
            if d.get("deposits_vault", "") != "":
                v = _word(r[k])
                k += 1
                if v < 0:
                    out["reason"] = "CALL_FAILED:deposits"
                    return out
                deps.append(str(v))
            else:
                deps.append("")
        led = {}
        for v in ledgers:
            x = _word(r[k])
            k += 1
            if x < 0:
                out["reason"] = "CALL_FAILED:ledger"
                return out
            # outstandingBridged is kept in 8 decimals for tokens with more
            led[v] = str(x * (10 ** (sdec - 8)) if sdec > 8 else x)
        rows = []
        for c in names:
            if c == src:
                continue
            idx = []
            calls = []
            for i in range(len(req["dests"])):
                d = req["dests"][i]
                if d["chain"] == c:
                    idx.append(i)
                    calls.append(eth_call(d["token"], S_SUPPLY, blocks[c]))
                    calls.append(eth_call(d["token"], S_DECIMALS, blocks[c]))
            n_c = len(calls)
            for i in range(len(anchors)):
                if anchors[i][0] == c:
                    calls.append(eth_call(anchors[i][1], anchors[i][2], blocks[c]))
            g = dual_read(c, calls) if len(calls) > 0 else []
            k = n_c
            for i in range(len(anchors)):
                if anchors[i][0] == c:
                    got[i] = _w32(g[k])
                    k += 1
            for j in range(len(idx)):
                sup = _word(g[2 * j])
                dec = _word(g[2 * j + 1])
                if sup < 0 or dec < 0 or dec > MAX_DECIMALS:
                    out["reason"] = "CALL_FAILED:" + c
                    return out
                rows.append([idx[j], {"chain": c, "token": req["dests"][idx[j]]["token"], "supply": str(sup),
                                      "decimals": dec, "deposits": deps[idx[j]]}])
        rows = sorted(rows, key=lambda x: x[0])
        out["dests"] = [x[1] for x in rows]
        out["anchors"] = [got.get(i, "") for i in range(len(anchors))]
        out["locked_by_vault"] = held
        out["source_decimals"] = sdec
        out["ledgers"] = led
    except ReadFailed:
        return {"status": "PENDING"}
    except Disagree:
        return {"status": "PENDING"}
    except Exception:
        out["reason"] = "MALFORMED_ANSWER"
        return out
    # phase 3: coverage scans and Proof of Reserve. They never decide the
    # verdict; an unreadable one is recorded as such (and never counts as complete).
    cov = []
    for s in req.get("scans", []):
        ids = lz_scan(s[0], be) if s[1] == "LZ" else ccip_scan(s[0], be)
        cov.append({"vault": s[0], "family": s[1], "ids": ids if isinstance(ids, list) else [],
                    "error": ids if isinstance(ids, str) else ""})
    out["coverage"] = cov
    por = por_read(req["source_token"], be)
    out["por"] = por if isinstance(por, dict) else ({"error": por} if isinstance(por, str) else None)
    out["status"] = "OK"
    return out


# =============================================================================
# storage
# =============================================================================

@gl.storage.allow
@dataclass
class Auth:
    auth_id: u64
    kind: str
    source_chain: str
    vault: str
    source_token: str
    dest_chain: str
    dest_token: str
    source_decimals: u64
    dest_decimals: u64
    source_block: u64
    source_time: u64
    dest_block: u64
    dest_time: u64
    proof_json: str
    anchors_json: str
    read_at: u64
    reader: str


@gl.storage.allow
@dataclass
class Reading:
    key: str
    registry: str
    check_id: u64
    round: u64
    request_sha: str
    status: str
    reason: str
    reading_json: str
    read_at: u64
    reader: str


@gl.storage.allow
@dataclass
class Pending:
    key: str
    attempts: u64
    first_at: u64
    last_at: u64
    last_by: str


class ChainReader(gl.contract.Contract):
    n_auth: u64
    auths: gl.storage.TreeMap[u64, Auth]
    readings: gl.storage.TreeMap[str, Reading]
    n_readings: u64
    pendings: gl.storage.TreeMap[str, Pending]
    n_pending: u64

    def __init__(self) -> None:
        self.n_auth = u64(0)
        self.n_readings = u64(0)
        self.n_pending = u64(0)

    def _now(self) -> int:
        return _epoch_from_iso(gl.message.raw.get("datetime", ""))

    @gl.public.write
    def authenticate(self, kind: str, source_token: str, dest_token: str) -> typing.Any:
        """Prove (kind, source_token, dest_token) is one bridge's pair, from the
        bridge's own mapping on both chains. Refused if not proved."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        k = str(kind).strip().lower()
        if k not in KINDS:
            raise gl.vm.UserError("REFUSED: UNSUPPORTED_BRIDGE_KIND")
        l1 = _addr(source_token)
        l2 = _addr(dest_token)
        if not _nonzero(l1) or not _nonzero(l2):
            raise gl.vm.UserError("REFUSED: BAD_TOKEN_ADDRESS")
        p = {"kind": k, "source_token": l1, "dest_token": l2}

        def leader() -> dict:
            return authenticate_at(p, -1, -1)

        def validator(res: gl.vm.Result) -> bool:
            if not isinstance(res, gl.vm.Return):
                return False
            got = res.calldata
            if not isinstance(got, dict):
                return False
            if "source_block" in got:
                mine = authenticate_at(p, int(got["source_block"]["number"]), int(got["dest_block"]["number"]))
            elif "blocks" in got and isinstance(got["blocks"], list) and len(got["blocks"]) == 2:
                mine = authenticate_at(p, int(got["blocks"][0]["number"]), int(got["blocks"][1]["number"]))
            else:
                mine = authenticate_at(p, -1, -1)
                if "refused" in got and "refused" in mine:
                    return True
            return _canon(mine) == _canon(got)

        a = gl.vm.run_nondet(leader, validator)
        if not isinstance(a, dict):
            raise gl.vm.UserError("REFUSED: UNREADABLE")
        if "refused" in a:
            raise gl.vm.UserError("REFUSED: " + str(a["refused"])[:120])
        if "reject" in a:
            raise gl.vm.UserError("REFUSED: " + str(a["reject"])[:120])
        # --- writes
        aid = int(self.n_auth) + 1
        self.auths[u64(aid)] = Auth(
            auth_id=u64(aid), kind=k, source_chain=SOURCE_CHAIN, vault=a["vault"], source_token=l1,
            dest_chain=KINDS[k], dest_token=a.get("dest_token", l2), source_decimals=u64(int(a["source_decimals"])),
            dest_decimals=u64(int(a["dest_decimals"])), source_block=u64(int(a["source_block"]["number"])),
            source_time=u64(int(a["source_block"]["timestamp"])), dest_block=u64(int(a["dest_block"]["number"])),
            dest_time=u64(int(a["dest_block"]["timestamp"])), proof_json=_canon(a["proof"]),
            anchors_json=_canon(a["anchors"]), read_at=u64(now),
            reader=gl.message.sender_address.as_hex.lower())
        self.n_auth = u64(aid)
        return {"auth_id": aid, "vault": a["vault"], "dest_token": a.get("dest_token", l2), "family": family(k),
                "remote": remote_id(k),
                "source_decimals": int(a["source_decimals"]),
                "dest_decimals": int(a["dest_decimals"])}

    @gl.public.write
    def read_check(self, registry: str, check_id: int, round_no: int) -> typing.Any:
        """Read one check of `registry` at its pinned blocks. Anyone may call."""
        now = self._now()
        if now <= 0:
            raise gl.vm.UserError("REFUSED: NO_CLOCK")
        reg = _addr(registry)
        cid = _as_int(check_id, -1)
        rnd = _as_int(round_no, -1)
        if reg == "" or cid <= 0 or rnd < 1 or rnd > 2:
            raise gl.vm.UserError("REFUSED: BAD_ARGUMENTS")
        key = reg + "|" + str(cid) + "|" + str(rnd)
        if self.readings.get(key) is not None:
            raise gl.vm.UserError("REFUSED: ALREADY_READ")
        try:
            req = gl.contract.get_at(Address(reg)).view().get_check_request(cid)
        except Exception:
            raise gl.vm.UserError("REFUSED: REGISTRY_UNREADABLE")
        if isinstance(req, str):
            try:
                req = json.loads(req)
            except Exception:
                raise gl.vm.UserError("REFUSED: REQUEST_UNREADABLE")
        bad = _req_ok(req)
        if bad != "":
            raise gl.vm.UserError("REFUSED: REQUEST_" + bad)
        if _as_int(req.get("round"), -1) != rnd or _as_int(req.get("check_id"), -1) != cid:
            raise gl.vm.UserError("REFUSED: NOT_THIS_ROUND")
        read_by = _as_int(req.get("read_by"), -1)
        if read_by <= 0 or now > read_by:
            raise gl.vm.UserError("REFUSED: READ_WINDOW_CLOSED_AT_" + str(read_by))
        # the request (blocks, vaults, tokens, anchors) comes from the registry's
        # state, read here before the non-deterministic block: every validator
        # reads exactly these, never a range or a block the leader names
        frozen = json.loads(_canon(req))

        def leader() -> dict:
            return read_at(frozen)

        def validator(res: gl.vm.Result) -> bool:
            if not isinstance(res, gl.vm.Return):
                return False
            return _canon(read_at(frozen)) == _canon(res.calldata)

        r = gl.vm.run_nondet(leader, validator)
        if not isinstance(r, dict) or r.get("status") not in ("OK", "INCONCLUSIVE", "PENDING"):
            raise gl.vm.UserError("REFUSED: UNREADABLE")
        if r["status"] == "PENDING":
            # a transport failure (an RPC down, throttling, or its two RPCs
            # answering differently) is no reading: nothing is stored for the
            # check, which stays open until its fixed deadline; anyone retries.
            # A validator agrees with a PENDING leader only when its own read
            # failed the same way.
            pd = self.pendings.get(key)
            if pd is None:
                self.pendings[key] = Pending(key=key, attempts=u64(1), first_at=u64(now), last_at=u64(now),
                                             last_by=gl.message.sender_address.as_hex.lower())
            else:
                pd.attempts = u64(int(pd.attempts) + 1)
                pd.last_at = u64(now)
                pd.last_by = gl.message.sender_address.as_hex.lower()
            self.n_pending = u64(int(self.n_pending) + 1)
            return {"key": key, "status": "PENDING", "retry_until": read_by}
        # --- writes
        self.readings[key] = Reading(key=key, registry=reg, check_id=u64(cid), round=u64(rnd),
                                     request_sha=_sha(_canon(frozen)), status=r["status"], reason=str(r["reason"]),
                                     reading_json=_canon(r), read_at=u64(now),
                                     reader=gl.message.sender_address.as_hex.lower())
        self.n_readings = u64(int(self.n_readings) + 1)
        return {"key": key, "status": r["status"], "reason": r["reason"]}

    # --- views (storage only) -------------------------------------------------

    def _auth_view(self, a: Auth) -> dict:
        return {"auth_id": int(a.auth_id), "kind": a.kind, "source_chain": a.source_chain, "vault": a.vault,
                "source_token": a.source_token, "dest_chain": a.dest_chain, "dest_token": a.dest_token,
                "source_decimals": int(a.source_decimals), "dest_decimals": int(a.dest_decimals),
                "source_block": int(a.source_block), "source_time": int(a.source_time),
                "dest_block": int(a.dest_block), "dest_time": int(a.dest_time),
                "proof": json.loads(a.proof_json), "anchors": json.loads(a.anchors_json), "read_at": int(a.read_at),
                "reader": a.reader, "family": family(a.kind), "remote": remote_id(a.kind)}

    @gl.public.view
    def get_auth(self, auth_id: int) -> typing.Any:
        a = self.auths.get(u64(max(_as_int(auth_id, 0), 0)))
        if a is None:
            return {"found": False}
        out = self._auth_view(a)
        out["found"] = True
        return out

    @gl.public.view
    def get_reading(self, registry: str, check_id: int, round_no: int) -> typing.Any:
        key = _addr(registry) + "|" + str(_as_int(check_id, -1)) + "|" + str(_as_int(round_no, -1))
        r = self.readings.get(key)
        if r is None:
            pd = self.pendings.get(key)
            if pd is None:
                return {"found": False, "pending": 0}
            return {"found": False, "pending": int(pd.attempts), "pending_first_at": int(pd.first_at),
                    "pending_last_at": int(pd.last_at)}
        return {"found": True, "key": r.key, "registry": r.registry, "check_id": int(r.check_id),
                "round": int(r.round), "request_sha": r.request_sha, "status": r.status, "reason": r.reason,
                "reading": json.loads(r.reading_json), "read_at": int(r.read_at), "reader": r.reader}

    @gl.public.view
    def get_config(self) -> typing.Any:
        return {"version": VERSION, "contract": "ChainReader", "source_chain": SOURCE_CHAIN,
                "chains": {k: {"chain_id": CHAINS[k][0], "rpcs": list(CHAINS[k][1])} for k in CHAINS},
                "kinds": KINDS, "deposit_kinds": list(DEPOSIT_KINDS), "leader_lag_s": LEADER_LAG_S,
                "layerzero_endpoint": LZ_ENDPOINT, "layerzero_endpoints": LZ_ENDPOINTS, "layerzero_eids": LZ_EID,
                "arbitrum_escrow_gateways": ARB_ESCROW_GATEWAYS, "polygon_erc20_type": POL_ERC20_TYPE,
                "auths": int(self.n_auth), "readings": int(self.n_readings), "pending_attempts": int(self.n_pending),
                "scan_rpcs": list(SCAN_RPCS), "lz_scan": list(LZ_SCAN), "multicall3": MULTICALL3,
                "wormhole": {"ethereum_bridge": WH_ETH_BRIDGE, "dests": WH_DESTS},
                "ccip": {"ethereum_selector": str(CCIP_ETH_SELECTOR), "ethereum_registry": CCIP_ETH_TAR,
                         "dests": {c: [str(CCIP_DESTS[c][0]), CCIP_DESTS[c][1]] for c in CCIP_DESTS}},
                "por_feeds": POR_FEEDS, "transient": list(TRANSIENT)}
