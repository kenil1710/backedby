// Display names and the known tokens, for labels only. Every number comes from the contracts.
export const CHAIN_NAME: Record<string, string> = {
  ethereum: "Ethereum", arbitrum: "Arbitrum One", optimism: "OP Mainnet", base: "Base", polygon: "Polygon PoS", moonbeam: "Moonbeam",
};
export const KIND_NAME: Record<string, string> = {
  arbitrum: "Arbitrum canonical bridge", optimism: "OP Standard Bridge", base: "Base Standard Bridge",
  op_dai: "OP DAI bridge", polygon: "Polygon PoS bridge", nomad: "Nomad",
};
export const TOKEN_SYMBOL: Record<string, string> = {
  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC", "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
  "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
  "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK", "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "UNI",
  "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": "AAVE", "0xd533a949740bb3306d119cc777fa900ba034cd52": "CRV",
  "0x5a98fcbea516cf06857215779fd812ca3bef1b32": "LDO", "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "wstETH",
  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH", "0xbe9895146f7af43049ca1c1ae358b0541ea49704": "cbETH",
  "0xae78736cd615f374d3085123a210448e74fc6393": "rETH",
};
export const symbolOf = (a: string) => TOKEN_SYMBOL[a?.toLowerCase()] ?? `${a.slice(0, 6)}…${a.slice(-4)}`;
