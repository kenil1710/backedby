# BackedBy v2 milestone

## BASE

BASE is commit `9e7d255d24d5fe973678b774c788bb12602368a0`, the head of the accepted BackedBy submission. Its contracts were deployed from
`047d3406d5c78f4cbb1913012bd5df249998fcb5`; `contracts/` and `build/` did not change between that commit and BASE.

Proof (`node tools/base_proof.mjs 9e7d255`, read 2026-11-14T06:19:15.634Z, raw result in [base-proof.json](base-proof.json)): each
address's code was read from Studio Dev with `gen_getContractCode` and compared byte for byte with the build file at
its deploy commit; the accepted set also with the build file at BASE. Every one is identical.

| Set | Contract | Address | Deploy commit | Bytes | sha256 (on chain = build file) |
|---|---|---|---|---|---|
| accepted | ChainReader | `0x7d0C1Ccc40A8ECB5a82a3879C78F503E7ECac35C` | `047d340` | 50058 | `a8d4f3ff0b62e485a8546c961db59e44978eb0d24ba96ccd12a34b1bc5b004a7` |
| accepted | BackedByRegistry | `0x66BA2FF893f5FaAf21f000286A5e34BBDB9c8102` | `047d340` | 65636 | `14c42a676e00f96dc686086b2776563f00ab5f6fdc8dcccfcbb6040641a96724` |
| accepted | BackedByRegistryDemo | `0x0Cf85aC9650f7957D74224561DF6667a769AF20f` | `047d340` | 65636 | `14c42a676e00f96dc686086b2776563f00ab5f6fdc8dcccfcbb6040641a96724` |
| accepted | CollateralGate | `0x78d4Bbfc42Ebc94A18Aee6557079215881bA3aD8` | `047d340` | 12274 | `2f84b3fd462670eadab910c2ffa02b704a23b770c158fc7d43ec0cece8808492` |
| accepted | CollateralGateDemo | `0x77F394DD1E2D7226621C37c7F6887D340B4D194F` | `047d340` | 12274 | `2f84b3fd462670eadab910c2ffa02b704a23b770c158fc7d43ec0cece8808492` |
| retired 6f9431f | ChainReader | `0x0F4ba6e25Deb78B977B71CBf54d13eD263510319` | `6f9431f` | 46972 | `7abbb98cf4823c1859572187784489ab242ed0cead0bc56ac88b001eb94a3a74` |
| retired 6f9431f | BackedByRegistry | `0x09b185B68B6d2f27D7d7Be3c4918e4dD0DFe0c6e` | `6f9431f` | 63547 | `4941c5defbb7cf3604d810a0911869bda4ec6ed8290da99cb0472c800b8538b8` |
| retired 6f9431f | BackedByRegistryDemo | `0xBb87c7D651a61041ED3ED7EB8059034634a528a1` | `6f9431f` | 63547 | `4941c5defbb7cf3604d810a0911869bda4ec6ed8290da99cb0472c800b8538b8` |
| retired 6f9431f | CollateralGate | `0xF19f7E68661d2267324277005041B6655be7B58c` | `6f9431f` | 11245 | `764bf95b37fc9b73d86c0b1f4f4b045e98ed67baefdee4986df3a0b6982e2c56` |
| retired 6f9431f | CollateralGateDemo | `0xB8b50FE0Ef0CdeF3163fA0a1743ED1558D8484A4` | `6f9431f` | 11245 | `764bf95b37fc9b73d86c0b1f4f4b045e98ed67baefdee4986df3a0b6982e2c56` |
| retired e915d21 | ChainReader | `0x73217767D2F71cdc9D22b19e65d7aA8926D328B9` | `e915d21` | 42598 | `5a141b225eb1b46943d189d337ce81e28f416b907cbc6db823afced601abb0fd` |
| retired e915d21 | BackedByRegistry | `0xB136AaB44b83e3408Ef1a421801271dba8Ff1DeD` | `e915d21` | 58680 | `358403350b9e37499b4576c9cd7950c6d510ad9f083c8fa41db1606c073b24b9` |
| retired e915d21 | BackedByRegistryDemo | `0xCA8b9d4E3Fa93A7A012306Fa443D71E9e42A45b6` | `e915d21` | 58680 | `358403350b9e37499b4576c9cd7950c6d510ad9f083c8fa41db1606c073b24b9` |
| retired e915d21 | CollateralGate | `0x2B7A38AaDF934887b2f6A4b057D63e99259aA831` | `e915d21` | 11242 | `e0b6ab99a08b23d64bb0e84bf809efb41a36ec2732dd3f1963b10b5c90068063` |
| retired e915d21 | CollateralGateDemo | `0x6F049473c968ce668Aebd46239CDFcCf8554086d` | `e915d21` | 11242 | `e0b6ab99a08b23d64bb0e84bf809efb41a36ec2732dd3f1963b10b5c90068063` |

v1 is left untouched: no v1 contract is written to by the milestone, and v2 is deployed at new addresses.

### v1 registry balances (`eth_getBalance`, read with the proof)

| Set | Registry | Address | eth_getBalance (wei) |
|---|---|---|---|
| accepted | BackedByRegistry | `0x66BA2FF893f5FaAf21f000286A5e34BBDB9c8102` | 0 |
| accepted | BackedByRegistryDemo | `0x0Cf85aC9650f7957D74224561DF6667a769AF20f` | 0 |
| retired 6f9431f | BackedByRegistry | `0x09b185B68B6d2f27D7d7Be3c4918e4dD0DFe0c6e` | 0 |
| retired 6f9431f | BackedByRegistryDemo | `0xBb87c7D651a61041ED3ED7EB8059034634a528a1` | 140000000000000000 |
| retired e915d21 | BackedByRegistry | `0xB136AaB44b83e3408Ef1a421801271dba8Ff1DeD` | 0 |
| retired e915d21 | BackedByRegistryDemo | `0xCA8b9d4E3Fa93A7A012306Fa443D71E9e42A45b6` | 140000000000000000 |

The two retired demo registries each hold 0.14 GEN: they paid with internal transfers, which Studio Dev skipped and
credited back to the contract ([superseded/6f9431f](superseded/6f9431f/README.md)). The accepted registries, which pay
with external sends, are at 0.

### Tests at BASE

| Suite | Tests |
|---|---|
| Offline contract tests (`python3 -m unittest`, test/) | 467 |
| Payout fee guard and delivery (`node --test test/payout.test.mjs`) | 12 |
| Total | 479 |
