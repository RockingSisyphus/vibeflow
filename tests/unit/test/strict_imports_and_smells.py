from tests.unit.strict_support import *


def test_urllib_parse_is_allowed_but_urllib_request_is_banned_for_nodes(tmp_path, capsys) -> None:
    parse_source = _valid_node_source(
        run_body="""
        from urllib.parse import urlparse
        return {"demo.out": len(urlparse("https://example.test/a").path) - 1}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path / "parse", capsys, parse_source)
    assert code == 0
    assert payload["health"]["status"] == "PASS"

    request_source = _valid_node_source(
        run_body="""
        from urllib.request import urlopen
        return {"demo.out": 1}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path / "request", capsys, request_source)
    assert code == 1
    assert any(error["details"].get("legacy_code") == "banned_import" for error in payload["health"]["errors"])


def test_urllib_parse_is_allowed_but_urllib_request_is_banned_for_base_lib(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "parse_tools.py").write_text(
        """
from urllib.parse import urlparse

def path_length(url):
    return len(urlparse(url).path)
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    assert report.findings == ()

    (base_dir / "request_tools.py").write_text(
        """
from urllib.request import urlopen

def load(url):
    return urlopen(url)
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    assert any(finding.rule_id == "BASE_LIB.BANNED_IMPORT" for finding in report.findings)


def test_graph_health_suppresses_duplicate_logic_for_standard_wrappers(tmp_path) -> None:
    module_path = tmp_path / "wrapper_nodes.py"
    module_path.write_text(
        """
from vibeflow import NodeContract, NodeInfo

def wrap_value(value):
    return value + 1

class WrapperOneNode:
    NODE_INFO = NodeInfo("test.wrapper_one", "Wrapper One", "test", "Wrapper node.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("wrap.one",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"wrap.one": ("wrapped value",)},
        output_schema={"wrap.one": {"type": "number"}},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {"wrap.one": 2}},),
    )

    def run_pure(self, inputs, params):
        value = inputs["value.in"]
        result = wrap_value(value)
        return {"wrap.one": result}

class WrapperTwoNode:
    NODE_INFO = NodeInfo("test.wrapper_two", "Wrapper Two", "test", "Wrapper node.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("wrap.two",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"wrap.two": ("wrapped value",)},
        output_schema={"wrap.two": {"type": "number"}},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {"wrap.two": 2}},),
    )

    def run_pure(self, inputs, params):
        value = inputs["value.in"]
        result = wrap_value(value)
        return {"wrap.two": result}
""".strip(),
        encoding="utf-8",
    )
    module = _load_module_from_path(module_path, "_wrapper_nodes")
    registry = NodeRegistry()
    register_node(registry, "test.wrapper_one", module.WrapperOneNode)
    register_node(registry, "test.wrapper_two", module.WrapperTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "wrapper_one", "type": "test.wrapper_one", "requires": ["value.in"], "provides": ["wrap.one"]},
                    {"name": "wrapper_two", "type": "test.wrapper_two", "requires": ["value.in"], "provides": ["wrap.two"]},
                ],
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    assert payload["info"]["node_metrics"]["wrapper_one"]["run_pure_shape"] == "wrapper"
    assert payload["info"]["node_metrics"]["wrapper_two"]["run_pure_shape"] == "wrapper"
    assert "GRAPH.SMELL.DUPLICATE_LOGIC" not in {warning["rule_id"] for warning in payload["warnings"]}
