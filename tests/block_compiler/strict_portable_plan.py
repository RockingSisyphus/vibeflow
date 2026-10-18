from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from vibeflow.targets.python.project.compiler import GraphCompiler
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.block_compiler import (
    PipelineInputSpec,
    PipelineOutputSpec,
    PortablePlanError,
    SourceRef,
    normalize_condition,
)
from vibeflow.targets.python.project.registry import NodeRegistry
from tests.fixtures.support.declarations import native_registry
from vibeflow.targets.python.runtime.planning import build_execution_plan
from vibeflow.targets.python.runtime.support.portable_adapter import build_workflow_plan


_TerminalNode_DECLARATION = NodeDescriptor(
    'test.terminal', 'Terminal', 'Starts or ends a flow.', '1', 'terminal',
    contract=NodeContractDescriptor(params_schema={}, params_defaults={}),
    rulesets=(),
)


class _TerminalNode:

    def run_pure(self, inputs, params):
        return {}


_StepNode_DECLARATION = NodeDescriptor(
    'test.step', 'Step', 'Updates a loop value.', '1', 'process',
    contract=NodeContractDescriptor(requires=(DataRequirement('value.current', 'exactly_one', display_name='value.current'),), provides=(DataProvider('value.next', 'value.next', display_name='value.next'), DataProvider('loop.done', 'loop.done', display_name='loop.done')), params_schema={'delta': {'type': 'number'}}, params_defaults={'delta': 1}, input_semantics={'value.current': ('Conformance input value.current.',)}, output_semantics={'value.next': ('Conformance output value.next.',), 'loop.done': ('Conformance output loop.done.',)}),
    rulesets=('vibeflow.process',),
)


class _StepNode:

    def run_pure(self, inputs, params):
        return {"value.next": 1, "loop.done": True}


_GlobalStateNode_DECLARATION = NodeDescriptor(
    'test.global_state', 'Global State', 'Changes audited ambient state.', '1', 'global_state',
    contract=NodeContractDescriptor(params_schema={}, params_defaults={}),
    rulesets=('vibeflow.global_state',),
)


class _GlobalStateNode:

    def run_pure(self, inputs, params):
        return {}


def _registry() -> NodeRegistry:
    registry = native_registry()
    registry.register(_TerminalNode_DECLARATION, _TerminalNode)
    registry.register(_StepNode_DECLARATION, _StepNode)
    registry.register(_GlobalStateNode_DECLARATION, _GlobalStateNode)
    return registry


def _input(key: str, data_type: str, *, required: bool = True) -> dict[str, object]:
    value: dict[str, object] = {"key": key, "type": data_type, "display_name": key}
    value["required"] = required
    return value


def _output(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type}


def _requirement(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type}


def _provider(key: str, data_type: str) -> dict[str, str]:
    return {"key": key, "type": data_type, "display_name": key}


def _node(node_id: str, type_used: str, **fields) -> dict[str, object]:
    return {
        "id": node_id,
        "type_used": type_used,
        "display_name": node_id.replace("_", " ").title(),
        "description": f"Portable-plan fixture instance {node_id}.",
        **fields,
    }


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
                            _node("start", "test.terminal"),
                            _node("step", "test.step", config={"delta": 2}),
                            _node("end", "test.terminal"),
                        ],
                        "edges": [["start", "step"], ["step", "end"]],
                        "outputs": [_output("value.next"), _output("loop.done")],
                    },
                }
            ],
            "pipeline": {
                "inputs": [_input("value.current", "value.current")],
                "nodes": [
                    _node("start", "test.terminal"),
                    _node(
                        "repeat",
                        "vibeflow.loop.while",
                        requires=[_requirement("value.current")],
                        provides=[_provider("value.final", "value.final")],
                        node_configs={"step": {"delta": 7}},
                        loop={
                            "body": "loop.step",
                            "max_iterations": 9,
                            "stop_when": {"from": "loop.done", "equals": True},
                            "carry": [
                                {"from": "value.current", "as": "value.current", "update": "value.next"}
                            ],
                            "collect": [{"from": "value.next", "as": "value.history"}],
                            "outputs": [{"from": "value.next", "as": "value.final"}],
                        },
                    ),
                    _node("end", "test.terminal"),
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


def test_python_execution_plan_adapter_preserves_global_state_and_locks() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "execution_lock": {"key": "trainer"},
                "nodes": [
                    _node("start", "test.terminal"),
                    _node("state", "test.global_state", execution_lock={"key": "trainer"}),
                    _node("end", "test.terminal"),
                ],
                "edges": [["start", "state"], ["state", "end"]],
            }
        }
    )
    registry = _registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    execution_plan = build_execution_plan(
        graph,
        compiled,
        registry=registry,
    )

    plan = execution_plan.to_workflow_plan()
    root = plan.block(plan.entry_block)
    state = root.node("state")

    assert plan.abi_version == "vibeflow.workflow.v8"
    assert plan.contains_global_state is True
    assert "root_exclusive" not in plan.to_dict()
    assert plan.execution_lock.to_dict() == {
        "key": "trainer",
        "scope": "root",
    }
    assert root.contains_global_state is True
    assert "root_exclusive" not in root.to_dict()
    assert state.effect_scope == "global_state"
    assert "runtime_dispatch" not in state.to_dict()
    assert state.contains_global_state is True
    assert state.execution_lock.to_dict() == {
        "key": "trainer",
        "scope": "node",
    }


def test_graph_adapter_normalizes_routes_and_preserves_required_inputs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [_input("flow.route", "flow.route")],
                "nodes": [
                    _node("route", "test.route"),
                    _node("end", "test.end"),
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

    assert plan.inputs[0].required is True
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


def test_portable_input_sidecar_cannot_change_required_contract() -> None:
    graph = _loop_graph()
    registry = _registry()
    compiled = GraphCompiler().compile(graph, registry=registry)
    execution = build_execution_plan(graph, compiled, registry=registry)
    with pytest.raises(PortablePlanError, match="key/type/required order"):
        execution.to_workflow_plan(pipeline_inputs=(
            PipelineInputSpec("value.current", "value.current", required=False),
        ))


def test_adapter_rejects_non_json_python_values_in_effective_params() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node("step", "test.step", config={"delta": Path("not-json")})
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
