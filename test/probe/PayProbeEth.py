# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *

# Throwaway: which emit_transfer form actually delivers GEN on Studio Dev.


class PayProbe(gl.contract.Contract):
    n: u256

    def __init__(self):
        self.n = u256(0)

    @gl.public.write.payable
    def fund(self) -> None:
        self.n = u256(int(self.n) + 1)

    @gl.public.write
    def pay_default(self, to: str, amt: int) -> None:
        gl.chain.Account(Address(to)).emit_transfer(u256(amt))

    @gl.public.write
    def pay_decided(self, to: str, amt: int) -> None:
        gl.chain.Account(Address(to)).emit_transfer(u256(amt), on="decided")

    @gl.public.write
    def pay_eth(self, to: str, amt: int) -> None:
        gl.evm.Account(Address(to)).emit_call(u256(amt), b"")

    @gl.public.view
    def bal(self) -> int:
        return int(self.balance)
