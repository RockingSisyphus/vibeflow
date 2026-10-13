"""Public Core → plan → Python/JavaScript regressions for parallel routes."""
from dataclasses import replace
import json
import subprocess
from types import SimpleNamespace

import pytest

from vibeflow.block_compiler import compile_workflow
from vibeflow.core.compiler import GraphCompileError, compile_core
from vibeflow.core.contracts import DataProvider, DataRequirement, PipelineInputSpec, PipelineOutputSpec
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec
from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts
from vibeflow.targets.javascript.frontend.bindings import build_javascript_binding_plan
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.python.runtime.engine import PipelineRuntime
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.shared.quality_support.workflow_rules.flow import append_flowchart_health
from vibeflow.targets.shared.quality_support.workflow_rules.flow_data import append_data_contract_warnings
from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
from vibeflow.tooling.application.python.project.declarations import default_python_registry


DONE = "route == 'done'"
FAILED = "route == 'failed'"
ROUTES = [
    (DONE, FAILED), (FAILED, DONE), ("", FAILED), (FAILED, ""),
    (DONE, DONE), (DONE, "route != 'failed'"), (FAILED,),
]


class Start:
    def run_pure(self, inputs, params):
        return {}


class Emit:
    def run_pure(self, inputs, params):
        return {"route": inputs["event"]["value"], "payload": 42}


class Finish:
    def run_pure(self, inputs, params):
        return {"answer": (inputs.get("payload") or {}).get("value", -1)}


def graph_for(conditions, *, optional=False, join="safe_any", mode="sync"):
    return GraphConfig(
        nodes=(NodeSpec("start", "probe.start", flow_kind="terminal"),
               NodeSpec("emit", "probe.emit", flow_kind="process",
                        requires=(DataRequirement("event", "exactly_one"),),
                        provides=(DataProvider("route", "route"), DataProvider("payload", "payload"))),
               NodeSpec("finish", "probe.finish", flow_kind="process", join_policy=join,
                        requires=(DataRequirement("payload", "optional_one" if optional else "exactly_one"),),
                        provides=(DataProvider("answer", "answer"),)),
               NodeSpec("end", "probe.end", flow_kind="terminal",
                        requires=(DataRequirement("answer", "exactly_one"),))),
        edges=(EdgeSpec("start", "emit"),
               *(EdgeSpec("emit", "finish", when=condition) for condition in conditions),
               EdgeSpec("finish", "end")),
        inputs=(PipelineInputSpec("event", "event", required=True),),
        outputs=(PipelineOutputSpec("answer", "exactly_one", "answer"),),
        root_id="probe.routes", entry_mode=mode,
    )


def compile_graph(graph):
    facts = ImplementationFacts(tuple(
        ImplementationFact(n.type_used, flow_kind=n.flow_kind, requires=n.requires, provides=n.provides,
                           source_kind="file", source_ref="./nodes.mjs", source_export=n.id)
        for n in graph.nodes), strict=True)
    return compile_core(CoreCompileRequest(graph, facts)), facts


def expected_value(conditions, event):
    # These expectations describe the fixture's inputs, independently of Core.
    return 42 if ("" in conditions or (event == "done" and DONE in conditions)
                  or (event == "failed" and FAILED in conditions)
                  or (event != "failed" and "route != 'failed'" in conditions)) else None


def python_runtime(graph, execution):
    registry = default_python_registry()
    for node, implementation in zip(graph.nodes, (Start, Emit, Finish, Start)):
        descriptor = NodeDescriptor(node.type_used, node.id, "Conditional route regression.", "1.0.0",
                                    node.flow_kind, contract=NodeContractDescriptor(
                                        requires=tuple(replace(r, display_name=r.type) for r in node.requires),
                                        provides=tuple(replace(p, display_name=p.key) for p in node.provides),
                                        input_semantics={r.type: ("Fixture input.",) for r in node.requires},
                                        output_semantics={p.key: ("Fixture output.",) for p in node.provides}))
        registry.register(descriptor, implementation)
    return PipelineRuntime(graph, registry=registry, runtime_options={"execution": execution})


@pytest.mark.parametrize("conditions", ROUTES)
@pytest.mark.parametrize("join", ["safe_any", "all"])
@pytest.mark.parametrize("execution", ["plan", "compiled", "block"])
def test_python_preserves_routes_and_executes_once(conditions, join, execution):
    graph = graph_for(conditions, join=join)
    runtime = python_runtime(graph, execution)
    for event in ("done", "failed", "unknown"):
        expected = expected_value(conditions, event)
        if expected is None:
            with pytest.raises(PipelineRuntimeError, match="expected exactly one value, got 0"):
                runtime.run({"event": event})
        else:
            assert runtime.run({"event": event}).get("answer")["value"] == expected
        assert runtime._node_runs["finish"] == (0 if expected is None else 1)


def run_javascript(tmp_path, graph):
    compilation, facts = compile_graph(graph)
    plan = compile_workflow(compilation.workflow, facts)
    bindings = build_javascript_binding_plan(plan, schemas={
        "event": {"type": "string"}, "route": {"type": "string"},
        "payload": {"type": "number"}, "answer": {"type": "number"}})
    emitted = emit_workflow_module(plan, javascript_bindings=bindings)
    (tmp_path / "workflow.mjs").write_text(emitted.source)
    (tmp_path / "nodes.mjs").write_text(
        "export function start() { return {}; }\n"
        "export function emit(inputs) { return {route: inputs.event.value, payload: 42}; }\n"
        "export function finish(inputs) { return {answer: inputs.payload?.value ?? -1}; }\n"
        "export function end() { return {}; }\n")
    script = """
import * as module from './workflow.mjs';
const rows = [];
for (const event of ['done', 'failed', 'unknown']) {
  const trace = []; let result, error;
  try { result = await (module.runWorkflow || module.runWorkflowAsync)(
    {event}, {trace: 'full', onTrace: item => trace.push(item)}); }
  catch (cause) { error = cause.code; }
  rows.push({event, result, error,
    count: trace.filter(item => item.kind === 'node_start' && item.nodeId === 'finish').length});
}
console.log(JSON.stringify(rows));
"""
    completed = subprocess.run(["node", "--input-type=module", "--eval", script], cwd=tmp_path,
                               text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("conditions", ROUTES)
@pytest.mark.parametrize("join", ["safe_any", "all"])
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_javascript_preserves_routes_and_executes_once(tmp_path, conditions, join, mode):
    for row in run_javascript(tmp_path, graph_for(conditions, join=join, mode=mode)):
        expected = expected_value(conditions, row["event"])
        if expected is None:
            assert row["error"] == "VF_OUTPUT_CARDINALITY"
        else:
            assert row["result"]["answer"] == expected
        assert row["count"] == (0 if expected is None else 1)


@pytest.mark.parametrize("change", [dict(when=FAILED), dict(schedule=True), dict(transfer=True),
                                     dict(when="route == \"done\"")])
def test_only_identical_declarations_are_deduplicated(change):
    graph = graph_for((DONE,))
    original = graph.edges[1]
    different = replace(original, **change)
    graph = replace(graph, edges=(*graph.edges, original, different))
    compilation, facts = compile_graph(graph)
    assert compilation.compiled_graph.effective_edges == (*graph.edges[:3], different)
    assert len(compile_workflow(compilation.workflow, facts).blocks[0].routes) == 4


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("same_condition", [False, True])
def test_schedule_and_transfer_permissions_stay_on_their_routes(tmp_path, target, same_condition):
    graph = graph_for((DONE, DONE if same_condition else FAILED), optional=True)
    graph = replace(graph, edges=(graph.edges[0],
        replace(graph.edges[1], schedule=True, transfer=False),
        replace(graph.edges[2], schedule=False, transfer=True), graph.edges[-1]))
    compilation, facts = compile_graph(graph)
    routes = compile_workflow(compilation.workflow, facts).blocks[0].routes[1:3]
    assert [(r.schedule, r.transfer) for r in routes] == [(True, False), (False, True)]
    expected = 42 if same_condition else -1
    if target == "python":
        runtime = python_runtime(graph, "block")
        assert runtime.run({"event": "done"}).get("answer")["value"] == expected
        with pytest.raises(PipelineRuntimeError, match="expected exactly one value, got 0"):
            runtime.run({"event": "failed"})
    else:
        rows = run_javascript(tmp_path, graph)
        assert rows[0]["result"]["answer"] == expected
        assert rows[1]["error"] == "VF_OUTPUT_CARDINALITY"


@pytest.mark.parametrize("conditions", ROUTES)
def test_rules_count_sources_instead_of_alternative_routes(conditions):
    graph = graph_for(conditions)
    compilation, _ = compile_graph(graph)
    state = SimpleNamespace(errors=[], warnings=[])
    append_flowchart_health(graph, compilation.compiled_graph, state)
    append_data_contract_warnings(graph, compilation.compiled_graph, state)
    append_join_policy_health(graph, compilation.compiled_graph, state)
    codes = {item.rule_id for item in (*state.errors, *state.warnings)}
    assert not codes & {"GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS", "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL",
                        "GRAPH.EDGE.CONFLICTING_DUPLICATE", "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT"}
    assert ("GRAPH.EDGE.DUPLICATE" in codes) == (conditions == (DONE, DONE))


def test_roleless_route_cannot_borrow_roles_from_another_route():
    graph = graph_for((DONE, FAILED))
    graph = replace(graph, edges=(graph.edges[0], graph.edges[1],
                                replace(graph.edges[2], schedule=False, transfer=False), graph.edges[-1]))
    with pytest.raises(GraphCompileError) as error:
        compile_graph(graph)
    assert error.value.rule_id == "GRAPH.EDGE.NO_ROLE"


def test_inferred_bypass_does_not_disable_parallel_conditional_route():
    graph = graph_for(("", DONE))
    graph = replace(graph, nodes=(*graph.nodes[:2], NodeSpec("middle", "probe.middle", flow_kind="process"),
                                 *graph.nodes[2:]),
                    edges=(*graph.edges, EdgeSpec("emit", "middle"), EdgeSpec("middle", "finish")))
    compilation, _ = compile_graph(graph)
    unconditional, conditional = graph.edges[1:3]
    assert unconditional not in compilation.compiled_graph.resolved_schedule_edges
    assert conditional in compilation.compiled_graph.resolved_schedule_edges
