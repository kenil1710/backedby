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
    def pay_balance(self, to: str, amt: int, budget: int) -> None:
        fp = gl.chain.InternalMessageParams(u256(100), u256(200), u256(budget), [u256(3)], u256(2), u256(300000000), u256(300000000))
        gl.contract.get_at(Address(to)).emit_transfer(u256(amt), use_balance=True, fee_params=fp)

    @gl.public.write
    def pay_balance_decided(self, to: str, amt: int, budget: int) -> None:
        fp = gl.chain.InternalMessageParams(u256(100), u256(200), u256(budget), [u256(3)], u256(2), u256(300000000), u256(300000000))
        gl.contract.get_at(Address(to)).emit_transfer(u256(amt), on="decided", use_balance=True, fee_params=fp)

    @gl.public.view
    def bal(self) -> int:
        return int(self.balance)
