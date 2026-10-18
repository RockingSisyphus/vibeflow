from __future__ import annotations

import time
from typing import Mapping

from vibeflow.core.flow import GraphConfig, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.planned import (
    PLANNED_BEHAVIOR_PYTHON_STUB,
    effective_planned_behavior,
)
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError


def condition_matches(expression: str, values: Mapping[str, object]) -> bool:
    for token, negate in (("==", False), ("!=", True)):
        if token not in expression:
            continue
        left, right = (part.strip() for part in expression.split(token, 1))
        if not left or not right:
            raise PipelineRuntimeError(f"invalid edge condition: {expression}")
        matches = _portable_literal_equal(
            values.get(left),
            _literal_value(right),
        )
        return not matches if negate else matches
    raise PipelineRuntimeError(f"unsupported edge condition: {expression}")


def has_planned(graph: GraphConfig) -> bool:
    return bool(planned_items(graph))


def planned_items(graph: GraphConfig, *, prefix: str = "") -> tuple[dict[str, object], ...]:
    """Inventory declarations once, including unused definitions."""
    items: list[dict[str, object]] = []
    seen_graphs: set[int] = set()
    seen_definitions: set[int] = set()
    active_nodes: set[int] = set()

    def add(label, object_type, behavior):
        items.append({"id": label, "object_type": object_type,
                      "behavior": behavior.kind, "stub_module": behavior.stub_module})

    def node(spec, current, label):
        if id(spec) in active_nodes:
            return
        active_nodes.add(id(spec))
        try:
            if spec.status == STATUS_PLANNED:
                add(label, "node", effective_planned_behavior(spec, current.nodesets.get(spec.type_used)))
        finally:
            active_nodes.remove(id(spec))

    def visit(current, path):
        if id(current) in seen_graphs:
            return
        seen_graphs.add(id(current))
        for spec in current.nodes:
            node(spec, current, f"{path}{spec.id}")
        for name, definition in current.nodesets.items():
            if id(definition) in seen_definitions:
                continue
            seen_definitions.add(id(definition))
            label = f"{path}nodeset.{name}"
            if definition.status == STATUS_PLANNED:
                add(label, "nodeset", definition.planned_behavior)
            else:
                visit(definition.graph, f"{label}.")

    visit(graph, prefix)
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


def _portable_literal_equal(left: object, right: object) -> bool:
    """Match JSON literals without Python's bool/int equality coercion."""

    return type(left) is type(right) and left == right


__all__ = [
    "all_planned_are_python_stub",
    "condition_matches",
    "elapsed_ms",
    "has_planned",
    "planned_items",
    "referenced_nodeset_names",
]
