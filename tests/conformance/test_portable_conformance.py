from __future__ import annotations

from pathlib import Path
import time

import pytest

from tests.conformance.support import (
    ErrorObservation,
    PortableConformanceCase,
    PortableConformanceResult,
    run_portable_conformance,
)
from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project import NodeContract, NodeInfo, NodeRegistry
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.block_compiler import SourceRef


class _TerminalNode:
    NODE_INFO = NodeInfo(
        "fixture.terminal",
        "Terminal",
        "conformance",
        "Starts or ends a conformance workflow.",
        "1",
        "terminal",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        return {}


class _AliasNode:
    NODE_INFO = NodeInfo(
        "fixture.alias",
        "Alias values",
        "conformance",
        "Produces values for every pipeline output cardinality.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(
            DataProvider("exact", "value.exact"),
            DataProvider("optional", "value.optional"),
            DataProvider("item", "value.item"),
        )
    )

    def run_pure(self, inputs, params):
        return {"exact": 3, "optional": 4, "item": 5}


class _AddNode:
    NODE_INFO = NodeInfo(
        "fixture.add",
        "Add",
        "conformance",
        "Adds a configured delta.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(DataProvider("answer", "answer"),),
        params_schema={"delta": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"answer": inputs["number"]["value"] + params["delta"]}


class _RouteNode:
    NODE_INFO = NodeInfo(
        "fixture.route",
        "Route",
        "conformance",
        "Chooses a branch from the input sign.",
        "1",
        "decision",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(
            DataProvider("number.branch", "number"),
            DataProvider("branch.left", "branch.left"),
        ),
    )

    def run_pure(self, inputs, params):
        value = inputs["number"]["value"]
        return {"number.branch": value, "branch.left": value >= 0}


class _AsyncRouteNode:
    NODE_INFO = NodeInfo(
        "fixture.async_route",
        "Async route",
        "conformance",
        "Chooses a branch after resolving a result-key future.",
        "1",
        "decision",
    )
    CONTRACT = _RouteNode.CONTRACT

    def run_pure(self, inputs, params):
        value = inputs["number"]["value"]
        return {"number.branch": value, "branch.left": value >= 0}


class _NumericTruthRouteNode:
    NODE_INFO = NodeInfo(
        "fixture.numeric_truth_route",
        "Numeric truth route",
        "conformance",
        "Produces numeric one to verify strict portable condition equality.",
        "1",
        "decision",
    )
    CONTRACT = _RouteNode.CONTRACT

    def run_pure(self, inputs, params):
        return {
            "number.branch": inputs["number"]["value"],
            "branch.left": 1,
        }


class _LeftNode:
    NODE_INFO = NodeInfo(
        "fixture.left",
        "Left",
        "conformance",
        "Runs the true branch.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(DataProvider("left.answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        return {"left.answer": inputs["number"]["value"] + 10}


class _RightNode:
    NODE_INFO = NodeInfo(
        "fixture.right",
        "Right",
        "conformance",
        "Runs the false branch.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(DataProvider("right.answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        return {"right.answer": inputs["number"]["value"] - 10}


class _OptionalLeftNode:
    NODE_INFO = NodeInfo(
        "fixture.optional_left",
        "Optional left",
        "conformance",
        "Runs the selected optional-data left branch.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "optional_one"),),
        provides=(DataProvider("left.answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        item = inputs["number"]
        value = item["value"] if item is not None else -1000
        return {"left.answer": value + 10}


class _OptionalRightNode:
    NODE_INFO = NodeInfo(
        "fixture.optional_right",
        "Optional right",
        "conformance",
        "Runs the selected optional-data right branch.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "optional_one"),),
        provides=(DataProvider("right.answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        item = inputs["number"]
        value = item["value"] if item is not None else 1000
        return {"right.answer": value - 10}


class _LeftItemNode:
    NODE_INFO = NodeInfo(
        "fixture.left_item",
        "Left item",
        "conformance",
        "Produces the first fan-in item.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(provides=(DataProvider("left", "item"),))

    def run_pure(self, inputs, params):
        return {"left": 1}


class _RightItemNode:
    NODE_INFO = NodeInfo(
        "fixture.right_item",
        "Right item",
        "conformance",
        "Produces the second fan-in item.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(provides=(DataProvider("right", "item"),))

    def run_pure(self, inputs, params):
        return {"right": 2}


class _DoubleNode:
    NODE_INFO = NodeInfo(
        "fixture.double",
        "Double",
        "conformance",
        "Doubles a number inside a nodeset.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(DataProvider("answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        return {"answer": inputs["number"]["value"] * 2}


class _IncrementNode:
    NODE_INFO = NodeInfo(
        "fixture.increment",
        "Increment",
        "conformance",
        "Advances one bounded-loop iteration.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("loop.current", "exactly_one"),),
        provides=(DataProvider("loop.next", "loop.next"),),
    )

    def run_pure(self, inputs, params):
        return {"loop.next": inputs["loop.current"]["value"] + 1}


class _IncrementUntilNode:
    NODE_INFO = NodeInfo(
        "fixture.increment_until",
        "Increment until",
        "conformance",
        "Advances a loop and reports its stop condition.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("loop.current", "exactly_one"),),
        provides=(
            DataProvider("loop.next", "loop.next"),
            DataProvider("loop.done", "loop.done"),
        ),
        params_schema={"target": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        value = inputs["loop.current"]["value"] + 1
        return {
            "loop.next": value,
            "loop.done": value >= params["target"],
        }


class _FailNode:
    NODE_INFO = NodeInfo(
        "fixture.fail",
        "Fail",
        "conformance",
        "Raises the shared conformance error.",
        "1",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        raise RuntimeError("conformance boom")


class _DetachedAuditNode:
    NODE_INFO = NodeInfo(
        "fixture.detached_audit",
        "Detached audit",
        "conformance",
        "Completes a delayed side task before workflow cleanup returns.",
        "1",
        "process",
    )
    CONTRACT = NodeContract()

    def run_pure(self, inputs, params):
        time.sleep(0.01)
        return {}


JAVASCRIPT_SOURCE = """
export function terminal() { return {}; }
export function aliasValues() {
  return { exact: 3, optional: 4, item: 5 };
}
export function add(inputs, params) {
  return { answer: inputs.number.value + params.delta };
}
export function route(inputs) {
  const value = inputs.number.value;
  return { "number.branch": value, "branch.left": value >= 0 };
}
export async function asyncRoute(inputs) {
  await Promise.resolve();
  const value = inputs.number.value;
  return { "number.branch": value, "branch.left": value >= 0 };
}
export function numericTruthRoute(inputs) {
  return { "number.branch": inputs.number.value, "branch.left": 1 };
}
export function left(inputs) {
  return { "left.answer": inputs.number.value + 10 };
}
export function right(inputs) {
  return { "right.answer": inputs.number.value - 10 };
}
export function optionalLeft(inputs) {
  const value = inputs.number === null ? -1000 : inputs.number.value;
  return { "left.answer": value + 10 };
}
export function optionalRight(inputs) {
  const value = inputs.number === null ? 1000 : inputs.number.value;
  return { "right.answer": value - 10 };
}
export function leftItem() { return { left: 1 }; }
export function rightItem() { return { right: 2 }; }
export function double(inputs) {
  return { answer: inputs.number.value * 2 };
}
export function increment(inputs) {
  return { "loop.next": inputs["loop.current"].value + 1 };
}
export function incrementUntil(inputs, params) {
  const value = inputs["loop.current"].value + 1;
  return {
    "loop.next": value,
    "loop.done": value >= params.target,
  };
}
export function fail() {
  throw new Error("conformance boom");
}
export async function detachedAudit() {
  await new Promise(resolve => setTimeout(resolve, 10));
  return {};
}
export function unusedComposite() {
  throw new Error("composite implementation must not run");
}
""".strip()


JAVASCRIPT_EXPORTS = {
    "fixture.terminal": "terminal",
    "fixture.alias": "aliasValues",
    "fixture.add": "add",
    "fixture.route": "route",
    "fixture.async_route": "asyncRoute",
    "fixture.numeric_truth_route": "numericTruthRoute",
    "fixture.left": "left",
    "fixture.right": "right",
    "fixture.optional_left": "optionalLeft",
    "fixture.optional_right": "optionalRight",
    "fixture.left_item": "leftItem",
    "fixture.right_item": "rightItem",
    "fixture.double": "double",
    "fixture.increment": "increment",
    "fixture.increment_until": "incrementUntil",
    "fixture.fail": "fail",
    "fixture.detached_audit": "detachedAudit",
    "fixture.double_flow": "unusedComposite",
    "fixture.loop_body": "unusedComposite",
    "vibeflow.loop.while": "unusedComposite",
}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(
        "fixture.terminal",
        _TerminalNode,
        config_schema={},
        config_defaults={},
    )
    registry.register(
        "fixture.alias",
        _AliasNode,
        config_schema={},
        config_defaults={},
    )
    registry.register(
        "fixture.add",
        _AddNode,
        config_schema={"delta": {"type": "number"}},
        config_defaults={"delta": 1},
    )
    registry.register(
        "fixture.increment_until",
        _IncrementUntilNode,
        config_schema={"target": {"type": "number"}},
        config_defaults={"target": 3},
    )
    for type_key, node in (
        ("fixture.route", _RouteNode),
        ("fixture.async_route", _AsyncRouteNode),
        ("fixture.numeric_truth_route", _NumericTruthRouteNode),
        ("fixture.left", _LeftNode),
        ("fixture.right", _RightNode),
        ("fixture.optional_left", _OptionalLeftNode),
        ("fixture.optional_right", _OptionalRightNode),
        ("fixture.left_item", _LeftItemNode),
        ("fixture.right_item", _RightItemNode),
        ("fixture.double", _DoubleNode),
        ("fixture.increment", _IncrementNode),
        ("fixture.fail", _FailNode),
        ("fixture.detached_audit", _DetachedAuditNode),
    ):
        registry.register(
            type_key,
            node,
            config_schema={},
            config_defaults={},
        )
    return registry


def _requirement(
    type_key: str,
    cardinality: str = "exactly_one",
) -> dict[str, str]:
    return {
        "type": type_key,
        "cardinality": cardinality,
        "display_name": type_key,
    }


def _provider(key: str, type_key: str | None = None) -> dict[str, str]:
    return {
        "key": key,
        "type": type_key or key,
        "display_name": key,
    }


def _pipeline_input(key: str, type_key: str | None = None) -> dict[str, object]:
    return {
        "key": key,
        "type": type_key or key,
        "display_name": key,
        "required": True,
    }


def _pipeline_output(
    type_key: str,
    cardinality: str = "exactly_one",
    alias: str | None = None,
) -> dict[str, str]:
    output = {
        "type": type_key,
        "cardinality": cardinality,
        "display_name": type_key,
    }
    if alias is not None:
        output["as"] = alias
    return output


def _node(
    node_id: str,
    type_key: str,
    *,
    requires: list[dict[str, str]] | None = None,
    provides: list[dict[str, str]] | None = None,
    **extra,
) -> dict[str, object]:
    return {
        "id": node_id,
        "type_used": type_key,
        "display_name": node_id,
        "description": f"Conformance node {node_id}.",
        "requires": requires or [],
        "provides": provides or [],
        **extra,
    }


def _edge(
    source: str,
    target: str,
    *,
    when: str | None = None,
) -> dict[str, str]:
    edge = {"from": source, "to": target}
    if when is not None:
        edge["when"] = when
    return edge


def _case(
    name: str,
    document: dict[str, object],
    inputs: dict[str, object],
    *,
    port_inputs: dict[str, tuple[object, ...]] | None = None,
) -> PortableConformanceCase:
    return PortableConformanceCase(
        name=name,
        document=document,
        inputs=inputs,
        registry=_registry(),
        javascript_source=JAVASCRIPT_SOURCE,
        javascript_exports=JAVASCRIPT_EXPORTS,
        port_inputs=port_inputs or {},
    )


def _branch_document(
    *,
    async_result: bool = False,
    optional_targets: bool = False,
) -> dict[str, object]:
    route_fields: dict[str, object] = {}
    route_type = "fixture.route"
    if async_result:
        route_type = "fixture.async_route"
        route_fields = {
            "async": "result_key",
            "result_key": "branch.left",
        }
    branch_cardinality = "optional_one" if optional_targets else "exactly_one"
    left_type = "fixture.optional_left" if optional_targets else "fixture.left"
    right_type = "fixture.optional_right" if optional_targets else "fixture.right"
    return {
        "pipeline": {
            "entry_mode": "async" if async_result else "sync",
            "inputs": [_pipeline_input("number")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "route",
                    route_type,
                    requires=[_requirement("number")],
                    provides=[
                        _provider("number.branch", "number"),
                        _provider("branch.left"),
                    ],
                    **route_fields,
                ),
                _node(
                    "left",
                    left_type,
                    requires=[_requirement("number", branch_cardinality)],
                    provides=[_provider("left.answer", "answer")],
                ),
                _node(
                    "right",
                    right_type,
                    requires=[_requirement("number", branch_cardinality)],
                    provides=[_provider("right.answer", "answer")],
                ),
                _node("join", "fixture.terminal", join_policy="any_active"),
            ],
            "edges": [
                _edge("start", "route"),
                _edge("route", "left", when="branch.left == true"),
                _edge("route", "right", when="branch.left == false"),
                _edge("left", "join"),
                _edge("right", "join"),
            ],
            "outputs": [_pipeline_output("answer", alias="selected")],
        }
    }


def _input_preflight_document(
    *,
    explicit_required: bool = True,
) -> dict[str, object]:
    input_spec = _pipeline_input("number")
    if not explicit_required:
        input_spec.pop("required")
    return {
        "pipeline": {
            "inputs": [input_spec],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node("end", "fixture.terminal"),
            ],
            "edges": [_edge("start", "end")],
            "outputs": [],
        }
    }


def _unbounded_loop_document() -> dict[str, object]:
    return {
        "nodesets": [
            {
                "type_key": "fixture.loop_body",
                "display_name": "Unbounded loop body",
                "description": "One portable unbounded-loop iteration.",
                "requires": [_requirement("loop.current")],
                "provides": [_provider("loop.next")],
                "pipeline": {
                    "inputs": [_pipeline_input("loop.current")],
                    "nodes": [
                        _node("start", "fixture.terminal"),
                        _node(
                            "increment",
                            "fixture.increment",
                            requires=[_requirement("loop.current")],
                            provides=[_provider("loop.next")],
                        ),
                        _node("end", "fixture.terminal"),
                    ],
                    "edges": [
                        _edge("start", "increment"),
                        _edge("increment", "end"),
                    ],
                    "outputs": [_pipeline_output("loop.next")],
                },
            }
        ],
        "pipeline": {
            "entry_mode": "async",
            "inputs": [_pipeline_input("loop.current")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "loop",
                    "vibeflow.loop.while",
                    requires=[_requirement("loop.current")],
                    provides=[_provider("loop.final")],
                    loop={
                        "body": "fixture.loop_body",
                        "max_iterations": None,
                        "carry": [
                            {
                                "from": "loop.current",
                                "as": "loop.current",
                                "update": "loop.next",
                            }
                        ],
                        "outputs": [
                            {"from": "loop.current", "as": "loop.final"}
                        ],
                    },
                ),
            ],
            "edges": [_edge("start", "loop")],
            "outputs": [_pipeline_output("loop.final", alias="final")],
        },
    }


def _assert_success(
    result: PortableConformanceResult,
    expected_outputs: dict[str, object],
) -> None:
    result.assert_equivalent()
    assert result.python.public_outputs == expected_outputs
    assert result.python.error is None


def test_python_runtime_projects_every_output_cardinality_through_public_name(
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node("start", "fixture.terminal"),
                    _node(
                        "values",
                        "fixture.alias",
                        provides=[
                            _provider("exact", "value.exact"),
                            _provider("optional", "value.optional"),
                            _provider("item", "value.item"),
                        ],
                    ),
                    _node("end", "fixture.terminal"),
                ],
                "edges": [_edge("start", "values"), _edge("values", "end")],
                "outputs": [
                    _pipeline_output("value.exact", alias="renamed_exact"),
                    _pipeline_output(
                        "value.optional",
                        "optional_one",
                        "renamed_optional",
                    ),
                    _pipeline_output("value.item", "all", "renamed_items"),
                ],
            }
        }
    )

    result = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path,
    ).run()

    assert result.get("renamed_exact")["value"] == 3
    assert result.get("renamed_optional")["value"] == 4
    assert [item["value"] for item in result.get("renamed_items")] == [5]
    assert not result.exists("value.exact")
    assert not result.exists("value.optional")
    assert not result.exists("value.item")


def test_python_runtime_output_without_alias_keeps_type_name(
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node("start", "fixture.terminal"),
                    _node(
                        "values",
                        "fixture.alias",
                        provides=[
                            _provider("exact", "value.exact"),
                            _provider("optional", "value.optional"),
                            _provider("item", "value.item"),
                        ],
                    ),
                    _node("end", "fixture.terminal"),
                ],
                "edges": [_edge("start", "values"), _edge("values", "end")],
                "outputs": [_pipeline_output("value.exact")],
            }
        }
    )

    result = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path,
    ).run()

    assert result.get("value.exact")["value"] == 3


@pytest.mark.parametrize(
    ("inputs", "expected_message"),
    [
        ({}, "required workflow input 'number' is missing"),
        (
            {"number": 1, "unexpected": 2},
            "unknown workflow input 'unexpected'",
        ),
    ],
)
def test_python_explicit_input_contract_fails_before_any_node(
    tmp_path: Path,
    inputs: dict[str, object],
    expected_message: str,
) -> None:
    graph = parse_graph_config(_input_preflight_document())
    runtime = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path,
        runtime_options=RuntimeOptions(trace="full"),
    )

    with pytest.raises(
        PipelineRuntimeError,
        match=expected_message,
    ):
        runtime.run(inputs)

    assert runtime.trace.step_count == 0
    assert runtime.trace.qualified_node_runs == {}
    assert runtime.trace.qualified_edge_executions == {}


def test_python_any_legacy_input_keeps_entire_contract_permissive(
    tmp_path: Path,
) -> None:
    document = _input_preflight_document(explicit_required=False)
    pipeline = document["pipeline"]
    assert isinstance(pipeline, dict)
    pipeline_inputs = pipeline["inputs"]
    assert isinstance(pipeline_inputs, list)
    pipeline_inputs.append(
        {
            "key": "explicit",
            "type": "explicit",
            "display_name": "explicit",
            "required": True,
        }
    )
    graph = parse_graph_config(document)
    runtime = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path,
        runtime_options=RuntimeOptions(trace="full"),
    )

    result = runtime.run({"unexpected": 2})

    assert not result.exists("number")
    assert not result.exists("unexpected")
    assert runtime.trace.step_count == 2
    assert runtime.trace.qualified_node_runs == {
        "start": 1,
        "end": 1,
    }


@pytest.mark.parametrize(
    ("name", "inputs", "expected_error"),
    [
        (
            "required",
            {},
            ErrorObservation(
                category="input_required",
                node_path="",
                message="required workflow input 'number' is missing",
            ),
        ),
        (
            "unknown",
            {"number": 1, "unexpected": 2},
            ErrorObservation(
                category="input_unknown",
                node_path="",
                message="unknown workflow input 'unexpected'",
            ),
        ),
    ],
)
def test_portable_conformance_input_preflight_before_nodes(
    tmp_path: Path,
    name: str,
    inputs: dict[str, object],
    expected_error: ErrorObservation,
) -> None:
    result = run_portable_conformance(
        _case(
            f"conformance.input_{name}",
            _input_preflight_document(),
            inputs,
        ),
        work_dir=tmp_path,
    )

    result.assert_equivalent()
    assert result.python.error == expected_error
    assert result.python.node_runs == ()
    assert result.python.edge_runs == ()


def test_portable_conformance_linear_alias_and_optional_output(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "inputs": [_pipeline_input("number")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "add",
                    "fixture.add",
                    requires=[_requirement("number")],
                    provides=[_provider("answer")],
                    config={"delta": 3},
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [_edge("start", "add"), _edge("add", "end")],
            "outputs": [
                _pipeline_output("answer", alias="total"),
                _pipeline_output("missing", "optional_one", "note"),
            ],
        }
    }

    result = run_portable_conformance(
        _case("conformance.linear", document, {"number": 2}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"total": 5})
    assert dict(result.python.node_runs) == {"add": 1, "end": 1, "start": 1}


def test_portable_conformance_all_cardinality_and_all_join(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "left",
                    "fixture.left_item",
                    provides=[_provider("left", "item")],
                ),
                _node(
                    "right",
                    "fixture.right_item",
                    provides=[_provider("right", "item")],
                ),
                _node("join", "fixture.terminal", join_policy="all"),
            ],
            "edges": [
                _edge("start", "left"),
                _edge("start", "right"),
                _edge("left", "join"),
                _edge("right", "join"),
            ],
            "outputs": [_pipeline_output("item", "all", "values")],
        }
    }

    result = run_portable_conformance(
        _case("conformance.all_join", document, {}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"values": [1, 2]})
    assert dict(result.python.edge_runs) == {
        "left->join": 1,
        "right->join": 1,
        "start->left": 1,
        "start->right": 1,
    }


def test_portable_conformance_safe_any_ignores_unselected_data_edge(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "direct",
                    "fixture.left_item",
                    provides=[_provider("left", "item")],
                ),
                _node(
                    "conditional",
                    "fixture.right_item",
                    provides=[_provider("right", "item")],
                ),
                _node(
                    "join",
                    "fixture.terminal",
                    requires=[_requirement("item")],
                    join_policy="safe_any",
                ),
            ],
            "edges": [
                _edge("start", "direct"),
                _edge("start", "conditional"),
                _edge("direct", "join"),
                _edge(
                    "conditional",
                    "join",
                    when='right == "never"',
                ),
            ],
            "outputs": [],
        }
    }

    result = run_portable_conformance(
        _case(
            "conformance.safe_any_mixed_data_edges",
            document,
            {},
        ),
        work_dir=tmp_path,
    )

    _assert_success(result, {})
    assert dict(result.python.node_runs)["join"] == 1
    assert dict(result.python.edge_runs) == {
        "direct->join": 1,
        "start->conditional": 1,
        "start->direct": 1,
    }


@pytest.mark.parametrize(
    ("value", "expected", "taken", "skipped"),
    [
        (5, 15, "left", "right"),
        (-5, -15, "right", "left"),
    ],
)
def test_portable_conformance_condition_branch_and_any_active_join(
    tmp_path: Path,
    value: int,
    expected: int,
    taken: str,
    skipped: str,
) -> None:
    document = _branch_document()

    result = run_portable_conformance(
        _case(f"conformance.branch.{taken}", document, {"number": value}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"selected": expected})
    node_runs = dict(result.python.node_runs)
    assert node_runs[taken] == 1
    assert skipped not in node_runs


def test_portable_conditions_do_not_coerce_number_one_to_boolean_true(
    tmp_path: Path,
) -> None:
    document = _branch_document(optional_targets=True)
    route = document["pipeline"]["nodes"][1]
    assert isinstance(route, dict)
    route["type_used"] = "fixture.numeric_truth_route"

    result = run_portable_conformance(
        _case(
            "conformance.condition_strict_boolean",
            document,
            {"number": 5},
        ),
        work_dir=tmp_path,
    )

    result.assert_equivalent()
    assert result.python.error is not None
    assert result.python.error.category == "output_cardinality"
    assert "left" not in dict(result.python.node_runs)
    assert "right" not in dict(result.python.node_runs)


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_python_result_key_async_node_rechecks_conditional_routes(
    tmp_path: Path,
    execution: str,
) -> None:
    graph = parse_graph_config(
        _branch_document(async_result=True, optional_targets=True)
    )

    result = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path / execution,
        runtime_options=RuntimeOptions(execution=execution, trace="full"),
    ).run({"number": 5})

    assert result.get("selected")["value"] == 15


def test_portable_conformance_result_key_async_conditional_route(
    tmp_path: Path,
) -> None:
    result = run_portable_conformance(
        _case(
            "conformance.async_condition",
            _branch_document(async_result=True, optional_targets=True),
            {"number": 5},
        ),
        work_dir=tmp_path,
    )

    _assert_success(result, {"selected": 15})
    node_runs = dict(result.python.node_runs)
    assert node_runs["route"] == 1
    assert node_runs["left"] == 1
    assert "right" not in node_runs
    assert result.python.task_events == (
        ("async_result", "route"),
        ("async_result_join", "route"),
    )
    root_block = next(
        block
        for block in result.portable_plan["blocks"]
        if block["id"] == "block:/"
    )
    assert root_block["tasks"] == [
        {
            "id": "block:/:task:route",
            "node_id": "route",
            "schedule": "deferred",
            "executor": "thread",
            "result_key": "branch.left",
        }
    ]


def test_portable_conformance_detached_task_is_settled_before_return(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "entry_mode": "async",
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "audit",
                    "fixture.detached_audit",
                    **{"async": "detached"},
                ),
                _node(
                    "value",
                    "fixture.left_item",
                    provides=[_provider("left", "item")],
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [
                _edge("start", "audit"),
                _edge("start", "value"),
                _edge("value", "end"),
            ],
            "outputs": [_pipeline_output("item", alias="value")],
        }
    }

    result = run_portable_conformance(
        _case("conformance.detached", document, {}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"value": 1})
    assert result.python.task_events == (
        ("async_detached", "audit"),
        ("async_detached_done", "audit"),
    )
    root_block = next(
        block
        for block in result.portable_plan["blocks"]
        if block["id"] == "block:/"
    )
    assert root_block["tasks"] == [
        {
            "id": "block:/:task:audit",
            "node_id": "audit",
            "schedule": "detached",
            "executor": "thread",
        }
    ]


def test_portable_conformance_port_receive_transform_and_send(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "entry_mode": "async",
            "nodes": [
                _node(
                    "receive",
                    "vibeflow.io",
                    provides=[_provider("number")],
                    io={"operation": "receive", "port": "math.in"},
                ),
                _node(
                    "add",
                    "fixture.add",
                    requires=[_requirement("number")],
                    provides=[_provider("answer")],
                    config={"delta": 4},
                ),
                _node(
                    "send",
                    "vibeflow.io",
                    requires=[_requirement("answer")],
                    io={"operation": "send", "port": "math.out"},
                ),
            ],
            "edges": [
                _edge("receive", "add"),
                _edge("add", "send"),
            ],
            "outputs": [_pipeline_output("answer", alias="total")],
        }
    }

    result = run_portable_conformance(
        _case(
            "conformance.port",
            document,
            {},
            port_inputs={"math.in": (6,)},
        ),
        work_dir=tmp_path,
    )

    _assert_success(result, {"total": 10})
    assert result.python.port_sends == (
        {"port": "math.out", "value": 10},
    )
    root_block = next(
        block
        for block in result.portable_plan["blocks"]
        if block["id"] == "block:/"
    )
    nodes = {node["id"]: node for node in root_block["nodes"]}
    assert {
        key: (
            nodes[key]["completion"],
            nodes[key]["schedule"],
            nodes[key]["executor"],
        )
        for key in ("receive", "send")
    } == {
        "receive": ("suspend", "inline", "event_loop"),
        "send": ("immediate", "inline", "current"),
    }
    assert root_block["tasks"] == []


def test_portable_conformance_nested_nodeset(tmp_path: Path) -> None:
    document = {
        "nodesets": [
            {
                "type_key": "fixture.double_flow",
                "display_name": "Double flow",
                "description": "A nested conformance flow.",
                "requires": [_requirement("number")],
                "provides": [_provider("answer")],
                "pipeline": {
                    "inputs": [_pipeline_input("number")],
                    "nodes": [
                        _node("start", "fixture.terminal"),
                        _node(
                            "double",
                            "fixture.double",
                            requires=[_requirement("number")],
                            provides=[_provider("answer")],
                        ),
                        _node("end", "fixture.terminal"),
                    ],
                    "edges": [
                        _edge("start", "double"),
                        _edge("double", "end"),
                    ],
                    "outputs": [
                        _pipeline_output("answer", alias="inner_answer")
                    ],
                },
            }
        ],
        "pipeline": {
            "inputs": [_pipeline_input("number")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "composite",
                    "fixture.double_flow",
                    requires=[_requirement("number")],
                    provides=[_provider("answer")],
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [
                _edge("start", "composite"),
                _edge("composite", "end"),
            ],
            "outputs": [_pipeline_output("answer", alias="doubled")],
        },
    }

    result = run_portable_conformance(
        _case("conformance.nodeset", document, {"number": 6}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"doubled": 12})
    assert dict(result.python.node_runs)["composite.double"] == 1


def test_portable_conformance_nested_nodeset_all_output(
    tmp_path: Path,
) -> None:
    document = {
        "nodesets": [
            {
                "type_key": "fixture.items_flow",
                "display_name": "Items flow",
                "description": "Exports an all-cardinality body result.",
                "requires": [],
                "provides": [_provider("items", "item")],
                "pipeline": {
                    "nodes": [
                        _node("start", "fixture.terminal"),
                        _node(
                            "left",
                            "fixture.left_item",
                            provides=[_provider("left", "item")],
                        ),
                        _node(
                            "right",
                            "fixture.right_item",
                            provides=[_provider("right", "item")],
                        ),
                        _node("join", "fixture.terminal", join_policy="all"),
                    ],
                    "edges": [
                        _edge("start", "left"),
                        _edge("start", "right"),
                        _edge("left", "join"),
                        _edge("right", "join"),
                    ],
                    "outputs": [
                        _pipeline_output("item", "all", "inner_items")
                    ],
                },
            }
        ],
        "pipeline": {
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "composite",
                    "fixture.items_flow",
                    provides=[_provider("items", "item")],
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [
                _edge("start", "composite"),
                _edge("composite", "end"),
            ],
            "outputs": [_pipeline_output("item", alias="items")],
        },
    }
    exports = {
        **JAVASCRIPT_EXPORTS,
        "fixture.items_flow": "unusedComposite",
    }
    case = PortableConformanceCase(
        name="conformance.nodeset_all",
        document=document,
        inputs={},
        registry=_registry(),
        javascript_source=JAVASCRIPT_SOURCE,
        javascript_exports=exports,
    )

    result = run_portable_conformance(case, work_dir=tmp_path)

    _assert_success(result, {"items": [1, 2]})
    assert dict(result.python.node_runs)["composite.join"] == 1


def test_portable_plan_canonically_preserves_unbounded_loop_sink(
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(_unbounded_loop_document())
    runtime = PipelineRuntime(
        graph,
        registry=_registry(),
        run_dir=tmp_path,
    )
    sources = {
        type_key: SourceRef(
            kind="javascript",
            ref="./nodes.mjs",
            export=export_name,
        )
        for type_key, export_name in JAVASCRIPT_EXPORTS.items()
    }

    first = runtime._plan.to_workflow_plan(
        workflow_id="conformance.unbounded_loop",
        source_by_type=sources,
    )
    second = runtime._plan.to_workflow_plan(
        workflow_id="conformance.unbounded_loop",
        source_by_type=sources,
    )

    assert first.to_json() == second.to_json()
    loop_blocks = [
        block
        for block in first.to_dict()["blocks"]
        if block["kind"] == "loop"
    ]
    assert len(loop_blocks) == 1
    assert loop_blocks[0]["loop"] == {
        "body": "fixture.loop_body",
        "max_iterations": None,
        "carry": [
            {
                "from": "loop.current",
                "as": "loop.current",
                "update": "loop.next",
            }
        ],
        "collect": [],
        "outputs": [
            {"from": "loop.current", "as": "loop.final"}
        ],
    }


def test_portable_conformance_bounded_loop(tmp_path: Path) -> None:
    document = {
        "nodesets": [
            {
                "type_key": "fixture.loop_body",
                "display_name": "Loop body",
                "description": "One conformance loop iteration.",
                "requires": [_requirement("loop.current")],
                "provides": [_provider("loop.next")],
                "pipeline": {
                    "inputs": [_pipeline_input("loop.current")],
                    "nodes": [
                        _node("start", "fixture.terminal"),
                        _node(
                            "increment",
                            "fixture.increment",
                            requires=[_requirement("loop.current")],
                            provides=[_provider("loop.next")],
                        ),
                        _node("end", "fixture.terminal"),
                    ],
                    "edges": [
                        _edge("start", "increment"),
                        _edge("increment", "end"),
                    ],
                    "outputs": [_pipeline_output("loop.next")],
                },
            }
        ],
        "pipeline": {
            "inputs": [_pipeline_input("loop.current")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "loop",
                    "vibeflow.loop.while",
                    requires=[_requirement("loop.current")],
                    provides=[_provider("loop.final")],
                    loop={
                        "body": "fixture.loop_body",
                        "max_iterations": 5,
                        "stop_after": 3,
                        "carry": [
                            {
                                "from": "loop.current",
                                "as": "loop.current",
                                "update": "loop.next",
                            }
                        ],
                        "outputs": [
                            {"from": "loop.current", "as": "loop.final"}
                        ],
                    },
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [_edge("start", "loop"), _edge("loop", "end")],
            "outputs": [_pipeline_output("loop.final", alias="final")],
        },
    }

    result = run_portable_conformance(
        _case("conformance.loop", document, {"loop.current": 4}),
        work_dir=tmp_path,
    )

    _assert_success(result, {"final": 7})
    node_runs = dict(result.python.node_runs)
    assert node_runs["loop.iter_0.increment"] == 1
    assert node_runs["loop.iter_2.increment"] == 1


def test_portable_conformance_stop_when_loop_with_carry_and_collect(
    tmp_path: Path,
) -> None:
    document = {
        "nodesets": [
            {
                "type_key": "fixture.loop_body",
                "display_name": "Conditional loop body",
                "description": "One stop-when conformance iteration.",
                "requires": [_requirement("loop.current")],
                "provides": [
                    _provider("loop.next"),
                    _provider("loop.done"),
                ],
                "pipeline": {
                    "inputs": [_pipeline_input("loop.current")],
                    "nodes": [
                        _node("start", "fixture.terminal"),
                        _node(
                            "increment",
                            "fixture.increment_until",
                            requires=[_requirement("loop.current")],
                            provides=[
                                _provider("loop.next"),
                                _provider("loop.done"),
                            ],
                            config={"target": 3},
                        ),
                        _node("end", "fixture.terminal"),
                    ],
                    "edges": [
                        _edge("start", "increment"),
                        _edge("increment", "end"),
                    ],
                    "outputs": [
                        _pipeline_output("loop.next", alias="next_value"),
                        _pipeline_output("loop.done", alias="done_value"),
                    ],
                },
            }
        ],
        "pipeline": {
            "inputs": [_pipeline_input("loop.current")],
            "nodes": [
                _node("start", "fixture.terminal"),
                _node(
                    "loop",
                    "vibeflow.loop.while",
                    requires=[_requirement("loop.current")],
                    provides=[
                        _provider("loop.final"),
                        _provider("loop.history"),
                        _provider("loop.iterations"),
                    ],
                    loop={
                        "body": "fixture.loop_body",
                        "max_iterations": 5,
                        "stop_when": {
                            "from": "loop.done",
                            "equals": True,
                        },
                        "carry": [
                            {
                                "from": "loop.current",
                                "as": "loop.current",
                                "update": "loop.next",
                            }
                        ],
                        "collect": [
                            {
                                "from": "loop.next",
                                "as": "loop.history",
                            }
                        ],
                        "outputs": [
                            {"from": "loop.current", "as": "loop.final"},
                            {"from": "loop.history", "as": "loop.history"},
                            {
                                "from": "loop.iterations",
                                "as": "loop.iterations",
                            },
                        ],
                    },
                ),
                _node("end", "fixture.terminal"),
            ],
            "edges": [_edge("start", "loop"), _edge("loop", "end")],
            "outputs": [
                _pipeline_output("loop.final", alias="final"),
                _pipeline_output("loop.history", alias="history"),
                _pipeline_output("loop.iterations", alias="iterations"),
            ],
        },
    }

    result = run_portable_conformance(
        _case(
            "conformance.stop_when_loop",
            document,
            {"loop.current": 0},
        ),
        work_dir=tmp_path,
    )

    _assert_success(
        result,
        {
            "final": 3,
            "history": [1, 2, 3],
            "iterations": 3,
        },
    )
    loop_blocks = [
        block
        for block in result.portable_plan["blocks"]
        if block["kind"] == "loop"
    ]
    assert len(loop_blocks) == 1
    loop_payload = loop_blocks[0]["loop"]
    assert "stop_after" not in loop_payload
    assert loop_payload["stop_when"] == {
        "key": "loop.done",
        "operator": "==",
        "literal": True,
    }


def test_portable_conformance_normalizes_node_failure(
    tmp_path: Path,
) -> None:
    document = {
        "pipeline": {
            "nodes": [
                _node("start", "fixture.terminal"),
                _node("fail", "fixture.fail"),
                _node("end", "fixture.terminal"),
            ],
            "edges": [_edge("start", "fail"), _edge("fail", "end")],
            "outputs": [],
        }
    }

    result = run_portable_conformance(
        _case("conformance.error", document, {}),
        work_dir=tmp_path,
    )

    result.assert_equivalent()
    assert result.python.error == ErrorObservation(
        category="node_failed",
        node_path="fail",
        message="conformance boom",
    )
