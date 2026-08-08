"""Integration gates for the Python Target runtime."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

import pytest

from tests.fixtures.support.strict_support import (
    PROV_SPEC,
    REQ_SPEC,
    _edge_chain,
    _input_add_pipeline,
    _node_call,
    _nodeset_config,
    _registry,
    _seed_add_pipeline,
)
from tests.targets.python.strict_planned_behavior import _planned_stub_config
from tests.targets.python.strict_runtime import _loop_registry, _while_loop_graph
from vibeflow.core import DataProvider, DataRequirement
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.targets.python.project import (
    NodeContract,
    NodeInfo,
    NodeRegistry,
    PluginRegistry,
)
from vibeflow.targets.python.runtime import (
    ExecutionPlan,
    PipelineRuntime,
    RuntimeOptions,
)


EXECUTION_MODES = ("plan", "block", "compiled")


class _DoubleNode:
    NODE_INFO = NodeInfo(
        "integration.double",
        "Double",
        "integration",
        "Doubles a received number.",
        "1.0.0",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one", display_name="number"),),
        provides=(DataProvider("answer", "answer", display_name="answer"),),
    )

    def run_pure(self, inputs, params):
        del params
        return {"answer": inputs["number"]["value"] * 2}


def _trace_lines(result) -> list[dict[str, object]]:
    trace_path = Path(result.get("runtime.trace_path"))
    return [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _frame_at(plan: ExecutionPlan, path: tuple[str, ...]):
    current = plan
    frame = None
    for index, node_id in enumerate(path):
        frame = current.frame(node_id)
        if index < len(path) - 1:
            assert frame.subplan is not None
            current = frame.subplan
    assert frame is not None
    return frame


def _child_binding_plans(binding_plan):
    for child in binding_plan.children:
        yield child
        yield from _child_binding_plans(child)


def _assert_live_node_bindings(plan: ExecutionPlan) -> None:
    for binding in plan.binding_plan.all_bindings():
        frame = _frame_at(plan, binding.path)
        assert frame.node is not None
        assert binding.implementation is frame.node
        assert dict(binding.effective_params) == dict(frame.params)
        assert binding.source.kind == "python"
        assert binding.source.ref == type(frame.node).__module__
        assert binding.source.export == type(frame.node).__qualname__
        assert binding.source_hash == ""


def _assert_plain_json_tree(value: object) -> None:
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            _assert_plain_json_tree(item)
        return
    assert isinstance(value, dict)
    for key, item in value.items():
        assert isinstance(key, str)
        _assert_plain_json_tree(item)


def test_real_binding_sidecar_covers_nodes_nodesets_and_loops(
    tmp_path: Path,
) -> None:
    plugins = PluginRegistry()
    ordinary = PipelineRuntime(
        parse_graph_config(
            {"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})}
        ),
        registry=_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path / "ordinary",
    )._plan
    nested = PipelineRuntime(
        parse_graph_config(
            {
                "nodesets": [
                    _nodeset_config(
                        "math.add_one",
                        requires=["value.in"],
                        provides=["value.out"],
                        exports=["value.out"],
                        pipeline=_input_add_pipeline(add={"delta": 6}),
                    )
                ],
                "pipeline": {
                    "inputs": [PROV_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the flow."),
                        _node_call(
                            "composite",
                            "math.add_one",
                            "Runs a nested add.",
                            requires=[REQ_SPEC("value.in")],
                            provides=[PROV_SPEC("value.out")],
                        ),
                        _node_call(
                            "end",
                            "test.out_end",
                            "Consumes the nested output.",
                            requires=[REQ_SPEC("value.out")],
                        ),
                    ],
                    "edges": _edge_chain("start", "composite", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        registry=_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path / "nested",
    )._plan
    loop = PipelineRuntime(
        _while_loop_graph(target=3),
        registry=_loop_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path / "loop",
    )._plan

    assert {binding.path for binding in ordinary.binding_plan.all_bindings()} == {
        ("start",),
        ("seed",),
        ("add",),
        ("end",),
    }
    assert {binding.path for binding in nested.binding_plan.all_bindings()} == {
        ("start",),
        ("end",),
        ("composite", "start"),
        ("composite", "add"),
        ("composite", "end"),
    }
    assert {binding.path for binding in loop.binding_plan.all_bindings()} == {
        ("start",),
        ("end",),
        ("while_loop", "start"),
        ("while_loop", "step"),
        ("while_loop", "end"),
    }
    assert ordinary.binding_plan.binding(("add",)).effective_params["delta"] == 4
    assert (
        nested.binding_plan.binding(("composite", "add")).effective_params[
            "delta"
        ]
        == 6
    )
    assert (
        loop.binding_plan.binding(("while_loop", "step")).effective_params[
            "target"
        ]
        == 3
    )

    for plan in (ordinary, nested, loop):
        assert plan.binding_plan.plugin_registry is plugins
        assert all(
            child.plugin_registry is None
            for child in _child_binding_plans(plan.binding_plan)
        )
        _assert_live_node_bindings(plan)

    workflow = loop.to_workflow_plan(workflow_id="python-binding-boundary")
    payload = json.loads(workflow.to_json())
    _assert_plain_json_tree(payload)
    assert "python_bindings" not in workflow.to_json()
    assert "plugin_registry" not in workflow.to_json()


def test_planned_stub_binding_is_hashed_and_loaded_only_when_run(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "loaded.txt"
    stub_path = tmp_path / "project" / "stubs" / "runtime_control_stub.py"
    stub_path.parent.mkdir(parents=True)
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        "def run_stub(inputs, params):\n"
        "    return {'value.out': inputs['value.in']['value'] + params['delta']}\n"
    )
    stub_path.write_text(source, encoding="utf-8")
    runtime = PipelineRuntime(
        parse_graph_config(_planned_stub_config(), project_root=tmp_path),
        registry=_registry(),
        runtime_options=RuntimeOptions(allow_planned_stub=True),
        run_dir=tmp_path / "planned",
    )

    assert not marker.exists()
    binding = runtime._plan.binding_plan.binding(("stub",))
    frame = runtime._plan.frame("stub")
    assert binding.path == ("stub",)
    assert binding.type_key == "planned.stub"
    assert binding.implementation == str(stub_path.resolve())
    assert not callable(binding.implementation)
    assert binding.effective_params["delta"] == 4
    assert binding.source.to_dict() == {
        "kind": "python_stub",
        "ref": "project/stubs/runtime_control_stub.py",
        "export": "run_stub",
    }
    assert binding.source_hash == sha256(source.encode("utf-8")).hexdigest()
    assert frame.node is None

    result = runtime.run({"value.in": 2})
    assert result.get("value.out")["value"] == 6
    assert marker.read_text(encoding="utf-8") == "loaded"


@pytest.mark.parametrize("execution", EXECUTION_MODES)
def test_result_key_semantics_and_trace_match_all_execution_modes(
    execution: str,
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the flow."),
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces an asynchronous value.",
                        provides=[PROV_SPEC("value.in")],
                        config={"value": 4},
                        result_key="value.in",
                        **{"async": "result_key"},
                    ),
                    _node_call(
                        "add",
                        "test.add",
                        "Consumes the asynchronous value.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                        config={"delta": 3},
                    ),
                    _node_call(
                        "end",
                        "test.out_end",
                        "Consumes the result.",
                        requires=[REQ_SPEC("value.out")],
                    ),
                ],
                "edges": _edge_chain("start", "seed", "add", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    result = PipelineRuntime(
        graph,
        registry=_registry(),
        runtime_options=RuntimeOptions(execution=execution, trace="full"),
        run_dir=tmp_path / execution,
    ).run()
    kinds = [line["kind"] for line in _trace_lines(result)]

    assert result.get("value.out")["value"] == 7
    assert result.get("runtime.stop_reason") == "completed"
    assert "async_result" in kinds
    assert "async_result_join" in kinds
    assert kinds[-1] == "runtime_summary"


@pytest.mark.parametrize("execution", EXECUTION_MODES)
def test_detached_failure_cleanup_and_trace_match_all_execution_modes(
    execution: str,
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the flow."),
                    _node_call(
                        "metrics",
                        "test.runtime_fail",
                        "Fails in a detached task.",
                        provides=[PROV_SPEC("value.out")],
                        config={"fail": True},
                        **{"async": "detached"},
                    ),
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces the retained output.",
                        provides=[PROV_SPEC("value.in")],
                        config={"value": 2},
                    ),
                    _node_call(
                        "end",
                        "test.in_end",
                        "Consumes the retained output.",
                        requires=[REQ_SPEC("value.in")],
                    ),
                ],
                "edges": _edge_chain("start", "metrics", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )
    result = PipelineRuntime(
        graph,
        registry=_registry(),
        runtime_options=RuntimeOptions(execution=execution, trace="full"),
        run_dir=tmp_path / execution,
    ).run()
    lines = _trace_lines(result)

    assert result.get("value.in")["value"] == 2
    assert result.get("runtime.stop_reason") == "completed"
    assert any(line["kind"] == "async_detached" for line in lines)
    assert any(
        line["kind"] == "async_detached_failed" and "boom" in line["failure"]
        for line in lines
    )
    assert lines[-1]["kind"] == "runtime_summary"


@pytest.mark.parametrize("execution", EXECUTION_MODES)
def test_python_port_semantics_and_trace_match_all_execution_modes(
    execution: str,
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "entry_mode": "async",
                "nodes": [
                    {
                        "id": "receive",
                        "type_used": "vibeflow.io",
                        "display_name": "Receive number",
                        "description": "Receives the number used by this integration workflow.",
                        "requires": [],
                        "provides": [PROV_SPEC("number")],
                        "io": {"operation": "receive", "port": "math.in"},
                    },
                    _node_call(
                        "double",
                        "integration.double",
                        "Doubles the received number.",
                        requires=[REQ_SPEC("number")],
                        provides=[PROV_SPEC("answer")],
                    ),
                    {
                        "id": "send",
                        "type_used": "vibeflow.io",
                        "display_name": "Send answer",
                        "description": "Sends the doubled answer from this integration workflow.",
                        "requires": [REQ_SPEC("answer")],
                        "provides": [],
                        "io": {"operation": "send", "port": "math.out"},
                    },
                ],
                "edges": [["receive", "double"], ["double", "send"]],
                "outputs": [REQ_SPEC("answer")],
            }
        }
    )
    registry = NodeRegistry()
    registry.register(
        "integration.double",
        _DoubleNode,
        config_schema={},
        config_defaults={},
    )
    sent: list[dict[str, object]] = []

    def receive(request: Mapping[str, object]) -> dict[str, object]:
        assert request == {"port": "math.in"}
        return {"value": 6}

    def send(request: Mapping[str, object]) -> None:
        sent.append(dict(request))

    result = PipelineRuntime(
        graph,
        registry=registry,
        runtime_options=RuntimeOptions(execution=execution, trace="full"),
        run_dir=tmp_path / execution,
        capabilities={
            "vibeflow.port": {
                "receive": receive,
                "send": send,
            }
        },
    ).run()
    kinds = [line["kind"] for line in _trace_lines(result)]

    assert result.get("answer")["value"] == 12
    assert sent == [{"port": "math.out", "value": 12}]
    assert "io_receive" in kinds
    assert "io_send" in kinds
    assert result.get("runtime.qualified_exec_order") == (
        "receive",
        "double",
        "send",
    )
    assert kinds[-1] == "runtime_summary"
