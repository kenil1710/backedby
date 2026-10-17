// The chains, RPCs and bridge constants used by the off-chain tools. The
// contracts carry their own copies (contracts/shared/*.py); tools/match.mjs
// checks the two agree.
export const CHAINS = {
  ethereum: { id: 1, rpcs: ["https://eth-pokt.nodies.app", "https://rpc.mevblocker.io"], explorer: "https://etherscan.io" },
  arbitrum: { id: 42161, rpcs: ["https://arb-pokt.nodies.app", "https://arbitrum.gateway.tenderly.co"], explorer: "https://arbitrum.blockscout.com" },
  optimism: { id: 10, rpcs: ["https://mainnet.optimism.io", "https://optimism.drpc.org"], explorer: "https://optimism.blockscout.com" },
  base: { id: 8453, rpcs: ["https://base-pokt.nodies.app", "https://base.drpc.org"], explorer: "https://base.blockscout.com" },
  polygon: { id: 137, rpcs: ["https://polygon.drpc.org", "https://rpc-mainnet.matic.quiknode.pro"], explorer: "https://polygon.blockscout.com" },
  moonbeam: { id: 1284, rpcs: ["https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public"], explorer: "https://moonbeam.subscan.io" },
  mantle: { id: 5000, rpcs: ["https://rpc.mantle.xyz", "https://mantle.drpc.org"], explorer: "https://explorer.mantle.xyz" },
  xlayer: { id: 196, rpcs: ["https://xlayerrpc.okx.com", "https://xlayer.drpc.org"], explorer: "https://www.oklink.com/xlayer" },
  sei: { id: 1329, rpcs: ["https://evm-rpc.sei-apis.com", "https://sei.api.pocket.network"], explorer: "https://seitrace.com" },
  flare: { id: 14, rpcs: ["https://flare-api.flare.network/ext/C/rpc", "https://rpc.ankr.com/flare"], explorer: "https://flare-explorer.flare.network" },
  hedera: { id: 295, rpcs: ["https://mainnet.hashio.io/api", "https://hedera.linkpool.pro"], explorer: "https://hashscan.io/mainnet" },
  unichain: { id: 130, rpcs: ["https://mainnet.unichain.org", "https://unichain.drpc.org"], explorer: "https://unichain.blockscout.com" },
  morph: { id: 2818, rpcs: ["https://rpc.morphl2.io", "https://rpc-quicknode.morphl2.io"], explorer: "https://explorer.morphl2.io" },
  ink: { id: 57073, rpcs: ["https://rpc-gel.inkonchain.com", "https://ink.drpc.org"], explorer: "https://explorer.inkonchain.com" },
  berachain: { id: 80094, rpcs: ["https://rpc.berachain.com", "https://berachain.drpc.org"], explorer: "https://berascan.com" },
  hyperevm: { id: 999, rpcs: ["https://rpc.hyperliquid.xyz/evm", "https://hyperliquid.drpc.org"], explorer: "https://hyperevmscan.io" },
  monad: { id: 143, rpcs: ["https://rpc.monad.xyz", "https://monad-mainnet-rpc.spidernode.net"], explorer: "https://monadscan.com" },
};

export const BRIDGE = {
  arb_l1_router: "0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef",
  arb_l2_router: "0x5288c571fd7ad117bea99bf60fe0846c4e84f933",
  op_l1_bridge: "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1",
  base_l1_bridge: "0x3154cf16ccdb4c6d922629664174b904d80f2c35",
  l2_std_bridge: "0x4200000000000000000000000000000000000010",
  op_dai_l1_bridge: "0x10e6593cdda8c58a1d0f14c5164b376352a55f2f",
  op_dai_l2_bridge: "0x467194771dae2967aef3ecbedd3bf9a310c76c65",
  pol_root_manager: "0xa0c68c638235ee32657e8f720a23cec1bfc77c77",
  pol_child_manager: "0xa6fa4fb5f76172d178d61b04b0ecd319c5d1c0aa",
  nomad_eth_router: "0x88a69b4e698a4b090df6cf5bd7b2d47325ad30a3",
  nomad_beam_router: "0xd3dfd3ede74e0dcebc1aa685e151332857efce2d",
  nomad_eth_domain: 6648936,
};

// USDT0: every chain where Ethereum's adapter (0x6c96...1dee) has a LayerZero
// peer and two independent RPCs serve the finalized tag and identical answers
// (docs/SEEDS.md lists the peers left out and why). Polygon's is the pair's
// own first destination. Hedera's entry is its OFT: its token() is the native
// HTS token, which ChainReader derives.
export const USDT0_DESTS = [
  ["oft_arbitrum", "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"],
  ["oft_optimism", "0x01bff41798a0bcf287b996046ca68b395dbc1071"],
  ["oft_mantle", "0x779ded0c9e1022225f8e0630b35a9b54be713736"],
  ["oft_xlayer", "0x779ded0c9e1022225f8e0630b35a9b54be713736"],
  ["oft_sei", "0x9151434b16b9763660705744891fa906f660ecc5"],
  ["oft_flare", "0xe7cd86e13ac4309349f30b3435a9d337750fc82d"],
  ["oft_hedera", "0xe3119e23fc2371d1e6b01775ba312035425a53d6"],
  ["oft_unichain", "0x9151434b16b9763660705744891fa906f660ecc5"],
  ["oft_morph", "0xe7cd86e13ac4309349f30b3435a9d337750fc82d"],
  ["oft_ink", "0x0200c29006150606b650577bbe7b6248f58470c1"],
  ["oft_berachain", "0x779ded0c9e1022225f8e0630b35a9b54be713736"],
  ["oft_hyperevm", "0xb8ce59fc3717ada4c02eadf9682a9e934f625ebb"],
  ["oft_monad", "0xe7cd86e13ac4309349f30b3435a9d337750fc82d"],
];

export const L1 = {
  USDC: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  USDT: "0xdac17f958d2ee523a2206206994597c13d831ec7",
  DAI: "0x6b175474e89094c44da98b954eedeac495271d0f",
  WBTC: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
  LINK: "0x514910771af9ca656af840dff83e8264ecf986ca",
  UNI: "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
  AAVE: "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
  CRV: "0xd533a949740bb3306d119cc777fa900ba034cd52",
  LDO: "0x5a98fcbea516cf06857215779fd812ca3bef1b32",
  wstETH: "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",
  WETH: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
  cbETH: "0xbe9895146f7af43049ca1c1ae358b0541ea49704",
  rETH: "0xae78736cd615f374d3085123a210448e74fc6393",
};

/** An explorer link; Subscan (Moonbeam) names addresses "account" and tokens "erc20_token". */
export function explorerLink(chain, kind, value) {
  const base = CHAINS[chain].explorer;
  if (chain === "moonbeam") kind = { address: "account", token: "erc20_token" }[kind] ?? kind;
  return `${base}/${kind}/${value}`;
}
