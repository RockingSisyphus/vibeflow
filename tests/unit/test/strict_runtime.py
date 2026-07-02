from tests.unit.strict_support import *

def test_checked_run_refuses_failed_health_before_runtime(tmp_path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing", "provides": ["value.out"]}]}}),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="bad_run")
    result = exc_info.value.result
    assert result.health.status == "FAIL"
    assert any(error.rule_id == "NODE.TYPE.UNKNOWN" for error in result.health.errors)
    assert (result.run_dir / "health_report.json").exists()
    assert (result.run_dir / "effective_policy.json").exists()
    assert not (result.run_dir / "boundary_trace.jsonl").exists()
    health_payload = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    assert health_payload["errors"][0]["failure_layer"] == "topology"
    assert health_payload["effective_policy"]["sources"] == ["kernel.default_policy"]
    assert (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8") == ""


def test_node_registration_requires_config_spec() -> None:
    with pytest.raises(Exception, match="config_schema"):
        NodeRegistry().register("test.seed", SeedNode)


def test_node_config_defaults_and_call_overrides_are_passed_to_runtime() -> None:
    graph = parse_graph_config(
        {
            "pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({})
    assert context.get("value.in") == 1
    assert context.get("value.out") == 5


def test_execution_plan_binds_node_instance_and_params_once() -> None:
    CountingInitNode.instances = 0
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "count", "type": "test.counting_init", "provides": ["value.out"], "config": {"value": 9}},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "count", "end"),
            }
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())

    assert runtime._plan.frame("count").params["value"] == 9
    assert CountingInitNode.instances == 1
    assert runtime.run({}).get("value.out") == 9
    assert runtime.run({}).get("value.out") == 9
    assert CountingInitNode.instances == 1


def test_execution_plan_prebuilds_nodeset_subplan_with_overrides() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={"inputs": ["value.in"], **_input_add_pipeline(add={"delta": 1})},
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
                        "node_configs": {"add": {"delta": 6}},
                    },
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())
    frame = runtime._plan.frame("composite")

    assert frame.is_nodeset
    assert frame.subplan is not None
    assert frame.subplan.frame("add").params["delta"] == 6
    assert runtime.run({"value.in": 2}).get("value.out") == 8


def test_nodeset_runner_reuses_cached_subruntime() -> None:
    CountingInitNode.instances = 0
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "count.once",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            {"name": "start", "type": "test.start"},
                            {"name": "count", "type": "test.counting_init", "provides": ["value.out"], "config": {"value": 5}},
                            {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                        ],
                        "edges": _edge_chain("start", "count", "end"),
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "composite", "type": "nodeset.count.once", "provides": ["value.out"]},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "composite", "end"),
            },
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())
    assert CountingInitNode.instances == 1

    assert runtime.run({}).get("value.out") == 5
    nested = runtime._nodeset_runtimes["composite"]
    assert runtime.run({}).get("value.out") == 5
    assert runtime._nodeset_runtimes["composite"] is nested
    assert CountingInitNode.instances == 1


def test_nodeset_inputs_and_exports_preserve_object_reference() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "identity.object",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "inputs": ["value.in"],
                        "nodes": [
                            {"name": "start", "type": "test.start"},
                            {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                            {"name": "identity", "type": "test.identity_object", "requires": ["value.in"], "provides": ["value.out"]},
                            {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                        ],
                        "edges": _edge_chain("start", "input", "identity", "end"),
                    },
                )
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                    {"name": "composite", "type": "nodeset.identity.object", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        }
    )

    value = NoDeepcopyObject()
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": value})

    assert context.get("value.in") is value
    assert context.get("value.out") is value


def test_node_config_invalid_override_fails_health_before_runtime() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": "bad"},
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert any(error.rule_id == "NODE.CONFIG.INVALID" for error in report.errors)


def test_checked_run_refuses_planned_architecture(tmp_path) -> None:
    config_path = tmp_path / "planned.json"
    config_path.write_text(
        json.dumps(
            {
                "nodesets": [{"name": "a", "status": "planned"}],
                "pipeline": {
                    "nodes": [
                        {"name": "a", "type": "nodeset.a", "status": "planned", "flow_kind": "predefined"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="planned_run")

    result = exc_info.value.result
    assert result.health.status == "FAIL"
    assert any(error.rule_id == "GRAPH.PLANNED.NODE_IN_RUN" for error in result.health.errors)
    assert "planned" in (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    assert "PLANNED" in (result.run_dir / "graph.txt").read_text(encoding="utf-8")


def test_nodeset_call_can_override_inner_node_config_independently() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "inputs": ["value.in"],
                        **_input_add_pipeline(add={"delta": 1}),
                    },
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
                        "node_configs": {"add": {"delta": 5}},
                    },
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": 2})
    assert context.get("value.out") == 7


class NoDeepcopyObject:
    def __deepcopy__(self, memo):
        raise AssertionError("should not deepcopy runtime objects")


def test_runtime_passes_non_deepcopy_object_by_reference() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
                    {"name": "identity", "type": "test.identity_object", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "input", "identity", "end"),
            }
        }
    )
    value = NoDeepcopyObject()
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": value})
    assert context.get("value.in") is value
    assert context.get("value.out") is value


def test_checked_run_writes_runtime_failure_trace(tmp_path) -> None:
    config_path = tmp_path / "runtime_fail.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "bad", "type": "test.runtime_fail", "provides": ["value.out"], "config": {"fail": True}},
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": _edge_chain("start", "bad", "end"),
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="boom"):
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="runtime_fail")
    trace_lines = [
        json.loads(line)
        for line in (tmp_path / "runs" / "runtime_fail" / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    failed = next(line for line in trace_lines if line["kind"] == "node_failed")
    assert "boom" in failed["failure"]
    assert trace_lines[-1]["kind"] == "runtime_summary"


def test_runtime_options_boundary_trace_records_only_boundaries() -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary"))

    context = runtime.run({})

    assert context.get("value.in") == 1
    assert [event["kind"] for event in runtime.trace.events] == ["run_start", "run_end"]
    assert runtime.trace.exec_order == ["start", "seed", "end"]
    assert runtime.trace.current_node == "end"


def test_runtime_options_off_keeps_summary_without_events() -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="off"))

    context = runtime.run({})

    assert context.get("runtime.events") == []
    assert context.get("runtime.current_node") == "end"
    assert context.get("runtime.stop_reason") == "completed"
    assert context.get("runtime.exception") == ""


def test_runtime_options_snapshot_outputs_restores_json_snapshot_check() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "set", "type": "test.nan_output", "provides": ["value.out"]},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": _edge_chain("start", "set", "end"),
            }
        }
    )

    with pytest.raises(PipelineRuntimeError, match="not JSON snapshot serializable"):
        PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(snapshot_outputs=True)).run({})


def test_runtime_options_node_hooks_false_skips_per_node_hooks(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "runtime_plugin.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
MARKER = Path({str(marker_path)!r})
def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")
class RuntimePlugin:
    name = "runtime_hook"
    def before_run(self, state):
        record({{"hook": "before_run"}})
    def before_node(self, name, node_type, input_summary):
        record({{"hook": "before_node"}})
    def after_node(self, name, node_type, output_summary):
        record({{"hook": "after_node"}})
    def after_run(self, state, trace):
        record({{"hook": "after_run"}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "class": "RuntimePlugin", "type": "runtime"}],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )

    run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="node_hooks_off", runtime_options=RuntimeOptions(node_hooks=False))

    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert hooks == ["before_run", "after_run"]

def test_checked_run_trace_records_nodeset_enter_exit(tmp_path) -> None:
    config_path = tmp_path / "nodeset_workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "nodesets": [
                    _nodeset_config(
                        "math.add_one",
                        requires=["value.in"],
                        provides=["value.out"],
                        exports=["value.out"],
                        pipeline={
                        "inputs": ["value.in"],
                        **_input_add_pipeline(),
                    },
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
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value": {"in": 2}},
        run_root=tmp_path / "runs",
        run_id="nodeset_run",
    )
    assert result.context.get("value.out") == 3
    trace_kinds = [
        json.loads(line)["kind"]
        for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "nodeset_enter" in trace_kinds
    assert "nodeset_exit" in trace_kinds

def test_cli_run_uses_checked_run_and_refuses_without_registered_nodes(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]}}),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "run",
            "--config",
            str(config_path),
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "cli_run",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    run_dir = Path(payload["run_dir"])
    assert (run_dir / "health_report.json").exists()
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.TYPE.UNKNOWN"

def test_cli_run_succeeds_with_global_registry_and_writes_artifacts(tmp_path, capsys) -> None:
    from vibeflow.registry import GLOBAL_NODE_REGISTRY

    original = dict(getattr(GLOBAL_NODE_REGISTRY, "_registry"))
    original_config_specs = dict(getattr(GLOBAL_NODE_REGISTRY, "_config_specs"))
    register_node(GLOBAL_NODE_REGISTRY, "test.start", StartNode, overwrite=True)
    register_node(GLOBAL_NODE_REGISTRY, "test.in_end", InEndNode, overwrite=True)
    register_node(GLOBAL_NODE_REGISTRY, "test.seed", SeedNode, {"value": {"type": "number"}}, {"value": 1}, overwrite=True)
    try:
        config_path = tmp_path / "workflow.json"
        input_path = tmp_path / "input.json"
        config_path.write_text(
            json.dumps({"pipeline": _seed_only_pipeline(seed={"value": 9})}),
            encoding="utf-8",
        )
        input_path.write_text("{}", encoding="utf-8")
        code = cli_main(
            [
                "run",
                "--config",
                str(config_path),
                "--input",
                str(input_path),
                "--run-root",
                str(tmp_path / "runs"),
                "--run-id",
                "cli_ok",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
    finally:
        getattr(GLOBAL_NODE_REGISTRY, "_registry").clear()
        getattr(GLOBAL_NODE_REGISTRY, "_registry").update(original)
        getattr(GLOBAL_NODE_REGISTRY, "_config_specs").clear()
        getattr(GLOBAL_NODE_REGISTRY, "_config_specs").update(original_config_specs)
    assert code == 0
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    for name in ("compiled_graph.json", "health_report.json", "graph.txt", "graph.mmd", "runtime_trace.jsonl", "output_summary.json"):
        assert (run_dir / name).exists()
    if is_mermaid_svg_renderer_available():
        assert (run_dir / "graph.svg").exists()
