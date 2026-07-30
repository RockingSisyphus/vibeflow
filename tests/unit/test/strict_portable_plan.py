from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from vibeflow.compiler import GraphCompiler
from vibeflow.data_contract import DataProvider, DataRequirement
from vibeflow.graph_config import parse_graph_config
from vibeflow.node import NodeContract, NodeInfo
from vibeflow.portable import (
    PipelineInputSpec,
    PipelineOutputSpec,
    PortablePlanError,
    SourceRef,
    build_workflow_plan,
    normalize_condition,
)
from vibeflow.registry import NodeRegistry
from vibeflow.runtime.planning import build_execution_plan


class _TerminalNode:
    NODE_INFO = NodeInfo("test.terminal", "Terminal", "test", "Starts or ends a flow.", "1", "terminal")
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        return {}


class _StepNode:
    NODE_INFO = NodeInfo("test.step", "Step", "test", "Updates a loop value.", "1", "process")
    CONTRACT = NodeContract(
        requires=(DataRequirement("value.current", "exactly_one"),),
        provides=(DataProvider("value.next", "value.next"), DataProvider("loop.done", "loop.done")),
    )

    def run_pure(self, inputs, params):
        return {"value.next": 1, "loop.done": True}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("test.terminal", _TerminalNode, config_schema={}, config_defaults={})
    registry.register(
        "test.step",
        _StepNode,
        config_schema={"delta": {"type": "number"}},
        config_defaults={"delta": 1},
    )
    return registry


def _input(key: str, data_type: str, *, required: bool | None = None) -> dict[str, object]:
    value: dict[str, object] = {"key": key, "type": data_type, "display_name": key}
    if required is not None:
        value["required"] = required
    return value


def _output(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type}


def _requirement(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type}


def _provider(key: str, data_type: str) -> dict[str, str]:
    return {"key": key, "type": data_type, "display_name": key}


def _loop_graph():
    return parse_graph_config(
        {
            "nodesets": [
                {
                    "type_key": "loop.step",
                    "display_name": "Loop Step",
                    "description": "One bounded iteration.",
                    "requires": [_requirement("value.current")],
                    "provides": [
                        _provider("value.next", "value.next"),
                        _provider("loop.done", "loop.done"),
                    ],
                    "pipeline": {
                        "inputs": [_input("value.current", "value.current")],
                        "nodes": [
                            {"id": "start", "type_used": "test.terminal"},
                            {
                                "id": "step",
                                "type_used": "test.step",
                                "requires": [_requirement("value.current")],
                                "provides": [
                                    _provider("value.next", "value.next"),
                                    _provider("loop.done", "loop.done"),
                                ],
                                "config": {"delta": 2},
                            },
                            {"id": "end", "type_used": "test.terminal"},
                        ],
                        "edges": [["start", "step"], ["step", "end"]],
                        "outputs": [_output("value.next"), _output("loop.done")],
                    },
                }
            ],
            "pipeline": {
                "inputs": [_input("value.current", "value.current")],
                "nodes": [
                    {"id": "start", "type_used": "test.terminal"},
                    {
                        "id": "repeat",
                        "type_used": "vibeflow.loop.while",
                        "requires": [_requirement("value.current")],
                        "provides": [_provider("value.final", "value.final")],
                        "node_configs": {"step": {"delta": 7}},
                        "loop": {
                            "body": "loop.step",
                            "max_iterations": 9,
                            "stop_when": {"from": "loop.done", "equals": True},
                            "carry": [
                                {"from": "value.current", "as": "value.current", "update": "value.next"}
                            ],
                            "collect": [{"from": "value.next", "as": "value.history"}],
                            "outputs": [{"from": "value.next", "as": "value.final"}],
                        },
                    },
                    {"id": "end", "type_used": "test.terminal"},
                ],
                "edges": [["start", "repeat"], ["repeat", "end"]],
                "outputs": [_output("value.final")],
                "max_steps": 25,
            },
        }
    )


def test_condition_normalization_matches_the_current_boolean_and_string_grammar() -> None:
    assert normalize_condition(" flow.route == 'again' ").to_dict() == {
        "key": "flow.route",
        "operator": "==",
        "literal": "again",
    }
    assert normalize_condition('loop.done != false').literal is False
    assert normalize_condition('flow.route == "a\\nb"').literal == "a\\nb"
    assert normalize_condition("") is None

    with pytest.raises(PortablePlanError, match="quoted string"):
        normalize_condition("flow.route == again")
    with pytest.raises(PortablePlanError, match="exactly one"):
        normalize_condition("flow.route == 'a' != 'b'")


def test_execution_plan_adapter_is_frozen_serializable_and_preserves_nested_loop_semantics() -> None:
    graph = _loop_graph()
    registry = _registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    execution_plan = build_execution_plan(graph, compiled, registry=registry)

    plan = execution_plan.to_workflow_plan(
        workflow_id="portable-loop",
        source_by_type={"test.step": SourceRef(kind="typescript", ref="nodes/step.ts", export="run")},
        pipeline_inputs=(PipelineInputSpec("value.current", "value.current", required=True),),
        pipeline_outputs=(PipelineOutputSpec("value.final", "exactly_one", "final"),),
    )

    assert plan.entry_block == "block:/"
    assert plan.inputs[0].required is True
    assert plan.outputs[0].as_key == "final"
    assert [block.kind for block in plan.blocks] == ["workflow", "loop"]

    root = plan.block(plan.entry_block)
    repeat = root.node("repeat")
    assert repeat.child_block == "block:/repeat"
    assert repeat.is_loop
    assert repeat.config_overrides.to_value() == {"step": {"delta": 7}}

    body = plan.block(repeat.child_block)
    assert body.loop is not None
    assert body.loop.max_iterations == 9
    assert body.loop.stop_when is not None
    assert body.loop.stop_when.to_dict() == {"key": "loop.done", "operator": "==", "literal": True}
    assert body.loop.carry[0].to_dict() == {
        "from": "value.current",
        "as": "value.current",
        "update": "value.next",
    }
    assert body.node("step").params.to_value()["delta"] == 7
    assert body.node("step").implementation == SourceRef(
        kind="typescript",
        ref="nodes/step.ts",
        export="run",
    )

    payload = plan.to_dict()
    assert json.loads(plan.to_json()) == payload
    assert not _contains_python_binding(payload)
    with pytest.raises(FrozenInstanceError):
        plan.max_steps = 1


def test_graph_adapter_normalizes_routes_and_marks_legacy_input_requiredness_unknown() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [_input("flow.route", "flow.route")],
                "nodes": [
                    {"id": "route", "type_used": "test.route"},
                    {"id": "end", "type_used": "test.end"},
                ],
                "edges": [{"from": "route", "to": "end", "when": "flow.route != 'skip'"}],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)

    plan = build_workflow_plan(
        graph,
        compiled,
        params_by_path={("route",): {"configured": True}},
    )
    route = plan.block(plan.entry_block).routes[0]

    assert plan.inputs[0].required is None
    assert route.condition is not None
    assert route.condition.to_dict() == {
        "key": "flow.route",
        "operator": "!=",
        "literal": "skip",
    }
    assert route.schedule and route.transfer and route.explicit
    assert plan.block(plan.entry_block).node("route").params.to_value() == {
        "configured": True
    }


def test_adapter_rejects_non_json_python_values_in_effective_params() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {
                        "id": "step",
                        "type_used": "test.step",
                        "config": {"delta": Path("not-json")},
                    }
                ]
            }
        }
    )
    compiled = GraphCompiler().compile(graph)

    with pytest.raises(PortablePlanError, match="non-portable value of type PosixPath"):
        build_workflow_plan(graph, compiled)


def _contains_python_binding(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_python_binding(key) or _contains_python_binding(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_python_binding(item) for item in value)
    return isinstance(value, type) or callable(value)
