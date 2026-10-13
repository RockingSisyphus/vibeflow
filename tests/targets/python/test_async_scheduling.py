"""Activated side tasks run before a terminal can stop the native scheduler."""
import json

import pytest

from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.project.graph_config import parse_graph_config


class _Terminal:
    def run_pure(self, inputs, params):
        return {}


class _Launch:
    def run_pure(self, inputs, params, context):
        ref=context.tasks.start("work", {})
        assert context.tasks.wait_all_exited([ref])[0]["status"]=="succeeded"
        return {}


class _Audit:
    def run_pure(self, inputs, params):
        return {}


@pytest.mark.parametrize("execution", ("plan", "block", "compiled"))
@pytest.mark.parametrize("reverse_edges", (False, True))
def test_outputless_declared_task_is_started_and_settled_before_terminal(tmp_path, execution, reverse_edges):
    registry = native_registry()
    for key, kind, implementation in (("test.terminal", "terminal", _Terminal), ("test.audit", "process", _Audit), ("test.launch", "task_manager", _Launch)):
        registry.register(NodeDescriptor(key, key, "Native scheduling fixture", "1", kind,
            contract=NodeContractDescriptor(), rulesets=()), implementation)
    edges = [{"from":"start", "to":"audit"}, {"from":"start", "to":"end"}, {"from":"audit", "to":"end"}]
    graph = parse_graph_config({"pipeline":{"entry_mode":"async", "nodes":[
        {"id":name, "type_used":"test.launch" if name == "audit" else "test.terminal",
         "display_name":name, "description":"Schedules an outputless side task",
         **({"task_targets":{"work":{"type_used":"test.audit"}}} if name == "audit" else {})}
        for name in ("start", "audit", "end")], "edges":list(reversed(edges)) if reverse_edges else edges,
        "outputs":[]}})
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
        runtime_options=RuntimeOptions(execution=execution, trace="full"))
    result = runtime.run({})
    assert set(result.to_dict()) == {"runtime"}
    assert runtime.trace.node_runs == {"start":1, "audit":1, "end":1}
    events = [json.loads(line) for line in (tmp_path / "runtime_trace.jsonl").read_text().splitlines()]
    assert {event["kind"] for event in events if event["kind"].startswith("task_")} == {
        "task_started", "task_exited"}


class _Decision:
    def run_pure(self, inputs, params):
        return {"flow.route":"done"}


@pytest.mark.parametrize("execution", ("plan", "block", "compiled"))
def test_inactive_conditional_edge_does_not_start_a_declared_task(tmp_path, execution):
    from vibeflow.core.contracts import DataProvider
    registry = native_registry()
    for key, kind, implementation, contract in (
        ("test.terminal", "terminal", _Terminal, NodeContractDescriptor()),
        ("test.audit", "process", _Audit, NodeContractDescriptor()),
        ("test.launch", "task_manager", _Launch, NodeContractDescriptor()),
        ("test.decision", "decision", _Decision, NodeContractDescriptor(
            provides=(DataProvider("flow.route", "flow.route", display_name="Route"),),
            output_semantics={"flow.route":("Selects the completed mainline",)})),
    ):
        registry.register(NodeDescriptor(key, key, "Conditional scheduling fixture", "1", kind,
            contract=contract, rulesets=()), implementation)
    graph = parse_graph_config({"pipeline":{"entry_mode":"async", "nodes":[
        {"id":name, "type_used":"test.launch" if name == "audit" else "test.decision" if name == "route" else "test.terminal",
         "display_name":name, "description":"Only active task routes execute",
         **({"task_targets":{"work":{"type_used":"test.audit"}}} if name == "audit" else {})}
        for name in ("start", "route", "audit", "end")], "edges":[
            {"from":"start", "to":"route"},
            {"from":"route", "to":"audit", "when":"flow.route == 'audit'"},
            {"from":"route", "to":"end", "when":"flow.route == 'done'"},{"from":"audit","to":"end"}], "outputs":[]}})
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
        runtime_options=RuntimeOptions(execution=execution, trace="full"))
    runtime.run({})
    assert runtime.trace.node_runs == {"start":1, "route":1, "end":1}
    assert not any(json.loads(line)["kind"].startswith("task_")
        for line in (tmp_path / "runtime_trace.jsonl").read_text().splitlines())
