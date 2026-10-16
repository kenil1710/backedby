"""Static properties of the deployed files (build/), checked on the source
text and AST: things a runtime test can miss.

    cd test && python3 -m unittest -q test_static
"""
import ast
import json
import re
import subprocess
import unittest
from pathlib import Path

import stub

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["ChainReader", "BackedByRegistry", "CollateralGate"]
DEPENDS = '# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }'


def src(n):
    return (ROOT / "build" / (n + ".py")).read_text()


def tree(n):
    return ast.parse(src(n))


def methods(n):
    for node in ast.walk(tree(n)):
        if isinstance(node, ast.ClassDef) and node.name == n:
            for f in node.body:
                if isinstance(f, ast.FunctionDef):
                    yield f


def decorated(f, text):
    return any(text in ast.unparse(d) for d in f.decorator_list)


class Header(unittest.TestCase):
    def test_first_lines(self):
        for n in NAMES:
            lines = src(n).split("\n")
            self.assertEqual(lines[0], "# v0.3.0", n)
            self.assertEqual(lines[1], DEPENDS, n)

    def test_build_is_current(self):
        r = subprocess.run(["python3", str(ROOT / "tools" / "build.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_contract_class_extends_contract(self):
        for n in NAMES:
            self.assertIn("class " + n + "(gl.contract.Contract):", src(n))

    def test_no_undefined_names(self):
        for n in NAMES:
            self.assertEqual(stub.undefined_names(ROOT / "build" / (n + ".py")), [], n)


class Safety(unittest.TestCase):
    def test_payable_methods_never_raise(self):
        found = 0
        for n in NAMES:
            for f in methods(n):
                if decorated(f, "payable"):
                    found += 1
                    for node in ast.walk(f):
                        self.assertNotIsInstance(node, ast.Raise, n + "." + f.name)
        self.assertEqual(found, 4)

    def test_payable_set_is_known(self):
        pay = sorted(f.name for f in methods("BackedByRegistry") if decorated(f, "payable"))
        self.assertEqual(pay, ["bond", "challenge", "contest", "top_up"])

    def test_no_self_in_nondet_closures(self):
        for n in NAMES:
            for f in methods(n):
                for node in ast.walk(f):
                    if isinstance(node, ast.FunctionDef) and node is not f:
                        names = {x.id for x in ast.walk(node) if isinstance(x, ast.Name)}
                        self.assertNotIn("self", names, n + "." + f.name + "." + node.name)

    def test_no_str_replace(self):
        for n in NAMES:
            self.assertIsNone(re.search(r"\.replace\(", src(n)), n)

    def test_no_raise_after_writes_marker(self):
        """In every write method, nothing after '# --- writes' can refuse."""
        for n in NAMES:
            text = src(n)
            for f in methods(n):
                if not decorated(f, "write"):
                    continue
                body = ast.get_source_segment(text, f)
                if "# --- writes" not in body:
                    continue
                tail = body[body.index("# --- writes"):]
                self.assertNotIn("raise ", tail, n + "." + f.name)
                self.assertNotIn("_ext(", tail, n + "." + f.name + " reads another contract after writing")

    def test_every_write_method_has_a_writes_marker(self):
        skip = {"authenticate", "read_check", "borrow"}   # their writes follow the last check without a marker
        for f in methods("BackedByRegistry"):
            if decorated(f, "write") and f.name not in skip:
                self.assertIn("# --- writes", ast.get_source_segment(src("BackedByRegistry"), f), f.name)

    def test_no_model_calls(self):
        for n in NAMES:
            t = src(n)
            for bad in ("exec_prompt", "web.render", "web.get(", "eq_principle", "prompt_comparative"):
                self.assertNotIn(bad, t, n)

    def test_only_the_reader_touches_the_web(self):
        self.assertIn("gl.nondet.web.request", src("ChainReader"))
        self.assertNotIn("gl.nondet", src("BackedByRegistry"))
        self.assertNotIn("gl.nondet", src("CollateralGate"))

    def test_urls_only_in_chains_table(self):
        t = src("ChainReader")
        urls = re.findall(r'"(https?://[^"]+)"', t)
        stub_mod = __import__("fixtures").CR
        allowed = {u for c in stub_mod.CHAINS.values() for u in c[1]}
        self.assertTrue(set(urls) <= allowed, set(urls) - allowed)
        self.assertEqual(len(allowed), 12)

    def test_no_owner_or_setter(self):
        for n in NAMES:
            for f in methods(n):
                self.assertFalse(f.name.startswith("set_"), n + "." + f.name)
                self.assertNotIn(f.name, ("pause", "unpause", "transfer_ownership", "set_owner", "upgrade"))

    def test_only_claim_moves_value(self):
        t = src("BackedByRegistry")
        self.assertEqual(t.count("emit_transfer"), 1)
        for n in ("ChainReader", "CollateralGate"):
            self.assertNotIn("emit_transfer", src(n))


class Consistency(unittest.TestCase):
    """The contracts' constants agree with each other and with the tools."""

    def mjs(self):
        return (ROOT / "tools" / "lib" / "bridges.mjs").read_text()

    def test_chains_match_tools(self):
        import fixtures as F
        t = self.mjs()
        for ch, (cid, urls) in F.CR.CHAINS.items():
            m = re.search(ch + r': \{ id: (\d+), rpcs: \["([^"]+)", "([^"]+)"\]', t)
            self.assertIsNotNone(m, ch)
            self.assertEqual((int(m.group(1)), m.group(2), m.group(3)), (cid, urls[0], urls[1]), ch)

    def test_bridge_constants_match_tools(self):
        import fixtures as F
        t = self.mjs()
        pairs = {"arb_l1_router": "ARB_L1_ROUTER", "arb_l2_router": "ARB_L2_ROUTER", "op_l1_bridge": "OP_L1_BRIDGE",
                 "base_l1_bridge": "BASE_L1_BRIDGE", "l2_std_bridge": "L2_STD_BRIDGE",
                 "op_dai_l1_bridge": "OP_DAI_L1_BRIDGE", "op_dai_l2_bridge": "OP_DAI_L2_BRIDGE",
                 "pol_root_manager": "POL_ROOT_MANAGER", "pol_child_manager": "POL_CHILD_MANAGER",
                 "nomad_eth_router": "NOMAD_ETH_ROUTER", "nomad_beam_router": "NOMAD_BEAM_ROUTER"}
        for js, py in pairs.items():
            m = re.search(js + r': "(0x[0-9a-f]{40})"', t)
            self.assertEqual(m.group(1), getattr(F.CR, py), js)

    def test_kinds_agree(self):
        import fixtures as F
        self.assertEqual(F.CR.KINDS, F.RG.KINDS)
        self.assertEqual(F.CR.DEPOSIT_KINDS, F.RG.DEPOSIT_KINDS)
        self.assertEqual(F.CR.MAX_DESTS, F.RG.MAX_DESTS)

    def test_selectors(self):
        import fixtures as F
        from hashlib import sha3_256  # noqa: F401  (keccak differs; checked against the recorded table instead)
        table = {"S_BALANCE": "0x70a08231", "S_SUPPLY": "0x18160ddd", "S_DECIMALS": "0x313ce567",
                 "S_GET_GATEWAY": "0xbda009fe", "S_CALC_L2": "0xa7e28d48", "S_L1_ESCROW": "0x000cc9e6",
                 "S_REMOTE_TOKEN": "0xd6c0b2c4", "S_L1_TOKEN": "0xc01e1bd6", "S_BRIDGE": "0xe78cea92",
                 "S_L2_BRIDGE": "0xae1f6aaf", "S_L2_TOKEN": "0x56eff267", "S_ESCROW": "0xe2fdcc17",
                 "S_L1_DAI_BRIDGE": "0x092d0ce3", "S_DEPOSITS": "0x8f601f66", "S_ROOT_TO_CHILD": "0xea60c7c4",
                 "S_TOKEN_TO_TYPE": "0xe43009a6", "S_TYPE_TO_PRED": "0xe66f9603", "S_CHILD_TO_ROOT": "0x6e86b770",
                 "S_TOKEN_REGISTRY": "0x9d23c4c7", "S_GET_TOKEN_ID": "0xf1537686", "S_GET_LOCAL": "0x589b3c64",
                 "S_REMOTES": "0x83bbb806"}
        for k, v in table.items():
            self.assertEqual(getattr(F.CR, k), v, k)


if __name__ == "__main__":
    unittest.main()
