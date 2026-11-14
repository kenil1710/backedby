"""ChainReader's v2 bridge templates in GenLayer's Direct Mode (genlayer-test):
the deployed bytes on the official SDK, every RPC mocked by URL. Covers
Wormhole and CCIP authentication, validator agreement, validator disagreement
when its own RPCs answer differently, forged leader results and errors, an
RPC down, and two RPCs of a chain disagreeing."""
import pytest

from conftest import (BASE_GHO, C, GHO, GHO_POOL, USDC, WH_ARB_USDC, A, W, map_ccip, map_wormhole)


def test_wormhole_pair_is_authenticated(direct_vm, net, reader):
    map_wormhole(net)
    r = reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)
    assert r["vault"] == C["WH_ETH_BRIDGE"] and r["family"] == "LEDGER" and r["remote"] == "wh:23", r
    a = reader.get_auth(r["auth_id"])
    assert a["found"] and a["dest_token"] == WH_ARB_USDC and len(a["anchors"]) == 4


def test_ccip_pair_is_authenticated(direct_vm, net, reader):
    map_ccip(net)
    r = reader.authenticate("ccip_base", GHO, BASE_GHO)
    assert r["vault"] == GHO_POOL and r["family"] == "CCIP", r


def test_validator_agrees_on_the_same_data(direct_vm, net, reader):
    map_wormhole(net)
    reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)
    assert direct_vm.run_validator() is True


def test_validator_disagrees_when_its_rpcs_see_another_mapping(direct_vm, net, reader):
    map_ccip(net)
    reader.authenticate("ccip_base", GHO, BASE_GHO)
    net.call("ethereum", GHO_POOL, C["S_CCIP_TYPE"], "0x" + "0" * 128)
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_forged_vault(direct_vm, net, reader):
    map_wormhole(net)
    reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)
    stored = direct_vm._captured_validators[-1][0]
    forged = dict(stored, vault="0x" + "1" * 40)
    assert direct_vm.run_validator(leader_result=forged) is False


def test_validator_rejects_a_leader_claiming_a_refusal(direct_vm, net, reader):
    map_wormhole(net)
    reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)
    stored = direct_vm._captured_validators[-1][0]
    fake = {"refused": "NOT_AUTHENTICATED: WRAPPED_ASSET_OF_SOURCE_IS_", "blocks": [stored["source_block"], stored["dest_block"]]}
    assert direct_vm.run_validator(leader_result=fake) is False


def test_validator_rejects_a_leader_error(direct_vm, net, reader):
    map_wormhole(net)
    reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)
    assert direct_vm.run_validator(leader_error=Exception("boom")) is False


def test_unmapped_token_is_refused(direct_vm, net, reader):
    map_wormhole(net)
    wid, tb = C["WH_DESTS"]["arbitrum"]
    net.call("arbitrum", tb, C["S_WH_WRAPPED"] + "%064x" % 2 + USDC[2:].rjust(64, "0"), A("0x" + "2" * 40))
    with direct_vm.expect_revert("NOT_AUTHENTICATED: WRAPPED_ASSET_OF_SOURCE_IS_"):
        reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)


def test_an_rpc_down_refuses(direct_vm, net, reader):
    map_wormhole(net)
    net.down.add(C["CHAINS"]["arbitrum"][1][1])
    with direct_vm.expect_revert("RPC"):
        reader.authenticate("wh_arbitrum", USDC, WH_ARB_USDC)


def test_two_rpcs_disagreeing_refuses(direct_vm, net, reader):
    map_ccip(net)
    url = C["CHAINS"]["base"][1][1]
    net.lie[url] = lambda req, ans: dict(ans, result=W(17)) if req["method"] == "eth_call" and "result" in ans and req["params"][0]["data"] == C["S_DECIMALS"] else ans
    with direct_vm.expect_revert("RPC_DISAGREE"):
        reader.authenticate("ccip_base", GHO, BASE_GHO)


def test_burn_mint_source_pool_refused(direct_vm, net, reader):
    map_ccip(net)
    from conftest import abi_string
    net.call("ethereum", GHO_POOL, C["S_CCIP_TYPE"], abi_string("BurnMintTokenPool 1.5.1"))
    with direct_vm.expect_revert("SOURCE_POOL_IS_NOT_LOCK_RELEASE"):
        reader.authenticate("ccip_base", GHO, BASE_GHO)


def test_unsupported_kind_refused(direct_vm, net, reader):
    with direct_vm.expect_revert("UNSUPPORTED_BRIDGE_KIND"):
        reader.authenticate("wh_solana", USDC, WH_ARB_USDC)


def test_config_lists_the_v2_templates(direct_vm, net, reader):
    cfg = reader.get_config()
    assert cfg["version"] == "2.0.0"
    assert "wh_arbitrum" in cfg["kinds"] and "ccip_base" in cfg["kinds"]
    assert cfg["transient"] == ["RPC_UNREADABLE", "RPC_DISAGREE"]
