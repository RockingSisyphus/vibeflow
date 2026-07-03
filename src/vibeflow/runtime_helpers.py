from __future__ import annotations

import operator
import time
from typing import Mapping

from .graph_config import GraphConfig, STATUS_PLANNED
from .planned_behavior import PLANNED_BEHAVIOR_PYTHON_STUB, effective_planned_behavior
from .runtime_errors import PipelineRuntimeError


def condition_matches(expression: str, values: Mapping[str, object]) -> bool:
    for token, op in (("==", operator.eq), ("!=", operator.ne)):
        if token not in expression:
            continue
        left, right = (part.strip() for part in expression.split(token, 1))
        if not left or not right:
            raise PipelineRuntimeError(f"invalid edge condition: {expression}")
        return bool(op(values.get(left), _literal_value(right)))
    raise PipelineRuntimeError(f"unsupported edge condition: {expression}")


def has_planned(graph: GraphConfig) -> bool:
    return any(node.status == STATUS_PLANNED for node in graph.nodes) or any(
        nodeset.status == STATUS_PLANNED or has_planned(nodeset.graph) for nodeset in graph.nodesets.values()
    )


def planned_items(graph: GraphConfig, *, prefix: str = "") -> tuple[dict[str, object], ...]:
    items: list[dict[str, object]] = []
    for node in graph.nodes:
        nodeset = graph.nodesets.get(node.node_type.removeprefix("nodeset.")) if node.node_type.startswith("nodeset.") else None
        if node.status == STATUS_PLANNED:
            behavior = effective_planned_behavior(node, nodeset)
            items.append(
                {
                    "id": f"{prefix}{node.name}",
                    "object_type": "node",
                    "behavior": behavior.kind,
                    "stub_module": behavior.stub_module,
                }
            )
    for name, nodeset in graph.nodesets.items():
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
        items.extend(planned_items(nodeset.graph, prefix=f"{full_name}."))
    return tuple(items)


def all_planned_are_python_stub(graph: GraphConfig) -> bool:
    items = planned_items(graph)
    return bool(items) and all(item.get("behavior") == PLANNED_BEHAVIOR_PYTHON_STUB for item in items)


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _literal_value(value: str) -> object:
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
