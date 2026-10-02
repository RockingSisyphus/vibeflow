from tests.fixtures.support.strict_support import *
from tests.fixtures.support.rule_inspection import _valid_node_source, _inspect_node_source, node_document
from vibeflow.tooling.project.descriptor_parser import parse_descriptor_manifest


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
    assert any(error["code"] == "NODE.EFFECT.IMPORT_FORBIDDEN" for error in payload["health"]["errors"])


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
def wrap_value(value):
    return value + 1

class WrapperOneNode:
    def run_pure(self, inputs, params):
        value = inputs["value.in"]
        result = wrap_value(value)
        return {"wrap.one": result}

class WrapperTwoNode:
    def run_pure(self, inputs, params):
        value = inputs["value.in"]
        result = wrap_value(value)
        return {"wrap.two": result}
""".strip(),
        encoding="utf-8",
    )
    module = _load_module_from_path(module_path, "_wrapper_nodes")
    registry = NodeRegistry()
    for key, implementation, output in (
        ("test.wrapper_one", module.WrapperOneNode, "wrap.one"),
        ("test.wrapper_two", module.WrapperTwoNode, "wrap.two"),
    ):
        declaration = node_document(type_key=key, class_name=implementation.__name__, contract={
            "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC(output)],
            "input_semantics": {"value.in": ["input value"]},
            "output_semantics": {output: ["wrapped value"]},
            "examples": [{"inputs": {"value.in": 1}, "params": {}}],
        })
        declaration["implementations"][0]["source"]["ref"] = str(module_path)
        register_node(registry, parse_descriptor_manifest(declaration), implementation)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("wrapper_one", "test.wrapper_one", "Wraps value.in once.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("wrap.one")]),
                    _node_call("wrapper_two", "test.wrapper_two", "Wraps value.in twice.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("wrap.two")]),
                ],
            }
        }
    )
    from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context
    source_context = collect_workflow_source_context(registry, graph)
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000), source_context=source_context)
    payload = report.to_dict()
    assert payload["info"]["node_metrics"]["wrapper_one"]["run_pure_shape"] == "wrapper"
    assert payload["info"]["node_metrics"]["wrapper_two"]["run_pure_shape"] == "wrapper"
    assert "GRAPH.SMELL.DUPLICATE_LOGIC" not in {warning["rule_id"] for warning in payload["warnings"]}
