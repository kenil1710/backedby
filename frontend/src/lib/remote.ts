// Names for the ids under which a vault's own bridge config lists a
// destination: LayerZero eids, CCIP chain selectors, Wormhole chain ids.
import CCIP from "./ccip-names.json";
import { CHAIN_NAME } from "./chains";

// LayerZero v2 mainnet eids (LayerZero's deployments list); only names stated there
const LZ: Record<string, string> = {
  "30101": "Ethereum", "30102": "BNB Chain", "30106": "Avalanche", "30108": "Aptos", "30109": "Polygon PoS", "30110": "Arbitrum One",
  "30111": "OP Mainnet", "30125": "Celo", "30145": "Gnosis", "30165": "zkSync Era", "30168": "Solana", "30181": "Mantle", "30183": "Linea",
  "30184": "Base", "30214": "Scroll", "30243": "Blast", "30260": "Mode", "30274": "X Layer", "30280": "Sei", "30295": "Flare",
  "30316": "Hedera", "30320": "Unichain", "30322": "Morph", "30339": "Ink", "30362": "Berachain", "30367": "HyperEVM", "30390": "Monad",
};
const WH: Record<string, string> = { "5": "Polygon PoS", "23": "Arbitrum One", "24": "OP Mainnet", "30": "Base" };
const ccip = CCIP as Record<string, { chain_id: number; name: string }>;

export function remoteName(id: string): string {
  const [fam, n] = id.split(":");
  if (fam === "lz") return LZ[n] ? `${LZ[n]} (LayerZero eid ${n})` : `LayerZero eid ${n}`;
  if (fam === "ccip") return ccip[n] ? `${ccip[n].name} (chain id ${ccip[n].chain_id})` : `CCIP selector ${n}`;
  if (fam === "wh") return WH[n] ? `${WH[n]} (Wormhole chain ${n})` : `Wormhole chain ${n}`;
  const chain = id.split(":")[1];
  return CHAIN_NAME[chain] ?? id;
}

export const FAMILY_TEXT: Record<string, string> = {
  MAPPING: "the bridge maps this token to exactly one destination",
  LEDGER: "the bridge's own ledger of what it owes on every chain is counted",
  LZ: "every LayerZero eid 30101-31100 scanned for a peer",
  CCIP: "the pool's supported chains",
  OPEN: "this bridge cannot be enumerated on chain",
};
