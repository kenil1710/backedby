// v2 bridge constants shared by the off-chain tools (the contract carries its
// own copy in contracts/ChainReader.py; test_static checks the two agree).
export const MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11";
// Ethereum RPCs for coverage scans: one Multicall3 call of 600 entries at a
// pinned block (the check RPCs refuse a request body that large)
export const SCAN_RPCS = ["https://rpc.mevblocker.io", "https://eth-mainnet.public.blastapi.io"];
export const LZ_SCAN = [30101, 30700];            // every LayerZero v2 eid in this range is scanned
export const WH = {
  eth_bridge: "0x3ee18b2214aff97000d974cf647e7c347e8fa585",
  eth_id: 2,
  // chain -> [wormhole chain id, token bridge]
  dests: {
    polygon: [5, "0x5a58505a96d1dbf8df91cb21b54419fc36e93fde"],
    arbitrum: [23, "0x0b2402144bb366a632d14b83f244d2e0e21bd39c"],
    optimism: [24, "0x1d68124e65fafc907325e3edbf8c4d84499daa8b"],
    base: [30, "0x8d2de8d2f73f1f4cab472ac9a881c9b123c79627"],
  },
};
export const CCIP = {
  eth_selector: "5009297550715157269",
  eth_tar: "0xb22764f98dd05c789929716d677382df22c05cb6",
  // chain -> [selector, TokenAdminRegistry]
  dests: {
    arbitrum: ["4949039107694359620", "0x39ae1032cf4b334a1ed41cdd0833bdd7c7e7751e"],
    base: ["15971525489660198786", "0x6f6c373d09c07425baae72317863d7f6bb731e37"],
    optimism: ["3734403246176062136", "0x657c42abe4cd8aa731aec322f871b5b90cf6274f"],
    polygon: ["4051577828743386545", "0x00f027ea6d0fb03256a15e9182b2b9227a4931d8"],
    mantle: ["1556008542357238666", "0x000a744940eb5d857c0d61d97015dfc83107404f"],
    xlayer: ["3016212468291539606", "0xecf1eaee01e82f3388decd7f4c3792374f3f72f3"],
    monad: ["8481857512324358265", "0x11acd984dd680363117b310f6ebdf78fd6c0195f"],
    ink: ["3461204551265785888", "0xeb062d21c713a3d940bb0faecfdc387d6ea23697"],
    unichain: ["1923510103922296319", "0xab3ee2e897cf23c10e76d26ab4674fefa376bc0d"],
    sei: ["9027416829622342829", "0x910a46ca93e8086bf1d7d65190ee6aee5256bd61"],
    berachain: ["1294465214383781161", "0x0944c3fb1db7d165336569221995b31cbe6c8a55"],
    hyperevm: ["2442541497099098535", "0xce44363496abc3a9e53b3f404a740f992d977bdf"],
  },
};
// Chainlink Proof of Reserve feeds on Ethereum: source token -> [feed, token whose supply the feed covers, name]
export const POR = {
  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ["0xa81fe04086865e63e12dd3776978e49deea2ea4e", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "WBTC PoR"],
  "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": ["0xad410e655c0fe4741f573152592eeb766e686ce7", "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", "stETH PoR"],
  "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee": ["0xc8cd82067ea907ea4af81b625d2bb653e21b5156", "0x35fa164735182de50811e8e2e824cfb9b6118ac2", "eETH PoR"],
};
