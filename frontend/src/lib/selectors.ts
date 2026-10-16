export const SELECTOR: Record<string, string> = {
  "0xbda009fe": "getGateway(l1)", "0xa7e28d48": "calculateL2TokenAddress(l1)", "0x000cc9e6": "l1Escrow()",
  "0xd6c0b2c4": "remoteToken()", "0xc01e1bd6": "l1Token()", "0xe78cea92": "bridge()", "0xae1f6aaf": "l2Bridge()",
  "0x56eff267": "l2Token()", "0xe2fdcc17": "escrow()", "0xea60c7c4": "rootToChildToken(l1)", "0xe43009a6": "tokenToType(l1)",
  "0xe66f9603": "typeToPredicate(ERC20)", "0x6e86b770": "childToRootToken(child)", "0x9d23c4c7": "tokenRegistry()",
  "0x83bbb806": "remotes(eth)", "0x589b3c64": "getLocalAddress(eth, l1)",
};
export const selName = (data: string) => SELECTOR[data.slice(0, 10)] ?? data.slice(0, 10);
