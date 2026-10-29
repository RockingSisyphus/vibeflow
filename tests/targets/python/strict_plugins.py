from tests.fixtures.support.strict_support_runtime_implementations import SinkNode
from tests.fixtures.support.declarations import node_declaration, configured_declaration
import re

from tests.fixtures.support.strict_support import *
from tests.fixtures.support.plugins import publish_native_fixture, write_lifecycle_fixture


from vibeflow.targets.python.quality.workflow.validation import validate_graph_health as _validate_graph_health
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def validate_graph_health(graph, *, registry=None, **kwargs):
    if registry is not None:
        kwargs.setdefault("source_context", collect_workflow_source_context(registry,graph))
    return _validate_graph_health(graph,registry=registry,**kwargs)


SinkNode_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='test.sink', display_name='Sink', description='Consumes a value.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(requires=(DataRequirement('value.in', 'exactly_one', display_name='value.in'),), input_semantics={'value.in': ('input value',)}, examples=({'inputs': {'value.in': 1}, 'params': {}},)), rulesets=("vibeflow.process",))


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
        record({{"hook": "before_node", "id": name}})
    def after_run(self, state, trace):
        record({{"hook": "after_run", "event_count": trace.get("event_count"), "trace_path": trace.get("trace_path")}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [
                    write_lifecycle_fixture(tmp_path, source={"kind":"file", "ref":plugin_path.name, "export":"CompilerPlugin"}, plugin_id="compiler_hook", plugin_type="compiler", filename="compiler_definition.py"),
                    write_lifecycle_fixture(tmp_path, source={"kind":"file", "ref":plugin_path.name, "export":"RuntimePlugin"}, plugin_id="runtime_hook", filename="runtime_definition.py"),
                ],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )
    publish_native_fixture(config_path, _registry())
    run_checked(config_path, run_root=tmp_path / "runs", run_id="plugin_hooks")
    records = [json.loads(line) for line in marker_path.read_text(encoding="utf-8").splitlines()]
    hooks = [record["hook"] for record in records]
    assert "after_compile" in hooks
    assert "before_node" in hooks
    assert "after_run" in hooks
    after_run = next(record for record in records if record["hook"] == "after_run")
    assert after_run["event_count"] >= 1
    assert after_run["trace_path"].endswith("runtime_trace.jsonl")
    assert "events" not in after_run

def test_plugin_registry_priority_scope_and_conflict_strategy() -> None:
    class A:
        name = "same"
        priority = 20

    class B:
        name = "same"
        priority = 10

    registry = PluginRegistry()
    registry.register(A(), plugin_type="compiler", scope="project")
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(B(), plugin_type="compiler")
    registry.register(B(), plugin_type="compiler", conflict="replace", scope="nodeset")
    descriptors = registry.to_dict()["plugins"]
    assert descriptors == [
        {
            "name": "same",
            "type": "compiler",
            "priority": 10,
            "scope": "nodeset",
            "source": "manual",
            "rulesets": [],
        }
    ]

def test_nodeset_can_be_used_as_a_node() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                {
                    "type_key": "math.add_one",
                    "display_name": "Add One",
                    "description": "Composite add-one flow.",
                    "requires": [REQ_SPEC("value.in")],
                    "provides": [PROV_SPEC("value.out")],
                    "pipeline": {
                        "inputs": [INPUT_SPEC("value.in")],
                        "nodes": [
                            {'id': 'start', 'definition_id': 'test.start', 'display_name': 'Start', 'description': 'Exercises start in the plugin test workflow.'},
                            {'id': 'add', 'definition_id': 'test.add', 'delta': 1, 'display_name': 'Add', 'description': 'Exercises add in the plugin test workflow.'},
                            {'id': 'end', 'definition_id': 'test.out_end', 'display_name': 'End', 'description': 'Exercises end in the plugin test workflow.'},
                        ],
                        "edges": _edge_chain("start", "add", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                }
            ],
                "pipeline": {
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        {'id': 'start', 'definition_id': 'test.start', 'display_name': 'Start', 'description': 'Exercises start in the plugin test workflow.'},
                        {'id': 'composite', 'definition_id': 'math.add_one', 'display_name': 'Composite', 'description': 'Exercises composite in the plugin test workflow.'},
                        {'id': 'end', 'definition_id': 'test.out_end', 'display_name': 'End', 'description': 'Exercises end in the plugin test workflow.'},
                    ],
                    "edges": _edge_chain("start", "composite", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": 2})
    assert context.get("value.out")["value"] == 3

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
    mermaid = export_mermaid(graph, registry=_registry())
    assert "flowchart TD" in mermaid
    assert "data: Value In" in mermaid
    assert "provides:" not in mermaid
    assert "requires:" not in mermaid

def test_mermaid_collapses_and_expands_nodesets_with_contract_metadata() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"id": "inner", "description": "Internal add step."}),
                )
            ],
                "pipeline": {
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the nodeset Mermaid fixture."),
                        _node_call("input", "test.value_input", "Reads value.in."),
                        _node_call("composite", "math.add_one", "Calls the add-one nodeset."),
                        _node_call("end", "test.out_end", "Consumes value.out at the end."),
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
        }
    )

    collapsed = export_mermaid(graph, registry=_registry())
    assert 'composite@{ shape: fr-rect, label: "Composite\\n\\nid: composite\\ndefinition_id: math.add_one' in collapsed
    assert "---------- nodeset ----------" in collapsed
    assert "type_key: math.add_one" in collapsed
    assert "requires:" not in collapsed
    assert "exports:" not in collapsed
    assert "data: Value Out" in collapsed
    assert "composite__inner" not in collapsed

    expanded = export_mermaid(graph, registry=_registry(), expand_nodesets=True)
    assert 'subgraph composite__expanded["Composite (id: composite, type_key: math.add_one)"]' in expanded
    assert 'composite__inner@{ shape: rect, label: "Inner\\n\\nid: inner\\ndefinition_id: test.add' in expanded
    assert "Internal add step." in expanded

def test_mermaid_review_columns_layout_separates_main_resources_and_expanded_nodesets() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"id": "inner", "description": "Internal add step."}),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the review-column fixture."),
                    _node_call("input", "test.value_input", "Reads value.in."),
                    _node_call("composite", "math.add_one", "Calls the add-one nodeset."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        }
    )
    resources = {
        "plugins": [
            {
                "id": "review_policy",
                "type": "compiler",
                "module": "project.plugins.review_policy",
                "status": "implemented",
                "info": {"display_name": "Review Policy", "description": "Checks graph policy."},
            },
            {
                "id": "future_policy",
                "type": "compiler",
                "module": "project.plugins.future_policy",
                "status": "planned",
                "info": {"display_name": "Future Policy", "description": "Not active in this review."},
            }
        ],
        "base_lib": {
            "modules": [
                {
                    "id": "contracts",
                    "module": "project.base_lib.contracts",
                    "status": "implemented",
                    "info": {"display_name": "Contracts", "description": "Shared contract helpers."},
                }
            ]
        },
    }

    mermaid = export_mermaid(graph, registry=_registry(), expand_nodesets=True, resources=resources, mermaid_layout="review-columns")

    assert mermaid.startswith("flowchart LR")
    assert 'subgraph __vibeflow_layout_main["main pipeline"]' in mermaid
    assert "    direction TB" in mermaid
    assert "start --> input" in mermaid
    assert 'subgraph __vibeflow_layout_plugins["plugins"]' in mermaid
    assert 'subgraph __vibeflow_layout_base_lib["base_lib"]' in mermaid
    assert "Review Policy" in mermaid
    assert "desc: Checks graph policy." in mermaid
    assert "Future Policy" in mermaid
    assert "class resource_plugins_1 plannedResource;" in mermaid
    assert "Contracts" in mermaid
    assert "desc: Shared contract helpers." in mermaid
    assert "---------- resource ----------" in mermaid
    assert "---------- meta ----------" in mermaid
    assert 'subgraph __vibeflow_layout_nodesets["expanded nodeset_types"]' in mermaid
    assert "type_key: math.add_one" in mermaid
    assert "__vibeflow_layout_nodesets__composite__inner" in mermaid
    assert mermaid.index("__vibeflow_layout_main") < mermaid.index("__vibeflow_layout_plugins")
    assert mermaid.index("__vibeflow_layout_plugins") < mermaid.index("__vibeflow_layout_base_lib")
    assert mermaid.index("__vibeflow_layout_base_lib") < mermaid.index("__vibeflow_layout_nodesets")


def test_run_checked_centralizes_preview_artifacts(tmp_path, monkeypatch) -> None:
    from vibeflow.tooling.application.python.presentation import preview
    from vibeflow.tooling.presentation.preview.catalog import new_record
    from tests.fixtures.support.preview import preview_directory
    calls = []
    def publish(prepared, **kwargs):
        calls.append(kwargs)
        record = new_record(tmp_path, {"id":"project:workflow.json"}, "run", "running")
        (record.directory / "snapshot.js").write_text("VibeFlowPreview.snapshot({version:2});")
        record.update("running")
        return record
    monkeypatch.setattr(preview, "python_preview", publish)
    # The source-run lifecycle imports the owning adapter once.
    import vibeflow.tooling.application.python.preview_run as lifecycle
    monkeypatch.setattr(lifecycle, "python_preview", publish)
    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"pipeline": _seed_add_pipeline()}), encoding="utf-8")
    publish_native_fixture(config_path, _registry())
    result = run_checked(config_path, run_root=tmp_path / "runs", run_id="svg_artifacts")
    assert len(calls) == 1
    assert not (result.run_dir / "graph.svg").exists()
    directory = preview_directory(result.run_dir)
    assert "version:2" in (directory / "snapshot.js").read_text()
    assert json.loads((directory / "record.json").read_text())["status"] == "succeeded"


def test_run_checked_records_preview_error_without_failing_run(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.application.python.preview_run as lifecycle
    def fail_preview(*args, **kwargs):
        raise RuntimeError("preview rendering failed")
    monkeypatch.setattr(lifecycle, "python_preview", fail_preview)
    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"pipeline": _seed_add_pipeline()}), encoding="utf-8")
    publish_native_fixture(config_path, _registry())
    result = run_checked(config_path, run_root=tmp_path / "runs", run_id="svg_error")
    assert result.health.status in {"PASS", "CONCERNS"}
    assert not (result.run_dir / "graph.svg").exists()
    assert "preview rendering failed" in (result.run_dir / "preview.error.txt").read_text()


def test_mermaid_shows_when_edges_and_health_findings() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {'id': 'seed', 'definition_id': 'test.seed', 'display_name': 'Seed', 'description': 'Exercises seed in the plugin test workflow.'},
                    {'id': 'consumer', 'definition_id': 'test.add', 'display_name': 'Consumer', 'description': 'Exercises consumer in the plugin test workflow.'},
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

    mermaid = export_mermaid(graph, registry=_registry(), health_report=report)
    assert "---------- when ----------" in mermaid
    assert "when: flow.route == 'go'" in mermaid
    assert "data: Value In" in mermaid
    assert "%% finding warning POLICY.TEST node:consumer policy warning" in mermaid
    assert "class consumer healthWarning;" in mermaid

def test_health_report_status_pass_when_no_findings() -> None:
    registry = _registry()
    register_node(registry, SinkNode_DECLARATION, SinkNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the sink fixture."),
                    _node_call("input", "test.seed", "Produces value.in."),
                    _node_call("sink", "test.sink", "Consumes value.in."),
                    _node_call("end", "test.start", "Ends the sink fixture."),
                ],
                "edges": _edge_chain("start", "input", "sink", "end"),
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    assert all(warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC" for warning in report.warnings)

def test_health_report_status_fail_for_unknown_node() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{'id': 'missing', 'definition_id': 'test.missing', 'display_name': 'Missing', 'description': 'Exercises missing in the plugin test workflow.'}]}})
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert report.errors[0].rule_id == "NODE.DEFINITION.UNKNOWN"
    assert report.errors[0].object_type == "pipeline"

def _declared_cli_document():
    pipeline = _seed_add_pipeline()
    return {"pipeline":pipeline}


def test_cli_validate_json_reports_pass(tmp_path, capsys) -> None:
    from tests.fixtures.support.rule_inspection import write_registry_project
    selection = write_registry_project(tmp_path,_registry(),("test.start","test.seed","test.add","test.out_end"))
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({**_declared_cli_document(), "plugins":[selection]}),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "CONCERNS"
    assert {item["code"] for item in payload["warnings"]} == {"GRAPH.SMELL.DUPLICATE_LOGIC"}
    assert len(payload["info"]["node_metrics"]) == 4
    assert payload["info"]["effective_edges"] == [["start", "seed"], ["seed", "add"], ["add", "end"]]

def test_cli_validate_json_reports_bad_json_location(tmp_path, capsys) -> None:
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
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
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
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
    from tests.fixtures.support.rule_inspection import write_registry_project
    selection = write_registry_project(tmp_path,_registry(),("test.start","test.seed","test.add","test.out_end"))
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({**_declared_cli_document(), "plugins":[selection]}),
        encoding="utf-8",
    )
    code = cli_main(["inspect-config", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    assert {item["code"] for item in payload["health"]["warnings"]} == {"GRAPH.SMELL.DUPLICATE_LOGIC"}
    assert payload["config"]["nodes"][0]["id"] == "start"
    assert payload["config"]["effective_edges"] == [
        {"from": "start", "to": "seed", "when": ""},
        {"from": "seed", "to": "add", "when": ""},
        {"from": "add", "to": "end", "when": ""},
    ]

def test_cli_inspect_node_with_module_reports_metadata_and_contract(tmp_path, capsys) -> None:
    from tests.fixtures.support.rule_inspection import node_document, _inspect_node_source
    descriptor = node_document(contract={"requires":[REQ_SPEC("demo.in")],"provides":[PROV_SPEC("demo.out")],
        "input_semantics":{"demo.in":["demo input"]},"output_semantics":{"demo.out":["demo output"]},
        "examples":[{"inputs":{"demo.in":5},"params":{}}]})
    code,payload = _inspect_node_source(tmp_path,capsys,
        'class DemoNode:\n    def run_pure(self,inputs,params):\n        return {"demo.out":inputs["demo.in"]}',descriptor=descriptor)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["id"] == "demo.node"
    assert payload["node"]["contract"]["requires"] == [
        {"type": "demo.in", "cardinality": "exactly_one", "display_name": "Demo In"}
    ]
    assert payload["node"]["metrics"]["source_lines"] > 0

def test_cli_inspect_node_requires_explicit_workflow(capsys) -> None:
    with pytest.raises(SystemExit) as error:
        cli_main(["inspect-node", "--node-id", "demo.node"])
    assert error.value.code == 2
    assert "--config" in capsys.readouterr().err
