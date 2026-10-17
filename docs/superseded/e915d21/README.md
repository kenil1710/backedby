# Superseded: deployment from e915d21

Records of the first deployment (contracts from commit `e915d21`), kept as they were. That version had one vault
per pair, so USDT on Polygon read UNDER_BACKED (0.64%) against the PoS predicate alone although USDT0's LayerZero
adapter also backs it, and it counted OP/Base supply as `min(totalSupply, deposits)`. Both were fixed in `bf24598`
(see docs/ATTACK_REPORT.md, H1 revised and H4); everything was then redeployed from one commit and re-seeded.
