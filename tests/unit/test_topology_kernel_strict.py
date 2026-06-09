from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from topology_kernel import (
    BoundaryRegistry,
    ConfigLoadError,
    GraphCompileError,
    GraphCompiler,
    HealthFinding,
    HealthReport,
    NodeContract,
    NodeInfo,
    NodeRegistry,
    PipelineRuntime,
    PipelineRuntimeError,
    CheckedRunError,
    PluginRegistry,
    STABLE_PUBLIC_API,
    schema_text,
    export_mermaid,
    load_config_document,
    parse_graph_config,
    resolve_effective_policy,
    run_checked,
    scan_base_lib,
    validate_graph_health,
)
from topology_kernel.cli import main as cli_main
from topology_kernel.config_schema import collect_config_schema_findings
from topology_kernel.devtools import QualityThresholds, scan_code_quality
from topology_kernel.purity import PurityPolicy, collect_node_metrics, validate_node_class


class SeedNode:
    NODE_INFO = NodeInfo(
        type_key="test.seed",
        display_name="Seed",
        category="test",
        description="Produces a seed value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.in",),
        output_semantics={"value.in": ("seed value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 4}, "outputs": {"value.in": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="test.add",
        display_name="Add",
        category="test",
        description="Adds delta to input.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.in": 4}, "params": {"delta": 3}, "outputs": {"value.out": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"] + params.get("delta", 1)}


class CopyNode:
    NODE_INFO = NodeInfo(
        type_key="test.copy",
        display_name="Copy",
        category="test",
        description="Copies a value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.in",),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.in": ("input value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.out": 7}, "params": {}, "outputs": {"value.in": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


class BadIoNode:
    NODE_INFO = NodeInfo(
        type_key="test.bad_io",
        display_name="Bad IO",
        category="test",
        description="Illegally performs IO.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        with open("forbidden.txt", "w", encoding="utf-8") as handle:
            handle.write("bad")
        return {"value.out": 1}


class NanOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.nan_output",
        display_name="NaN Output",
        category="test",
        description="Returns a runtime-invalid JSON value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": float("nan")}


class EffectRequestNode:
    NODE_INFO = NodeInfo(
        type_key="test.effect_request",
        display_name="Effect Request",
        category="test",
        description="Emits a structured effect request.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("effects.request",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"effects.request": ("structured effect request",)},
        output_schema={"effects.request": {"type": "object"}},
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": inputs["value.in"]}}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("test.seed", SeedNode)
    registry.register("test.add", AddNode)
    registry.register("test.copy", CopyNode)
    registry.register("test.nan_output", NanOutputNode)
    registry.register("test.effect_request", EffectRequestNode)
    return registry


def _nodeset_config(
    name: str,
    *,
    pipeline: dict,
    requires: list[str] | None = None,
    provides: list[str] | None = None,
    exports: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "display_name": name.replace(".", " ").title(),
        "category": "test",
        "description": f"Composite flow for {name}.",
        "version": "0.1.0",
        "purity": "pure",
        "requires": requires or [],
        "provides": provides or ["value.out"],
        "exports": exports or ["value.out"],
        "pipeline": pipeline,
    }


class DemoBoundary:
    calls: list[str] = []

    def __init__(self):
        self.run_dir = None

    def before_run(self, run_config):
        self.__class__.calls.append("before_run")
        self.run_dir = Path(run_config["run_dir"])
        return {}

    def after_run(self, outputs, run_config):
        self.__class__.calls.append("after_run")
        return {}

    def before_iteration(self, iteration, state):
        self.__class__.calls.append(f"before_iteration:{iteration}")
        return {}

    def after_iteration(self, iteration, outputs, state):
        self.__class__.calls.append(f"after_iteration:{iteration}")
        value = outputs.get("effects.request", {}).get("value", 0)
        run_dir = self.run_dir
        return {"io.result": value + iteration + 1, "artifacts": [str(run_dir / f"artifact_{iteration}.txt")]}


class FailingBoundary(DemoBoundary):
    def after_iteration(self, iteration, outputs, state):
        raise RuntimeError("boundary failed")


def test_pure_node_metadata_and_static_check() -> None:
    assert validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1000)) == []
    violations = validate_node_class(BadIoNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "banned_call" for item in violations)


def test_source_size_limit_is_enforced() -> None:
    violations = validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1))
    assert any(item.code == "source_too_large" for item in violations)


def test_requires_provides_data_edges_are_inferred_and_runtime_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                ],
                "edges": [],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("seed", "add") in [edge.pair for edge in compiled.data_edges]
    context = PipelineRuntime(graph, registry=_registry()).run()
    assert context.get("value.out") == 7


def test_undeclared_cycle_is_rejected() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 3},
                    {"from": "copy", "to": "add", "max_executions": 3},
                ],
            }
        }
    )
    with pytest.raises(GraphCompileError):
        GraphCompiler().compile(graph)


def test_declared_bounded_loop_compiles_and_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 1},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 4},
                    {"from": "copy", "to": "add", "max_executions": 3, "loop": "counter_loop"},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "nodes": ["add", "copy"],
                        "max_iterations": 3,
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("copy", "add") in [edge.pair for edge in compiled.loop_edges]
    assert compiled.loop_orders["counter_loop"] == ("add", "copy")
    assert compiled.edge_execution_limits[("add", "copy")] == 4
    assert compiled.edge_execution_limits[("copy", "add")] == 3
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}})
    assert context.get("value.in") == 4
    assert context.get("runtime.edge_executions") == {"add->copy": 4, "copy->add": 3}
    assert context.get("runtime.loop_iterations") == {"counter_loop": 3}
    assert context.get("runtime.loop_stop_reasons") == {"counter_loop": "max_iterations"}
    assert context.get("runtime.loop_orders") == {"counter_loop": ["add", "copy"]}


def test_loop_edge_inherits_loop_limit_when_edge_has_no_explicit_max() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 2,
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert compiled.edge_execution_limits[("copy", "add")] == 2
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}})
    assert context.get("runtime.edge_executions") == {"add->copy": 3, "copy->add": 2}


def test_loop_until_stops_before_iteration_and_is_traced() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in", "stop.now"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 5,
                        "until": "stop.now",
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert compiled.loop_orders["counter_loop"] == ("add", "copy")
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}, "stop": {"now": True}})
    assert context.get("runtime.loop_iterations") == {"counter_loop": 0}
    assert context.get("runtime.loop_stop_reasons") == {"counter_loop": "until"}
    assert context.get("runtime.edge_executions") == {"add->copy": 1}


def test_loop_compile_rejects_unresolved_until_and_missing_max_iterations() -> None:
    with pytest.raises(ValueError, match="requires max_iterations"):
        parse_graph_config(
            {
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                        {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                    ],
                    "loops": [{"name": "counter_loop", "edges": [["copy", "add"]]}],
                }
            }
        )

    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "max_iterations": 2,
                        "until": "missing.stop",
                    }
                ],
            }
        }
    )
    with pytest.raises(GraphCompileError, match="until key is not resolvable"):
        GraphCompiler().compile(graph)


def test_compiler_can_check_registry_node_types() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing"}]}})
    with pytest.raises(GraphCompileError, match="unknown type"):
        GraphCompiler().compile(graph, registry=_registry())


def test_boundary_lifecycle_updates_context_and_writes_trace(tmp_path) -> None:
    DemoBoundary.calls = []
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    run_dir = tmp_path / "run"
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.boundary",
                "config": {"run_dir": str(run_dir)},
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
                "edges": [{"from": "effect", "to": "effect", "loop": "effect_loop"}],
                "loops": [{"name": "effect_loop", "edges": [["effect", "effect"]], "max_iterations": 2}],
            },
        }
    )
    context = PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry).run({"value": {"in": 10}})
    assert context.get("io.result") == 12
    assert context.get("runtime.loop_stop_reasons") == {"effect_loop": "max_iterations"}
    assert DemoBoundary.calls == [
        "before_run",
        "before_iteration:0",
        "after_iteration:0",
        "before_iteration:1",
        "after_iteration:1",
        "after_run",
    ]
    trace_path = run_dir / "boundary_trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["stage"] for event in events] == [
        "before_run",
        "before_iteration",
        "after_iteration",
        "before_iteration",
        "after_iteration",
        "after_run",
    ]


def test_boundary_health_resolves_type_and_suppresses_consumed_effect_warning() -> None:
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.boundary",
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
            },
        }
    )
    unresolved = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(error.rule_id == "BOUNDARY.TYPE.UNRESOLVED" for error in unresolved.errors)
    report = validate_graph_health(
        graph,
        registry=_registry(),
        boundary_registry=boundary_registry,
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    assert not any(warning.object_id == "effects.request" for warning in report.warnings)
    assert report.info["boundary"]["type"] == "test.boundary"


def test_boundary_runtime_rejects_unknown_type_undeclared_key_and_escaped_artifact(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "boundary": {"type": "missing.boundary", "consumes": ["effects.request"], "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="unknown boundary key"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=BoundaryRegistry())

    class BadKeyBoundary(DemoBoundary):
        def before_run(self, run_config):
            return {"unsafe.key": 1}

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("bad.key", BadKeyBoundary)
    graph = parse_graph_config(
        {
            "boundary": {"type": "bad.key", "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="undeclared key"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry, run_dir=tmp_path / "run").run()

    class EscapedArtifactBoundary(DemoBoundary):
        def before_run(self, run_config):
            return {"artifacts": [str(tmp_path / "outside.txt")]}

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("bad.artifact", EscapedArtifactBoundary)
    graph = parse_graph_config(
        {
            "boundary": {"type": "bad.artifact", "provides": ["io.result"]},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    with pytest.raises(PipelineRuntimeError, match="outside controlled paths"):
        PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry, run_dir=tmp_path / "run").run()


def test_boundary_failure_stops_loop_with_boundary_failed_reason(tmp_path) -> None:
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.failing_boundary", FailingBoundary)
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.failing_boundary",
                "config": {"run_dir": str(tmp_path / "run")},
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "effect",
                        "type": "test.effect_request",
                        "requires": ["value.in"],
                        "provides": ["effects.request"],
                    }
                ],
                "edges": [{"from": "effect", "to": "effect", "loop": "effect_loop"}],
                "loops": [{"name": "effect_loop", "edges": [["effect", "effect"]], "max_iterations": 2}],
            },
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), boundary_registry=boundary_registry)
    with pytest.raises(PipelineRuntimeError, match="boundary after_iteration failed"):
        runtime.run({"value": {"in": 10}})
    assert runtime.trace.loop_stop_reasons == {"effect_loop": "boundary_failed", "runtime": "boundary_failed"}


def test_boundary_schema_and_node_registry_isolation() -> None:
    findings = collect_config_schema_findings(
        {
            "boundary": {
                "type": "test.boundary",
                "config": [],
                "consumes": ["bad.request"],
                "provides": ["bad.result"],
                "allowed_paths": "runs",
            },
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.BOUNDARY_CONFIG" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_STRING_LIST" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_CONSUMES_KEY" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_PROVIDES_KEY" in rule_ids

    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    with pytest.raises(Exception, match="boundary class cannot be registered as a node"):
        NodeRegistry().register("test.boundary", DemoBoundary)


def test_checked_run_writes_reproducible_artifacts_without_raw_inputs(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"secret": "top-secret-value"},
        run_root=tmp_path / "runs",
        run_id="run_001",
    )
    assert result.run_id == "run_001"
    assert result.context.get("value.out") == 7
    expected_files = {
        "input_summary.json",
        "effective_policy.json",
        "compiled_graph.json",
        "health_report.json",
        "graph.mmd",
        "runtime_trace.jsonl",
        "boundary_trace.jsonl",
        "output_summary.json",
    }
    assert expected_files <= {path.name for path in result.run_dir.iterdir()}
    input_summary = json.loads((result.run_dir / "input_summary.json").read_text(encoding="utf-8"))
    assert input_summary["secret"] == {"size": 16, "type": "str"}
    assert "top-secret-value" not in (result.run_dir / "input_summary.json").read_text(encoding="utf-8")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    assert compiled["data_edges"] == [["seed", "add"]]
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    for edge in compiled["effective_edges"]:
        assert f'{edge["from"]} -->|max={edge["max_executions"]}| {edge["to"]}' in graph_mmd
    assert "provides: value.out" in graph_mmd
    trace_lines = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["kind"] for event in trace_lines[:2]] == ["node", "node"]
    assert trace_lines[-1]["kind"] == "runtime_summary"
    assert "top-secret-value" not in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8")
    assert (result.run_dir / "boundary_trace.jsonl").read_text(encoding="utf-8") == ""


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
    assert (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8") == ""


def test_checked_run_writes_runtime_failure_trace(tmp_path) -> None:
    config_path = tmp_path / "runtime_fail.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [{"name": "nan", "type": "test.nan_output", "provides": ["value.out"]}]}}),
        encoding="utf-8",
    )
    with pytest.raises(PipelineRuntimeError, match="not JSON snapshot serializable"):
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="runtime_fail")
    trace_lines = [
        json.loads(line)
        for line in (tmp_path / "runs" / "runtime_fail" / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert trace_lines[0]["kind"] == "node_failed"
    assert "not JSON snapshot serializable" in trace_lines[0]["failure"]
    assert trace_lines[-1]["kind"] == "runtime_summary"


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
                            "nodes": [
                                {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
                            ],
                        },
                    )
                ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        }
                    ],
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
    from topology_kernel.registry import GLOBAL_NODE_REGISTRY

    original = dict(getattr(GLOBAL_NODE_REGISTRY, "_registry"))
    GLOBAL_NODE_REGISTRY.register("test.seed", SeedNode, overwrite=True)
    try:
        config_path = tmp_path / "workflow.json"
        input_path = tmp_path / "input.json"
        config_path.write_text(
            json.dumps({"pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 9}]}}),
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
    assert code == 0
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    for name in ("compiled_graph.json", "health_report.json", "graph.mmd", "runtime_trace.jsonl", "output_summary.json"):
        assert (run_dir / name).exists()


def test_policy_plugin_tightens_effective_policy_and_health_uses_it(tmp_path) -> None:
    plugin_path = tmp_path / "tight_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "tight_policy"
    priority = 1

    def extend_policy(self, policy):
        return {"node_source": {"max_lines": 1}}
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_tight")
    payload = exc_info.value.result.health.to_dict()
    assert payload["effective_policy"]["node_source"]["max_lines"] == 1
    assert "plugin.policy:tight_policy" in payload["effective_policy"]["sources"]
    assert any(error["details"].get("legacy_code") == "source_too_large" for error in payload["errors"])


def test_policy_plugin_relaxation_requires_audited_downgradeable_rule(tmp_path) -> None:
    plugin_path = tmp_path / "relax_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "relax_policy"

    def extend_policy(self, policy):
        return {"imports": {"allowed_roots": ["numpy"]}}
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_relax")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.POLICY.RELAXATION_REQUIRED" for error in exc_info.value.result.health.errors)


def test_policy_plugin_allows_audited_downgradeable_relaxation(tmp_path) -> None:
    plugin_path = tmp_path / "audited_relax_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "audited_relax_policy"

    def extend_policy(self, policy):
        return {
            "policy": {
                "rules": {
                    "downgrades": [
                        {
                            "rule_id": "GRAPH.OUTPUT.UNCONSUMED",
                            "to": "warning",
                            "scope": {"pipeline": "demo"},
                            "reason": "documented project preference",
                            "expires": "2026-12-31"
                        }
                    ]
                }
            },
            "relaxations": [
                {
                    "rule_id": "GRAPH.OUTPUT.UNCONSUMED",
                    "scope": {"pipeline": "demo"},
                    "reason": "documented project preference",
                    "source": "audited_relax_policy"
                }
            ]
        }
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_audited")
    assert len(result.health.effective_policy["rules"]["downgrades"]) == 1
    assert "plugin.policy:audited_relax_policy" in result.health.effective_policy["sources"]


def test_plugin_load_and_execution_fail_closed(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_plugin.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(tmp_path / "missing.py"), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "PLUGIN.LOAD"

    plugin_path = tmp_path / "raise_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "raise_policy"

    def extend_policy(self, policy):
        raise RuntimeError("boom")
""".strip(),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_exec")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.EXECUTION" for error in exc_info.value.result.health.errors)


def test_plugin_schema_extension_errors_are_fail_closed(tmp_path) -> None:
    plugin_path = tmp_path / "schema_plugin.py"
    plugin_path.write_text(
        """
class Plugin:
    name = "schema_policy"

    def extend_node_metadata_schema(self, schema):
        raise RuntimeError("schema boom")
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_schema")
    assert exc_info.value.result.health.status == "ERROR"
    assert any(error.rule_id == "PLUGIN.EXECUTION" for error in exc_info.value.result.health.errors)


def test_policy_plugin_can_add_node_and_graph_findings(tmp_path) -> None:
    plugin_path = tmp_path / "finding_plugin.py"
    plugin_path.write_text(
        """
from topology_kernel import HealthFinding

class Plugin:
    name = "finding_policy"

    def validate_node(self, spec, node_cls, metrics):
        return [HealthFinding(
            rule_id="PLUGIN.NODE.CHECK",
            severity="warning",
            object_type="node",
            object_id=spec.name,
            failure_layer="plugin",
            message="plugin node check",
            suggested_fix_type="fix_node",
        )]

    def validate_graph(self, graph, compiled):
        return [HealthFinding(
            rule_id="PLUGIN.GRAPH.CHECK",
            severity="warning",
            object_type="pipeline",
            object_id="pipeline",
            failure_layer="plugin",
            message="plugin graph check",
            suggested_fix_type="fix_config",
        )]
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "type": "policy"}],
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_findings")
    rule_ids = {warning.rule_id for warning in result.health.warnings}
    assert "PLUGIN.NODE.CHECK" in rule_ids
    assert "PLUGIN.GRAPH.CHECK" in rule_ids
    assert result.health.info["plugins"]["plugins"][0]["name"] == "finding_policy"


def test_compiler_runtime_and_boundary_plugins_are_hooked(tmp_path) -> None:
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

class BoundaryPlugin:
    name = "boundary_hook"
    def before_boundary(self, stage, state, iteration):
        record({{"hook": "before_boundary", "stage": stage}})
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
                    {"module": str(plugin_path), "class": "BoundaryPlugin", "type": "boundary"},
                ],
                "boundary": {"type": "test.boundary", "config": {"run_dir": str(tmp_path / "run")}, "provides": ["io.result"]},
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    boundary_registry = BoundaryRegistry()
    boundary_registry.register("test.boundary", DemoBoundary)
    run_checked(config_path, registry=_registry(), boundary_registry=boundary_registry, run_root=tmp_path / "runs", run_id="plugin_hooks")
    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert "after_compile" in hooks
    assert "before_node" in hooks
    assert "after_run" in hooks
    assert "before_boundary" in hooks


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
                    "pipeline": {
                        "inputs": ["value.in"],
                        "nodes": [
                            {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 1}
                        ],
                    },
                }
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "composite",
                        "type": "nodeset.math.add_one",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                    }
                ],
            },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 2}})
    assert context.get("value.out") == 3


def test_health_report_and_mermaid_export() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    assert report.warnings[0].rule_id == "GRAPH.OUTPUT.UNCONSUMED"
    serialized = report.to_dict()
    assert serialized["warnings"][0]["object_type"] == "contract_key"
    assert serialized["warnings"][0]["failure_layer"] == "topology"
    mermaid = export_mermaid(graph)
    assert "flowchart TD" in mermaid
    assert "seed -->|max=1| add" in mermaid
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
                    pipeline={
                        "inputs": ["value.in"],
                        "nodes": [
                            {
                                "name": "inner",
                                "type": "test.add",
                                "requires": ["value.in"],
                                "provides": ["value.out"],
                                "description": "Internal add step.",
                            }
                        ],
                    },
                )
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "composite",
                        "type": "nodeset.math.add_one",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                    }
                ],
            },
        }
    )

    collapsed = export_mermaid(graph)
    assert 'composite["composite\\nnodeset.math.add_one' in collapsed
    assert "requires: value.in" in collapsed
    assert "exports: value.out" in collapsed
    assert "composite__inner" not in collapsed

    expanded = export_mermaid(graph, expand_nodesets=True)
    assert 'subgraph composite__expanded["math.add_one"]' in expanded
    assert 'composite__inner["inner\\ntest.add' in expanded
    assert "Internal add step." in expanded


def test_mermaid_shows_boundary_ports_loops_and_health_findings() -> None:
    graph = parse_graph_config(
        {
            "boundary": {
                "type": "test.boundary",
                "consumes": ["effects.request"],
                "provides": ["io.result"],
            },
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "effect", "type": "test.effect_request", "requires": ["value.in"], "provides": ["effects.request"]},
                    {"name": "consumer", "type": "test.add", "requires": ["io.result"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [["copy", "consumer"]],
                "loops": [
                    {
                        "name": "feedback",
                        "edges": [["copy", "consumer"]],
                        "nodes": ["consumer", "copy"],
                        "max_iterations": 3,
                    }
                ],
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
    assert '__boundary__["boundary\\ntest.boundary\\nconsumes: effects.request\\nprovides: io.result"]' in mermaid
    assert "effect -.->|effects.request| __boundary__" in mermaid
    assert "__boundary__ -.->|io.result| consumer" in mermaid
    assert "copy -->|loop feedback max=3| consumer" in mermaid
    assert "%% loop feedback: max_iterations=3; edges=copy->consumer" in mermaid
    assert "%% finding warning POLICY.TEST node:consumer policy warning" in mermaid
    assert "class consumer healthWarning" in mermaid


def test_health_report_status_pass_when_no_findings() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "loops": [
                    {
                        "name": "value_loop",
                        "edges": [["copy", "add"]],
                        "nodes": ["add", "copy"],
                        "max_iterations": 1,
                    }
                ],
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "PASS"
    assert report.to_dict()["status"] == "PASS"


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
    assert plugins.PluginRegistry is PluginRegistry
    assert "NodeInfo" in STABLE_PUBLIC_API
    assert "schema_text" in STABLE_PUBLIC_API

    for schema_name in ("config", "policy", "health_report", "node", "nodeset", "boundary"):
        payload = json.loads(schema_text(schema_name))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["title"].startswith("Topology Kernel")


def test_cli_validate_json_reports_pass(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["info"]["nodes"] == 2
    assert payload["info"]["effective_edges"] == [["seed", "add"]]


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
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["inspect-config", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["config"]["nodes"][0]["name"] == "seed"
    assert payload["config"]["effective_edges"] == [["seed", "add"]]


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


VALID_NODE_IMPORT = "from topology_kernel import NodeContract, NodeInfo\n\n"
VALID_NODE_INFO = """
    NODE_INFO = NodeInfo(
        type_key="demo.node",
        display_name="Demo",
        category="demo",
        description="Demo node.",
        version="0.1.0",
    )
""".rstrip()
VALID_NODE_CONTRACT = """
    CONTRACT = NodeContract(
        provides=("demo.out",),
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),
    )
""".rstrip()


def _inspect_node_source(tmp_path, capsys, source: str, *, node_type: str = "demo.node", class_name: str = "DemoNode", extra_args=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(source.strip(), encoding="utf-8")
    args = ["inspect-node", "--type", node_type, "--module", str(module_path), "--class", class_name]
    if extra_args:
        args.extend(extra_args)
    code = cli_main(args)
    return code, json.loads(capsys.readouterr().out)


def _valid_node_source(*, run_body: str = '        return {"demo.out": 1}', contract: str = VALID_NODE_CONTRACT, info: str = VALID_NODE_INFO) -> str:
    return f"""
{VALID_NODE_IMPORT}
class DemoNode:
{info}
{contract}

    def run_pure(self, inputs, params):
{run_body}
"""


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


class SetOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.set_output",
        display_name="Set Output",
        category="test",
        description="Returns a non-json output.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class OpaqueOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.opaque_output",
        display_name="Opaque Output",
        category="test",
        description="Returns an explicitly opaque output.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"snapshot": "opaque"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class MutatingInputNode:
    NODE_INFO = NodeInfo(
        type_key="test.mutating_input",
        display_name="Mutating Input",
        category="test",
        description="Mutates its input.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        inputs["value.in"].append(3)
        return {"value.out": inputs["value.in"]}


def test_runtime_rejects_non_json_snapshot_output() -> None:
    registry = NodeRegistry()
    registry.register("test.set_output", SetOutputNode)
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "set_output", "type": "test.set_output", "provides": ["value.out"]}]}})
    with pytest.raises(PipelineRuntimeError, match="not JSON snapshot serializable"):
        PipelineRuntime(graph, registry=registry).run()


def test_runtime_allows_explicit_opaque_snapshot_output() -> None:
    registry = NodeRegistry()
    registry.register("test.opaque_output", OpaqueOutputNode)
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "opaque", "type": "test.opaque_output", "provides": ["value.out"]}]}})
    context = PipelineRuntime(graph, registry=registry).run()
    assert context.get("value.out") == {1, 2}


def test_runtime_rejects_input_mutation() -> None:
    registry = NodeRegistry()
    registry.register("test.mutating_input", MutatingInputNode)
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


def test_architecture_smells_warn_for_mismatched_metadata_and_unstable_keys(tmp_path, capsys) -> None:
    info = VALID_NODE_INFO.replace('description="Demo node."', 'description="Calculates invoice total."')
    contract = """
    CONTRACT = NodeContract(
        provides=("Tmp Key",),
        output_semantics={"Tmp Key": ("scratch debug value",)},
        output_schema={"Tmp Key": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"Tmp Key": 1}},),
    )
""".rstrip()
    source = _valid_node_source(info=info, contract=contract, run_body='        return {"Tmp Key": 1}')
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    warnings = {warning["details"].get("legacy_code") for warning in payload["health"]["warnings"]}
    assert "responsibility_mismatch" in warnings
    assert "temporary_key" in warnings
    assert "confusing_key_name" in warnings


class DuplicateOneNode:
    NODE_INFO = NodeInfo("test.duplicate_one", "Duplicate One", "test", "Duplicates output.", "0.1.0")
    CONTRACT = NodeContract(
        provides=("dup.one",),
        output_semantics={"dup.one": ("duplicate value",)},
        output_schema={"dup.one": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.one": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.one": 1}


class DuplicateTwoNode:
    NODE_INFO = NodeInfo("test.duplicate_two", "Duplicate Two", "test", "Duplicates output.", "0.1.0")
    CONTRACT = NodeContract(
        provides=("dup.two",),
        output_semantics={"dup.two": ("duplicate value",)},
        output_schema={"dup.two": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.two": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.two": 1}


def test_graph_health_reports_node_metrics_duplicate_logic_and_confusing_node_names() -> None:
    registry = NodeRegistry()
    registry.register("test.duplicate_one", DuplicateOneNode)
    registry.register("test.duplicate_two", DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "DuplicateOne", "type": "test.duplicate_one", "provides": ["dup.one"]},
                    {"name": "duplicate_two", "type": "test.duplicate_two", "provides": ["dup.two"]},
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    assert payload["info"]["node_metrics"]["DuplicateOne"]["function_count"] == 1
    rule_ids = {warning["rule_id"] for warning in payload["warnings"]}
    assert "GRAPH.SMELL.CONFUSING_NODE_NAME" in rule_ids
    assert "GRAPH.SMELL.DUPLICATE_LOGIC" in rule_ids


def test_graph_health_warns_for_overwide_nodeset() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "wide.flow",
                    provides=["wide.out"],
                    exports=["wide.out"],
                    pipeline={
                        "nodes": [
                            {"name": f"n{index}", "type": "test.seed", "provides": [f"wide.k{index}"]}
                            for index in range(11)
                        ]
                    },
                )
            ],
            "pipeline": {"nodes": [{"name": "wide_flow", "type": "nodeset.wide.flow", "provides": ["wide.out"]}]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(warning.rule_id == "NODESET.SMELL.TOO_WIDE" for warning in report.warnings)
    assert "wide.flow" in report.info["nodeset_findings"]


def test_nodeset_schema_requires_metadata_contract_and_purity() -> None:
    findings = collect_config_schema_findings(
        {
            "nodesets": [
                {
                    "name": "bad.flow",
                    "purity": "impure",
                    "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
                }
            ],
            "pipeline": {"nodes": [{"name": "flow", "type": "nodeset.bad.flow", "provides": ["value.out"]}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.NODESET_METADATA" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_CONTRACT" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_PURITY" in rule_ids


def test_nodeset_health_accepts_valid_contract_and_groups_no_findings() -> None:
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
                        "nodes": [
                            {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
                        ],
                    },
                )
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "composite",
                        "type": "nodeset.math.add_one",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                    }
                ],
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.errors == ()
    assert report.info["nodeset_findings"] == {}


def test_nodeset_health_rejects_direct_and_indirect_recursion() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.self",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={
                        "nodes": [{"name": "self", "type": "nodeset.loop.self", "provides": ["loop.out"]}]
                    },
                ),
                _nodeset_config(
                    "loop.a",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [{"name": "to_b", "type": "nodeset.loop.b", "provides": ["loop.out"]}]},
                ),
                _nodeset_config(
                    "loop.b",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [{"name": "to_a", "type": "nodeset.loop.a", "provides": ["loop.out"]}]},
                ),
            ],
            "pipeline": {"nodes": [{"name": "use_self", "type": "nodeset.loop.self", "provides": ["loop.out"]}]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    recursion_errors = [error for error in report.errors if error.rule_id == "NODESET.RECURSION"]
    assert len(recursion_errors) == 2
    assert "loop.self" in report.info["nodeset_findings"]
    assert "loop.a" in report.info["nodeset_findings"]


def test_nodeset_health_rejects_export_and_internal_key_leak() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "bad.scope",
                    provides=["public.out", "tmp.internal"],
                    exports=["missing.out"],
                    pipeline={
                        "nodes": [
                            {"name": "public", "type": "test.seed", "provides": ["public.out"]},
                            {"name": "tmp", "type": "test.seed", "provides": ["tmp.internal"]},
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {
                        "name": "bad_scope",
                        "type": "nodeset.bad.scope",
                        "provides": ["public.out", "tmp.internal"],
                    }
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {error.rule_id for error in report.errors}
    assert "NODESET.CONTRACT.EXPORTS_NOT_PROVIDES" in rule_ids
    assert "NODESET.EXPORT.UNKNOWN_KEY" in rule_ids
    assert "NODESET.KEY_LEAK" in rule_ids
    assert "NODESET.INTERNAL_KEY_LEAK" in rule_ids


def test_nodeset_health_and_runtime_reject_external_contract_mismatch() -> None:
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
                        "nodes": [
                            {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
                        ],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {
                        "name": "bad_composite",
                        "type": "nodeset.math.add_one",
                        "provides": ["wrong.out"],
                    }
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(error.rule_id == "NODESET.CONTRACT.EXTERNAL_MISMATCH" for error in report.errors)
    with pytest.raises(PipelineRuntimeError, match="requires must match"):
        PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 2}})


def test_nodeset_health_rejects_nested_nodeset_contract_mismatch() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "inner.flow",
                    provides=["inner.out"],
                    exports=["inner.out"],
                    pipeline={"nodes": [{"name": "seed", "type": "test.seed", "provides": ["inner.out"]}]},
                ),
                _nodeset_config(
                    "outer.flow",
                    provides=["outer.out"],
                    exports=["outer.out"],
                    pipeline={"nodes": [{"name": "inner", "type": "nodeset.inner.flow", "provides": ["outer.out"]}]},
                ),
            ],
            "pipeline": {"nodes": [{"name": "outer", "type": "nodeset.outer.flow", "provides": ["outer.out"]}]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(
        error.rule_id == "NODESET.CONTRACT.EXTERNAL_MISMATCH" and error.details.get("owner") == "nodeset:outer.flow"
        for error in report.errors
    )


def test_base_lib_scan_discovers_default_root_and_reports_metrics(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "math_tools.py").write_text(
        """
def add_one(value):
    return value + 1
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    assert payload["roots"] == [str(base_dir.resolve())]
    assert payload["modules"][0]["module"] == "base_lib.math_tools"
    assert payload["modules"][0]["function_count"] == 1
    assert payload["findings"] == []


def test_base_lib_scan_reports_size_complexity_imports_side_effects_and_globals(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "bad.py").write_text(
        """
import os

CACHE = {}

def risky(value):
    if value:
        if value > 1:
            open("x.txt", "w")
    return value
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(
        tmp_path,
        policy=PurityPolicy(
            max_source_lines=3,
            max_functions=0,
            max_branches=1,
            max_nesting_depth=1,
        ),
    )
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "BASE_LIB.SOURCE.MAX_LINES" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_FUNCTIONS" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_BRANCHES" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_NESTING_DEPTH" in rule_ids
    assert "BASE_LIB.BANNED_IMPORT" in rule_ids
    assert "BASE_LIB.GLOBAL_STATE" in rule_ids
    assert "BASE_LIB.SIDE_EFFECT_CALL" in rule_ids


def test_base_lib_scan_reports_forbidden_project_import_and_dependency_closure(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "bad.py").write_text(
        """
from nodes.some_node import SomeNode

def value():
    return 1
""".strip(),
        encoding="utf-8",
    )
    (base_dir / "wrapper.py").write_text(
        """
import base_lib.bad

def wrapped():
    return base_lib.bad.value()
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {finding.rule_id for finding in report.findings}
    assert ("base_lib.wrapper", "base_lib.bad") in report.dependency_edges
    assert "BASE_LIB.FORBIDDEN_PROJECT_IMPORT" in rule_ids
    assert "BASE_LIB.DEPENDENCY_CLOSURE_VIOLATION" in rule_ids


def test_node_importing_base_lib_requires_policy_declaration(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "good.py").write_text(
        """
def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.good import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    assert any(error["details"].get("legacy_code") == "base_lib_undeclared" for error in payload["health"]["errors"])

    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.good"]}}',
        encoding="utf-8",
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert "base_lib.good" in {module["module"] for module in payload["base_lib"]["modules"]}


def test_node_importing_unhealthy_base_lib_reports_indirect_violation(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "bad.py").write_text(
        """
import os

def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.bad"]}}',
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.bad import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 1
    rule_ids = {error["rule_id"] for error in payload["health"]["errors"]}
    assert "BASE_LIB.BANNED_IMPORT" in rule_ids
    assert "NODE.BASE_LIB.INDIRECT_VIOLATION" in rule_ids


def _write_base_lib_chain(tmp_path: Path, modules: list[str]) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    for index, name in enumerate(modules):
        next_name = modules[index + 1] if index + 1 < len(modules) else ""
        body = f"import base_lib.{next_name}\n\n\ndef helper():\n    return base_lib.{next_name}.helper()\n" if next_name else "\ndef helper():\n    return 1\n"
        (base_dir / f"{name}.py").write_text(body, encoding="utf-8")


def _clear_base_lib_modules() -> None:
    for name in tuple(sys.modules):
        if name == "base_lib" or name.startswith("base_lib."):
            sys.modules.pop(name, None)


def test_node_base_lib_dependency_chain_warning_and_error(tmp_path, capsys, monkeypatch) -> None:
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_base_lib_chain(tmp_path, ["a", "b", "c", "d"])
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.a"]}}',
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.a import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    warning = next(item for item in payload["health"]["warnings"] if item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP")
    assert warning["details"]["longest_chain_length"] == 5
    assert warning["details"]["longest_chain"] == ["node", "base_lib.a", "base_lib.b", "base_lib.c", "base_lib.d"]
    assert payload["base_lib_dependency_chain"]["longest_chain_length"] == 5

    deeper = tmp_path / "deep"
    deeper.mkdir()
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(deeper))
    _write_base_lib_chain(deeper, ["a", "b", "c", "d", "e", "f"])
    deep_policy = deeper / "kernel_policy.jsonc"
    deep_policy.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.a"]}}',
        encoding="utf-8",
    )
    code, payload = _inspect_node_source(deeper, capsys, source, extra_args=["--policy", str(deep_policy)])
    assert code == 1
    error = next(item for item in payload["health"]["errors"] if item["rule_id"] == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP")
    assert error["details"]["longest_chain_length"] == 7
    assert error["suggested_fix_type"] == "fix_base_lib"


def test_jsonc_loader_strips_comments_without_changing_runtime_data(tmp_path) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  // this comment must not become data
  "url": "http://example.test/not//comment",
  "marker": "/* not a comment */",
  /*
    block comment
  */
  "pipeline": {
    "nodes": [
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )
    document = load_config_document(config_path)
    assert document.format == "jsonc"
    assert "comment" not in document.data
    assert document.data["url"] == "http://example.test/not//comment"
    assert document.data["marker"] == "/* not a comment */"


def test_jsonc_loader_reports_unterminated_block_comment_location(tmp_path) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {},\n  /* missing end\n', encoding="utf-8")
    with pytest.raises(ConfigLoadError) as exc_info:
        load_config_document(config_path)
    exc = exc_info.value
    assert exc.rule_id == "CONFIG.JSONC.UNTERMINATED_BLOCK_COMMENT"
    assert exc.failure_layer == "syntax"
    assert exc.source_location["line"] == 3
    assert exc.source_location["column"] == 3


def test_jsonc_loader_keeps_parse_error_location_after_comments(tmp_path) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text(
        '{\n  // stable width comment\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError) as exc_info:
        load_config_document(config_path)
    exc = exc_info.value
    assert exc.rule_id == "CONFIG.JSON"
    assert exc.source_location["line"] == 4
    assert exc.source_location["column"] > 1


def test_policy_default_discovery_explicit_and_inline_merge_order(tmp_path) -> None:
    config_path = tmp_path / "workflow.jsonc"
    discovered_path = tmp_path / "kernel_policy.jsonc"
    explicit_path = tmp_path / "explicit_policy.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "policy": {
                    "node_source": {"max_bytes": 3000},
                    "imports": {"allowed_roots": ["inline_allowed"]},
                    "rules": {
                        "downgrades": [
                            {
                                "rule_id": "NODE.SOURCE.MAX_LINES",
                                "to": "warning",
                                "scope": {"node": "inline"},
                                "reason": "inline",
                                "expires": "2026-12-31",
                            }
                        ]
                    },
                },
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        ),
        encoding="utf-8",
    )
    discovered_path.write_text(
        '{"node_source": {"max_lines": 400}, "imports": {"allowed_roots": ["discovered"]}}',
        encoding="utf-8",
    )
    explicit_path.write_text(
        json.dumps(
            {
                "policy": {
                    "node_source": {"max_lines": 250},
                    "imports": {"allowed_roots": ["explicit"]},
                    "rules": {
                        "downgrades": [
                            {
                                "rule_id": "NODE.IMPORT.BANNED",
                                "to": "info",
                                "scope": {"node": "explicit"},
                                "reason": "explicit",
                                "expires": "2026-12-31",
                            }
                        ],
                        "exemptions": [
                            {
                                "rule_id": "NODE.IMPORT.BANNED",
                                "scope": {"node": "explicit"},
                                "reason": "explicit",
                                "expires": "2026-12-31",
                            }
                        ],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    document = load_config_document(config_path)
    result = resolve_effective_policy(document.data, config_path=config_path, explicit_policy_path=explicit_path)
    policy = result.effective_policy.to_dict()
    assert result.findings == ()
    assert policy["node_source"]["max_lines"] == 250
    assert policy["node_source"]["max_bytes"] == 3000
    assert policy["imports"]["allowed_roots"] == ["inline_allowed"]
    assert len(policy["rules"]["downgrades"]) == 2
    assert len(policy["rules"]["exemptions"]) == 1
    assert policy["sources"][0] == "kernel.default_policy"
    assert f"project.policy:{discovered_path}" in policy["sources"]
    assert f"project.policy:{explicit_path}" in policy["sources"]
    assert policy["sources"][-1] == "config.inline_policy"


def test_policy_discovery_prefers_kernel_policy_over_governance(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text('{"pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]}}', encoding="utf-8")
    (tmp_path / "kernel_policy.jsonc").write_text('{"node_source": {"max_lines": 321}}', encoding="utf-8")
    (tmp_path / "governance.jsonc").write_text('{"node_source": {"max_lines": 123}}', encoding="utf-8")
    result = resolve_effective_policy(load_config_document(config_path).data, config_path=config_path)
    policy = result.effective_policy.to_dict()
    assert policy["node_source"]["max_lines"] == 321
    assert f"project.policy:{tmp_path / 'governance.jsonc'}" not in policy["sources"]


def test_schema_validation_rejects_invalid_pipeline_shapes() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    {"type": "test.seed"},
                    {"name": "bad_requires", "type": "test.seed", "requires": "x"},
                ],
                "edges": [{"from": "a", "to": "b", "max_executions": 0}],
                "loops": [{"name": "loop", "edges": [["a", "b"]]}],
            },
            "nodesets": [{"name": "bad"}],
            "boundary": {"config": []},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    object_ids = {finding.object_id for finding in findings}
    assert "CONFIG.SCHEMA.NODE_MISSING_NAME" in rule_ids
    assert "CONFIG.SCHEMA.NODE_REQUIRES_LIST" in rule_ids
    assert "CONFIG.SCHEMA.EDGE_MAX_EXECUTIONS" in rule_ids
    assert "CONFIG.SCHEMA.LOOP_MAX_ITERATIONS" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_PIPELINE" in rule_ids
    assert "CONFIG.SCHEMA.BOUNDARY_TYPE" in rule_ids
    assert "pipeline.nodes[0].name" in object_ids


def test_schema_validation_rejects_policy_bool_as_int() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {"node_source": {"max_lines": True}},
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
        }
    )
    assert any(finding.object_id == "policy.node_source.max_lines" for finding in findings)
    assert any(finding.rule_id == "CONFIG.SCHEMA.POLICY_POSITIVE_INT" for finding in findings)


def test_cli_validate_jsonc_outputs_effective_policy(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "policy": {
    "node_source": {"max_lines": 222},
    "base_lib": {"allowed_paths": ["src/shared"], "allowed_modules": ["shared.math"]}
  },
  "pipeline": {
    // data edge should be inferred
    "nodes": [
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
      {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["effective_policy"]["node_source"]["max_lines"] == 222
    assert payload["effective_policy"]["base_lib"]["allowed_modules"] == ["shared.math"]
    assert payload["effective_policy"]["sources"][-1] == "config.inline_policy"


def test_cli_validate_bad_jsonc_reports_syntax_layer(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["failure_layer"] == "syntax"
    assert payload["errors"][0]["source_location"]["line"] == 3


def test_cli_validate_schema_error_reports_schema_layer(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_schema.json"
    config_path.write_text('{"pipeline": {"nodes": [{"type": "test.seed"}]}}', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["rule_id"] == "CONFIG.SCHEMA.NODE_MISSING_NAME"
    assert payload["errors"][0]["failure_layer"] == "schema"


def test_cli_validate_topology_error_reports_topology_layer(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad_topology.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [{"name": "seed", "type": "test.seed"}],
                    "edges": [["seed", "missing"]],
                }
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["errors"][0]["failure_layer"] == "topology"


def test_cli_validate_explicit_policy_path_and_inspect_config(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    policy_path = tmp_path / "policy.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    policy_path.write_text('{"node_source": {"max_lines": 111}}', encoding="utf-8")
    code = cli_main(["inspect-config", "--config", str(config_path), "--policy", str(policy_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["effective_policy"]["node_source"]["max_lines"] == 111
    assert payload["config"]["effective_edges"] == [["seed", "add"]]


def test_cli_export_mermaid_reads_jsonc(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        """
{
  "pipeline": {
    "nodes": [
      {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
      {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}
    ]
  }
}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["export-mermaid", "--config", str(config_path)])
    output = capsys.readouterr().out
    assert code == 0
    assert "flowchart TD" in output
    assert "seed -->|max=1| add" in output
    assert "provides: value.in" in output


def test_cli_export_mermaid_writes_output_and_expands_nodesets(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.mmd"
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
                            "nodes": [{"name": "inner", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}],
                        },
                    )
                ],
                "pipeline": {
                    "inputs": ["value.in"],
                    "nodes": [
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": ["value.in"],
                            "provides": ["value.out"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(["export-mermaid", "--config", str(config_path), "--output", str(output_path), "--expand-nodesets"])
    assert capsys.readouterr().out == ""
    assert code == 0
    output = output_path.read_text(encoding="utf-8")
    assert "flowchart TD" in output
    assert 'subgraph composite__expanded["math.add_one"]' in output
    assert "composite__inner" in output


def test_cli_export_mermaid_reports_config_errors_as_health_report(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")
    code = cli_main(["export-mermaid", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 3


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_minimal_example_project_runs_only_through_declared_extension_points(tmp_path, monkeypatch) -> None:
    project = _repo_root() / "examples" / "minimal_project"
    _clear_base_lib_modules()
    monkeypatch.syspath_prepend(str(project))
    module = _load_module_from_path(project / "nodes.py", "_minimal_project_nodes")
    registry = NodeRegistry()
    registry.register("example.seed", module.SeedNode)
    registry.register("example.add", module.AddNode)

    result = run_checked(
        project / "config.jsonc",
        registry=registry,
        run_root=tmp_path / "runs",
        run_id="minimal_example",
    )

    assert result.context.get("value.out") == 5
    assert result.health.status == "CONCERNS"
    assert "plugin.policy:minimal_project_policy" in result.health.effective_policy["sources"]
    assert result.health.effective_policy["base_lib"]["allowed_modules"] == ["base_lib.math_tools"]
    assert (result.run_dir / "compiled_graph.json").exists()
    assert (result.run_dir / "graph.mmd").exists()
    assert "nodeset.example.add_one" in (result.run_dir / "graph.mmd").read_text(encoding="utf-8")


def _failure_case_source(case: dict[str, object]) -> str:
    kind = str(case.get("kind", ""))
    if kind == "generated_giant_node":
        return _valid_node_source() + "\n" + "\n".join("    # filler line" for _ in range(510))
    if kind == "node_mutual_call":
        return f"""
{VALID_NODE_IMPORT}
class OtherNode:
    NODE_INFO = NodeInfo(type_key="demo.other", display_name="Other", category="demo", description="Other node.", version="0.1.0")
    CONTRACT = NodeContract(provides=("other.out",), output_semantics={{"other.out": ("other output",)}}, output_schema={{"other.out": {{"type": "number"}}}}, examples=({{"inputs": {{}}, "params": {{}}, "outputs": {{"other.out": 1}}}},))

    def run_pure(self, inputs, params):
        return {{"other.out": 1}}


class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        OtherNode().run_pure({{}}, {{}})
        return {{"demo.out": 1}}
"""
    return _valid_node_source(run_body=str(case["run_body"]))


def test_failure_examples_manifest_covers_absolute_guardrails(tmp_path, capsys) -> None:
    manifest = load_config_document(_repo_root() / "examples" / "failure_cases" / "cases.jsonc").data
    observed: set[str] = set()

    for case in manifest["node_cases"]:
        code, payload = _inspect_node_source(tmp_path / str(case["name"]), capsys, _failure_case_source(case))
        assert code == 1
        legacy_codes = {
            finding["details"].get("legacy_code")
            for finding in (*payload["health"]["errors"], *payload["health"]["warnings"])
        }
        expected = str(case["expected_legacy_code"])
        assert expected in legacy_codes
        observed.add(expected)

    for case in manifest["config_cases"]:
        config_path = tmp_path / f"{case['name']}.json"
        config_path.write_text(json.dumps(case["config"]), encoding="utf-8")
        code = cli_main(["validate", "--config", str(config_path), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 1
        rule_ids = {finding["rule_id"] for finding in (*payload["errors"], *payload["warnings"])}
        expected_rule = str(case["expected_rule_id"])
        assert expected_rule in rule_ids
        observed.add(expected_rule)

    for case in manifest["base_lib_cases"]:
        base_dir = tmp_path / str(case["name"]) / "base_lib"
        base_dir.mkdir(parents=True)
        (base_dir / "bad.py").write_text(str(case["module_source"]), encoding="utf-8")
        report = scan_base_lib(base_dir.parent, policy=PurityPolicy(max_source_lines=1000))
        rule_ids = {finding.rule_id for finding in report.findings}
        expected_rule = str(case["expected_rule_id"])
        assert expected_rule in rule_ids
        observed.add(expected_rule)

    assert {
        "source_too_large",
        "banned_call",
        "node_direct_call",
        "GRAPH.COMPILE",
        "CONFIG.SCHEMA.BOUNDARY_CONSUMES_KEY",
        "BASE_LIB.FORBIDDEN_PROJECT_IMPORT",
    } <= observed


def test_policy_downgrade_schema_requires_audit_fields() -> None:
    findings = collect_config_schema_findings(
        {
            "policy": {
                "rules": {
                    "downgrades": [
                        {"rule_id": "GRAPH.OUTPUT.UNCONSUMED", "to": "warning", "scope": "bad"}
                    ]
                }
            },
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.POLICY_RULE_REASON" in rule_ids
    assert "CONFIG.SCHEMA.POLICY_RULE_SCOPE" in rule_ids
    assert "CONFIG.SCHEMA.POLICY_RULE_EXPIRES" in rule_ids


def test_mermaid_collapsed_and_expanded_views_share_top_level_compiled_edges() -> None:
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
                        "nodes": [{"name": "inner", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]}],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "flow", "type": "nodeset.math.add_one", "requires": ["value.in"], "provides": ["value.out"]},
                ]
            },
        }
    )
    collapsed = export_mermaid(graph, expand_nodesets=False)
    expanded = export_mermaid(graph, expand_nodesets=True)
    assert "seed -->|max=1| flow" in collapsed
    assert "seed -->|max=1| flow" in expanded
    assert "flow__inner" not in collapsed
    assert "flow__inner" in expanded


def test_checked_run_artifact_integrity_cross_links_health_graph_trace(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 6},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 2},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="integrity")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    health = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    trace = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]

    assert result.context.get("value.out") == 8
    assert health["status"] == result.health.status
    assert compiled["effective_edges"] == [{"from": "seed", "to": "add", "max_executions": 1, "loop": ""}]
    assert "seed -->|max=1| add" in graph_mmd
    assert [event["node"] for event in trace if event.get("kind") == "node"] == ["seed", "add"]


def test_code_quality_tool_reports_file_function_dependency_and_side_effect_findings(tmp_path) -> None:
    (tmp_path / "a.py").write_text(
        "\n".join(
            [
                "import b",
                "",
                "def too_big(flag):",
                "    if flag:",
                "        if flag > 1:",
                "            return open('x.txt').read()",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("import c\n\ndef helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("def leaf():\n    return 1\n", encoding="utf-8")

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(
            max_file_lines=5,
            warn_file_lines=4,
            max_function_lines=3,
            max_function_branches=1,
            max_function_nesting=1,
            warn_dependency_chain=2,
            max_dependency_chain=2,
        ),
    )

    rule_ids = {finding.rule_id for finding in report.findings}
    assert report.status == "FAIL"
    assert "QUALITY.FILE.MAX_LINES" in rule_ids
    assert "QUALITY.FUNCTION.MAX_LINES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_MANY_BRANCHES" in rule_ids
    assert "QUALITY.FUNCTION.TOO_DEEP_NESTING" in rule_ids
    assert "QUALITY.SIDE_EFFECT.CALL" in rule_ids
    assert "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP" in rule_ids
    assert report.longest_dependency_chain == ("a", "b", "c")


def test_code_quality_tool_detects_cycles_and_duplicate_function_fingerprints(tmp_path) -> None:
    (tmp_path / "a.py").write_text(
        "import b\n\ndef normalize_one(value):\n    result = value + 1\n    return result\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "import a\n\ndef normalize_two(item):\n    result = item + 1\n    return result\n",
        encoding="utf-8",
    )

    report = scan_code_quality(tmp_path)
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "QUALITY.DEPENDENCY.CYCLE" in rule_ids
    assert "QUALITY.DEPENDENCY.BIDIRECTIONAL" in rule_ids
    assert "QUALITY.DUPLICATE.AST_FINGERPRINT" in rule_ids


def test_code_quality_tool_reports_python_syntax_errors(tmp_path) -> None:
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = scan_code_quality(tmp_path)

    assert report.status == "FAIL"
    assert any(finding.rule_id == "QUALITY.SYNTAX.PYTHON" for finding in report.findings)


def test_cli_quality_check_json_and_text_outputs(tmp_path, capsys) -> None:
    (tmp_path / "bad.py").write_text("def side_effect():\n    return open('x.txt').read()\n", encoding="utf-8")

    json_code = cli_main(["quality-check", "--path", str(tmp_path), "--json"])
    json_payload = json.loads(capsys.readouterr().out)
    text_code = cli_main(["quality-check", "--path", str(tmp_path)])
    text_output = capsys.readouterr().out

    assert json_code == 0
    assert json_payload["status"] == "CONCERNS"
    assert json_payload["warnings"][0]["rule_id"] == "QUALITY.SIDE_EFFECT.CALL"
    assert text_code == 0
    assert "QUALITY.SIDE_EFFECT.CALL" in text_output
