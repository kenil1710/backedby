// The chains, RPCs and bridge constants used by the off-chain tools. The
// contracts carry their own copies (contracts/shared/*.py); tools/match.mjs
// checks the two agree.
export const CHAINS = {
  ethereum: { id: 1, rpcs: ["https://eth-pokt.nodies.app", "https://rpc.mevblocker.io"], explorer: "https://etherscan.io" },
  arbitrum: { id: 42161, rpcs: ["https://arb-pokt.nodies.app", "https://arbitrum.gateway.tenderly.co"], explorer: "https://arbiscan.io" },
  optimism: { id: 10, rpcs: ["https://mainnet.optimism.io", "https://optimism.drpc.org"], explorer: "https://optimistic.etherscan.io" },
  base: { id: 8453, rpcs: ["https://mainnet.base.org", "https://base.drpc.org"], explorer: "https://basescan.org" },
  polygon: { id: 137, rpcs: ["https://polygon.drpc.org", "https://polygon.gateway.tenderly.co"], explorer: "https://polygonscan.com" },
  moonbeam: { id: 1284, rpcs: ["https://moonbeam.drpc.org", "https://moonbeam.api.onfinality.io/public"], explorer: "https://moonscan.io" },
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
