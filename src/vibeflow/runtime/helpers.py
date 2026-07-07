from __future__ import annotations

import operator
import time
from typing import Mapping

from vibeflow.graph_config import GraphConfig, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.graph_config.planned_behavior import PLANNED_BEHAVIOR_PYTHON_STUB, effective_planned_behavior
from vibeflow.runtime.errors import PipelineRuntimeError


def condition_matches(expression: str, values: Mapping[str, object]) -> bool:
    for token, op in (("==", operator.eq), ("!=", operator.ne)):
        if token not in expression:
            continue
        left, right = (part.strip() for part in expression.split(token, 1))
        if not left or not right:
            raise PipelineRuntimeError(f"invalid edge condition: {expression}")
        return bool(op(values.get(left), _literal_value(right)))
    raise PipelineRuntimeError(f"unsupported edge condition: {expression}")


def has_planned(graph: GraphConfig, *, visited_nodesets: set[str] | None = None) -> bool:
    if visited_nodesets is None:
        visited_nodesets = set()
    if any(node.status == STATUS_PLANNED for node in graph.nodes):
        return True
    for nodeset in graph.nodesets.values():
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        if nodeset.status == STATUS_PLANNED or has_planned(nodeset.graph, visited_nodesets=visited_nodesets):
            return True
    return False


def planned_items(graph: GraphConfig, *, prefix: str = "", visited_nodesets: set[str] | None = None) -> tuple[dict[str, object], ...]:
    if visited_nodesets is None:
        visited_nodesets = set()
    items: list[dict[str, object]] = []
    for node in graph.nodes:
        nodeset = graph.nodesets.get(node.type_used)
        if node.status == STATUS_PLANNED:
            behavior = effective_planned_behavior(node, nodeset)
            items.append(
                {
                    "id": f"{prefix}{node.id}",
                    "object_type": "node",
                    "behavior": behavior.kind,
                    "stub_module": behavior.stub_module,
                }
            )
    for name, nodeset in graph.nodesets.items():
        if name in visited_nodesets:
            continue
        visited_nodesets.add(name)
        full_name = f"{prefix}nodeset.{name}"
        if nodeset.status == STATUS_PLANNED:
            behavior = nodeset.planned_behavior
            items.append(
                {
                    "id": full_name,
                    "object_type": "nodeset",
                    "behavior": behavior.kind,
                    "stub_module": behavior.stub_module,
                }
            )
            continue
        for node in nodeset.graph.nodes:
            child_nodeset = nodeset.graph.nodesets.get(node.type_used)
            if node.status == STATUS_PLANNED:
                behavior = effective_planned_behavior(node, child_nodeset)
                items.append(
                    {
                        "id": f"{full_name}.{node.id}",
                        "object_type": "node",
                        "behavior": behavior.kind,
                        "stub_module": behavior.stub_module,
                    }
                )
    return tuple(items)


def all_planned_are_python_stub(graph: GraphConfig) -> bool:
    items = planned_items(graph)
    return bool(items) and all(item.get("behavior") == PLANNED_BEHAVIOR_PYTHON_STUB for item in items)


def referenced_nodeset_names(graph: GraphConfig) -> tuple[str, ...]:
    refs: list[str] = []
    for node in graph.nodes:
        if node.type_used in graph.nodesets:
            refs.append(node.type_used)
        elif node.type_used in LOOP_NODE_TYPES and node.loop.body:
            refs.append(node.loop.body)
    return tuple(sorted(set(refs)))


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _literal_value(value: str) -> object:
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
