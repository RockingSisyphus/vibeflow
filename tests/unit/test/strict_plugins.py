from tests.unit.strict_support import *


class SinkNode:
    NODE_INFO = NodeInfo(
        type_key="test.sink",
        display_name="Sink",
        category="test",
        description="Consumes a value.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


def test_compiler_and_runtime_plugins_are_hooked(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "hook_plugins.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path

MARKER = Path({str(marker_path)!r})

def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")

class CompilerPlugin:
    name = "compiler_hook"
    def after_compile(self, graph, compiled):
        record({{"hook": "after_compile", "nodes": len(graph.nodes)}})

class RuntimePlugin:
    name = "runtime_hook"
    def before_node(self, name, node_type, input_summary):
        record({{"hook": "before_node", "name": name}})
    def after_run(self, state, trace):
        record({{"hook": "after_run", "events": len(trace.get("events", []))}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [
                    {"module": str(plugin_path), "class": "CompilerPlugin", "type": "compiler"},
                    {"module": str(plugin_path), "class": "RuntimePlugin", "type": "runtime"},
                ],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )
    run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_hooks")
    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert "after_compile" in hooks
    assert "before_node" in hooks
    assert "after_run" in hooks

def test_plugin_registry_priority_scope_and_conflict_strategy() -> None:
    class A:
        name = "same"
        priority = 20

    class B:
        name = "same"
        priority = 10

    registry = PluginRegistry()
    registry.register(A(), plugin_type="policy", scope="project")
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(B(), plugin_type="policy")
    registry.register(B(), plugin_type="policy", conflict="replace", scope="nodeset")
    descriptors = registry.to_dict()["plugins"]
    assert descriptors == [
        {"name": "same", "type": "policy", "priority": 10, "scope": "nodeset", "source": "manual"}
    ]

def test_nodeset_can_be_used_as_a_node() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                {
                    "name": "math.add_one",
                    "display_name": "Add One",
                    "category": "math",
                    "description": "Composite add-one flow.",
                    "version": "0.1.0",
                    "purity": "pure",
                    "requires": ["value.in"],
                    "provides": ["value.out"],
                    "exports": ["value.out"],
                    "pipeline": _input_add_pipeline(add={"delta": 1}),
                }
            ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        },
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 2}})
    assert context.get("value.out") == 3

def test_health_report_and_mermaid_export() -> None:
    graph = parse_graph_config(
        {
            "pipeline": _seed_add_pipeline()
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    serialized = report.to_dict()
    assert serialized["warnings"][0]["rule_id"] == "GRAPH.SMELL.DUPLICATE_LOGIC"
    mermaid = export_mermaid(graph)
    assert "flowchart TD" in mermaid
    assert "seed --> add" in mermaid
    assert "provides: value.in" in mermaid
    assert "requires: value.in" in mermaid

def test_mermaid_collapses_and_expands_nodesets_with_contract_metadata() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"name": "inner", "description": "Internal add step."}),
                )
            ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        },
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
        }
    )

    collapsed = export_mermaid(graph)
    assert 'composite@{ shape: fr-rect, label: "composite\\nnodeset.math.add_one' in collapsed
    assert "requires: value.in" in collapsed
    assert "exports: value.out" in collapsed
    assert "composite__inner" not in collapsed

    expanded = export_mermaid(graph, expand_nodesets=True)
    assert 'subgraph composite__expanded["math.add_one"]' in expanded
    assert 'composite__inner@{ shape: rect, label: "inner\\ntest.add' in expanded
    assert "Internal add step." in expanded

def test_mermaid_shows_when_edges_and_health_findings() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "consumer", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                ],
                "edges": [{"from": "seed", "to": "consumer", "when": "flow.route == 'go'"}],
            },
        }
    )
    report = HealthReport(
        status="CONCERNS",
        warnings=(
            HealthFinding(
                rule_id="POLICY.TEST",
                severity="warning",
                object_type="node",
                object_id="consumer",
                failure_layer="policy",
                message="policy warning",
            ),
        ),
    )

    mermaid = export_mermaid(graph, health_report=report)
    assert "seed -->|flow.route == 'go'| consumer" in mermaid
    assert "%% finding warning POLICY.TEST node:consumer policy warning" in mermaid
    assert "class consumer healthWarning;" in mermaid

def test_health_report_status_pass_when_no_findings() -> None:
    registry = _registry()
    register_node(registry, "test.sink", SinkNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                    {"name": "sink", "type": "test.sink", "requires": ["value.in"]},
                    {"name": "end", "type": "test.start"},
                ],
                "edges": _edge_chain("start", "input", "sink", "end"),
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    assert all(warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC" for warning in report.warnings)

def test_health_report_status_fail_for_unknown_node() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing", "provides": ["x"]}]}})
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert report.errors[0].rule_id == "NODE.TYPE.UNKNOWN"
    assert report.errors[0].object_type == "node"

def test_target_package_structure_reexports_stable_api_and_schema_resources() -> None:
    import topology_kernel.core as core
    import topology_kernel.devtools as devtools
    import topology_kernel.plugins as plugins

    assert core.NodeInfo is NodeInfo
    assert core.GraphCompiler is GraphCompiler
    assert devtools.export_mermaid is export_mermaid
    assert devtools.export_ascii_flowchart is export_ascii_flowchart
    assert devtools.render_mermaid_svg is render_mermaid_svg
    assert devtools.is_mermaid_svg_renderer_available is is_mermaid_svg_renderer_available
    assert plugins.PluginRegistry is PluginRegistry
    assert "NodeInfo" in STABLE_PUBLIC_API
    assert "render_mermaid_svg" in STABLE_PUBLIC_API
    assert "schema_text" in STABLE_PUBLIC_API

    for schema_name in ("config", "policy", "health_report", "node", "nodeset"):
        payload = json.loads(schema_text(schema_name))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["title"].startswith("Topology Kernel")

def test_cli_validate_json_reports_pass(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {"pipeline": _seed_add_pipeline()}
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["info"]["nodes"] == 4
    assert payload["info"]["effective_edges"] == [["start", "seed"], ["seed", "add"], ["add", "end"]]

def test_cli_validate_json_reports_bad_json_location(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text('{"pipeline": ', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 1
    assert payload["errors"][0]["source_location"]["column"] > 1

def test_cli_validate_text_error_includes_rule_file_line_and_column(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text('{"pipeline": ', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path)])
    output = capsys.readouterr().out
    assert code == 1
    assert "CONFIG.JSON" in output
    assert str(config_path) in output
    assert "line 1" in output
    assert "column" in output

def test_cli_inspect_config_outputs_effective_edges(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {"pipeline": _seed_add_pipeline()}
        ),
        encoding="utf-8",
    )
    code = cli_main(["inspect-config", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["config"]["nodes"][0]["name"] == "start"
    assert payload["config"]["effective_edges"] == [
        {"from": "start", "to": "seed", "when": ""},
        {"from": "seed", "to": "add", "when": ""},
        {"from": "add", "to": "end", "when": ""},
    ]

def test_cli_inspect_node_with_module_reports_metadata_and_contract(tmp_path, capsys) -> None:
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(
        """
from topology_kernel import NodeContract, NodeInfo

class DemoNode:
    NODE_INFO = NodeInfo(
        type_key="demo.node",
        display_name="Demo",
        category="demo",
        description="Demo node.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("demo.in",),
        provides=("demo.out",),
        input_semantics={"demo.in": ("demo input",)},
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {"demo.in": 5}, "params": {}, "outputs": {"demo.out": 5}},),
    )

    def run_pure(self, inputs, params):
        return {"demo.out": inputs["demo.in"]}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["inspect-node", "--type", "demo.node", "--module", str(module_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metadata"]["type_key"] == "demo.node"
    assert payload["node"]["contract"]["requires"] == ["demo.in"]
    assert payload["node"]["source"]["lines"] > 0

def test_cli_inspect_node_requires_module_boundary(capsys) -> None:
    code = cli_main(["inspect-node", "--type", "demo.node"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["health"]["status"] == "FAIL"
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.INSPECT.MODULE_REQUIRED"
