from tests.unit.strict_support import *

def test_cli_inspect_node_reports_unmatched_type(tmp_path, capsys) -> None:
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(
        """
from topology_kernel import NodeContract, NodeInfo

class DemoNode:
    NODE_INFO = NodeInfo(type_key="demo.other", display_name="Other", category="demo", description="Other.", version="0.1.0")
    CONTRACT = NodeContract(
        provides=("demo.out",),
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"demo.out": 1}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["inspect-node", "--type", "demo.node", "--module", str(module_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["health"]["status"] == "ERROR"
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.INSPECT.LOAD_ERROR"

@pytest.mark.parametrize(
    ("source", "legacy_code"),
    [
        (
            f"""
{VALID_NODE_IMPORT}
class DemoNode:
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        return {{"demo.out": 1}}
""",
            "missing_node_info",
        ),
        (_valid_node_source(info=VALID_NODE_INFO.replace('type_key="demo.node"', 'type_key=""')), "node_info_type_key"),
        (_valid_node_source(info=VALID_NODE_INFO.replace('purity="pure"', 'purity="impure"') if 'purity=' in VALID_NODE_INFO else VALID_NODE_INFO.replace('version="0.1.0",', 'version="0.1.0",\n        purity="impure",')), "non_pure_node"),
        (
            f"""
{VALID_NODE_IMPORT}
class DemoNode:
{VALID_NODE_INFO}

    def run_pure(self, inputs, params):
        return {{"demo.out": 1}}
""",
            "missing_contract",
        ),
        (_valid_node_source(contract=VALID_NODE_CONTRACT.replace('provides=("demo.out",)', 'provides=("demo.out", "demo.out")')), "contract_duplicate_key"),
        (_valid_node_source(contract=VALID_NODE_CONTRACT.replace('output_semantics={"demo.out": ("demo output",)},', 'output_semantics={},')), "contract_semantics_missing"),
        (_valid_node_source(contract=VALID_NODE_CONTRACT.replace('output_schema={"demo.out": {"type": "number"}},', 'output_schema={},')), "contract_schema_missing"),
        (_valid_node_source(contract=VALID_NODE_CONTRACT.replace('output_schema={"demo.out": {"type": "number"}},', 'output_schema={"demo.out": {}},')), "contract_schema_shape"),
        (_valid_node_source(run_body='        return {"demo.out": params.get("delta", 1)}'), "undeclared_param"),
        (_valid_node_source(run_body='        return {"other.out": 1}'), "undeclared_output"),
        (_valid_node_source(run_body='        return {}'), "missing_output"),
        (
            _valid_node_source(
                contract=VALID_NODE_CONTRACT.replace(
                    'output_schema={"demo.out": {"type": "number"}},',
                    'params_schema={"output_key": {"type": "string"}},\n        output_schema={"demo.out": {"type": "number"}},',
                ),
                run_body='        return {params["output_key"]: 1}',
            ),
            "dynamic_output_key",
        ),
        (
            f"""
{VALID_NODE_IMPORT}
class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}
""",
            "missing_run_pure",
        ),
        (
            _valid_node_source(run_body='        return {"demo.out": 1}\n\n    def run(self, context):\n        return context'),
            "context_run_forbidden",
        ),
        (
            _valid_node_source().replace("def run_pure(self, inputs, params):", "def run_pure(self, inputs, params, extra):"),
            "run_pure_signature",
        ),
        (
            _valid_node_source().replace("def run_pure(self, inputs, params):", "async def run_pure(self, inputs, params):"),
            "async_run_pure",
        ),
        (
            _valid_node_source(run_body='        while True:\n            return {"demo.out": 1}'),
            "internal_loop",
        ),
        (
            _valid_node_source().replace(
                "from topology_kernel import NodeContract, NodeInfo",
                "from topology_kernel import NodeContract, NodeInfo, GlobalBoundary",
            ),
            "boundary_import",
        ),
        (
            _valid_node_source(run_body='        return {"demo.out": 1}\n\n    def helper(self):\n        return 1'),
            "public_callable",
        ),
        (
            _valid_node_source(run_body='        return {"demo.out": 1}').replace("class DemoNode:", "class DemoNode:\n    def __init__(self, client):\n        self.x = client"),
            "init_signature",
        ),
        (
            _valid_node_source(run_body='        return {"demo.out": 1}').replace("class DemoNode:", "class DemoNode:\n    def __init__(self):\n        self.session = None"),
            "resource_field",
        ),
        (_valid_node_source(run_body='        open("x.txt", "w")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        import os\n        return {"demo.out": 1}'), "banned_import"),
        (_valid_node_source(run_body='        os.getenv("HOME")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        subprocess.run(["echo", "x"])\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        requests.get("https://example.com")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        sqlite3.connect("x.db")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        eval("1 + 1")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        importlib.import_module("math")\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        global X\n        X = 1\n        return {"demo.out": 1}'), "global_state"),
        (_valid_node_source(run_body='        setattr(self, "x", 1)\n        return {"demo.out": 1}'), "monkey_patch"),
        (_valid_node_source(run_body='        DemoNode.x = 1\n        return {"demo.out": 1}'), "monkey_patch"),
        (_valid_node_source(run_body='        from nodes.other_node import OtherNode\n        return {"demo.out": 1}'), "node_import"),
        (
            _valid_node_source().replace(VALID_NODE_IMPORT, VALID_NODE_IMPORT + "CACHE = {}\n\n"),
            "module_global_state",
        ),
        (
            _valid_node_source().replace(VALID_NODE_IMPORT, VALID_NODE_IMPORT + "if True:\n    X = 1\n\n"),
            "module_side_effect",
        ),
        (_valid_node_source(run_body='        Path("x").read_text()\n        return {"demo.out": 1}'), "banned_call"),
        (_valid_node_source(run_body='        compile("1", "<x>", "eval")\n        return {"demo.out": 1}'), "banned_call"),
    ],
)
def test_inspect_node_rejects_invalid_node_shapes(tmp_path, capsys, source, legacy_code) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    errors = payload["health"]["errors"]
    assert any(error["details"].get("legacy_code") == legacy_code for error in errors), errors

def test_inspect_node_rejects_node_direct_call_and_internal_read(tmp_path, capsys) -> None:
    other_info = VALID_NODE_INFO.replace('type_key="demo.node"', 'type_key="demo.other"').replace('display_name="Demo"', 'display_name="Other"')
    source = f"""
{VALID_NODE_IMPORT}
class OtherNode:
{other_info}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        return {{"demo.out": 1}}

class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        OtherNode.CONTRACT
        return OtherNode().run_pure({{}}, {{}})
"""
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    legacy_codes = {error["details"].get("legacy_code") for error in payload["health"]["errors"]}
    assert "node_direct_call" in legacy_codes
    assert "node_internal_read" in legacy_codes

def test_validate_node_class_warns_when_source_nears_policy_limit() -> None:
    violations = validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1000, warn_source_lines=1))
    assert any(item.code == "source_near_limit" and item.severity == "warning" for item in violations)

def test_cli_inspect_node_uses_explicit_policy_path(tmp_path, capsys) -> None:
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text('{"node_source": {"max_lines": 1}}', encoding="utf-8")
    code, payload = _inspect_node_source(
        tmp_path,
        capsys,
        _valid_node_source(),
        extra_args=["--policy", str(policy_path)],
    )
    assert code == 1
    assert any(error["details"].get("legacy_code") == "source_too_large" for error in payload["health"]["errors"])

def test_node_internal_call_chain_short_path_is_allowed(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metrics"]["call_chain_length"] == 3
    assert payload["node"]["metrics"]["call_chain_path"] == ["run_pure", "_a", "_b"]

def test_node_internal_call_chain_length_four_warns(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    warning = payload["health"]["warnings"][0]
    assert warning["rule_id"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    assert warning["details"]["length"] == 4
    assert warning["details"]["path"] == ["run_pure", "_a", "_b", "_c"]

def test_node_internal_call_chain_over_four_fails(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return self._d()

    def _d(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    error = payload["health"]["errors"][0]
    assert error["rule_id"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    assert error["details"]["length"] == 5
    assert error["suggested_fix_type"] == "split_node"

def test_node_internal_call_chain_recursion_fails(tmp_path, capsys) -> None:
    direct = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._a()
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, direct)
    assert code == 1
    assert any(error["rule_id"] == "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN" for error in payload["health"]["errors"])

    indirect = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._a()
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, indirect)
    assert code == 1
    recursive = next(error for error in payload["health"]["errors"] if error["rule_id"] == "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN")
    assert recursive["details"]["path"] == ["_a", "_b", "_a"]

def test_graph_health_reports_node_call_chain_metrics() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]}})
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.info["node_metrics"]["seed"]["call_chain_length"] == 1
    assert report.info["node_metrics"]["seed"]["call_chain_path"] == ["run_pure"]

def test_runtime_rejects_non_json_snapshot_output() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.set_output", SetOutputNode)
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "set_output", "type": "test.set_output", "provides": ["value.out"]}]}})
    with pytest.raises(PipelineRuntimeError, match="not JSON snapshot serializable"):
        PipelineRuntime(graph, registry=registry).run()

def test_runtime_allows_explicit_opaque_snapshot_output() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.opaque_output", OpaqueOutputNode)
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "opaque", "type": "test.opaque_output", "provides": ["value.out"]}]}})
    context = PipelineRuntime(graph, registry=registry).run()
    assert context.get("value.out") == {1, 2}

def test_runtime_rejects_input_mutation() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.mutating_input", MutatingInputNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "mutate",
                        "type": "test.mutating_input",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                    }
                ],
            }
        }
    )
    with pytest.raises(PipelineRuntimeError, match="mutated inputs"):
        PipelineRuntime(graph, registry=registry).run({"value": {"in": [1, 2]}})

def test_collect_node_metrics_reports_complexity_and_contract_size() -> None:
    metrics = collect_node_metrics(AddNode)
    payload = metrics.to_dict()
    assert payload["function_count"] == 1
    assert payload["branch_count"] == 0
    assert payload["param_count"] == 1
    assert payload["requires_count"] == 1
    assert payload["provides_count"] == 1
    assert payload["contract_key_count"] == 2
    assert payload["source_lines"] > 0

def test_complexity_policy_thresholds_are_enforced() -> None:
    violations = validate_node_class(
        AddNode,
        policy=PurityPolicy(
            max_source_lines=1000,
            max_functions=0,
            max_params=0,
            max_contract_keys=1,
        ),
    )
    codes = {item.code for item in violations}
    assert "complexity_max_functions" in codes
    assert "complexity_max_params" in codes
    assert "complexity_max_contract_keys" in codes
    assert all(item.suggested_fix_type in {"split_node", "fix_contract"} for item in violations if item.code.startswith("complexity_"))

def test_branch_and_nesting_complexity_are_enforced(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        if params.get("flag", False):
            if params.get("other", False):
                return {"demo.out": 2}
        return {"demo.out": 1}
""".rstrip(),
        contract=VALID_NODE_CONTRACT.replace(
            'examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),',
            'params_schema={"flag": {"type": "boolean"}, "other": {"type": "boolean"}},\n        examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),',
        ),
    )
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text('{"complexity": {"max_branches": 1, "max_nesting_depth": 1}}', encoding="utf-8")
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 1
    codes = {error["details"].get("legacy_code") for error in payload["health"]["errors"]}
    assert "complexity_max_branches" in codes
    assert "complexity_max_nesting_depth" in codes
    assert payload["node"]["metrics"]["branch_count"] == 2
    assert payload["node"]["metrics"]["max_nesting_depth"] == 2

def test_inspect_node_reports_metrics_for_valid_node(tmp_path, capsys) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source())
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metrics"]["function_count"] == 1
    assert payload["node"]["metrics"]["provides_count"] == 1
    assert payload["node"]["contract"]["examples"][0]["outputs"] == {"demo.out": 1}

def test_missing_examples_and_example_contract_gap_are_concerns(tmp_path, capsys) -> None:
    no_examples_contract = VALID_NODE_CONTRACT.replace(
        '        examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),\n',
        "",
    )
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(contract=no_examples_contract))
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    assert any(warning["details"].get("legacy_code") == "missing_examples" for warning in payload["health"]["warnings"])

    gap_contract = VALID_NODE_CONTRACT.replace(
        'examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),',
        'examples=({"inputs": {}, "params": {}, "outputs": {}},),',
    )
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(contract=gap_contract))
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    assert any(warning["details"].get("legacy_code") == "example_contract_gap" for warning in payload["health"]["warnings"])

def test_example_failure_is_health_error(tmp_path, capsys) -> None:
    bad_example_contract = VALID_NODE_CONTRACT.replace(
        'examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),',
        'examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 2}},),',
    )
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(contract=bad_example_contract))
    assert code == 1
    assert payload["health"]["status"] == "FAIL"
    assert any(error["details"].get("legacy_code") == "example_failed" for error in payload["health"]["errors"])
