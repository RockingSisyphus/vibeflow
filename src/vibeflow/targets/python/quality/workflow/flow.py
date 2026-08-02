"""Python registry adapter for Core structural flow health rules."""

from __future__ import annotations

from typing import Mapping

from vibeflow.core.quality.workflow_rules.flow import (
    append_flowchart_health as _append_core_flowchart_health,
    append_join_policy_health,
)
from vibeflow.targets.python.quality.workflow.flow_data import (
    _append_nodeset_flow_health,
    append_data_contract_warnings,
)


def append_flowchart_health(
    graph,
    compiled,
    state,
    *,
    registry,
    owner: str = "pipeline",
    visited_nodesets: set[str] | None = None,
) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    _append_core_flowchart_health(
        graph,
        compiled,
        state,
        decision_schema_values=_decision_schema_values(graph, registry),
        owner=owner,
    )
    _append_nodeset_flow_health(
        graph,
        state,
        registry=registry,
        visited_nodesets=visited_nodesets,
    )


def _decision_schema_values(
    graph,
    registry,
) -> dict[str, set[object] | None]:
    values_by_node: dict[str, set[object] | None] = {}
    if registry is None:
        return values_by_node
    for node in graph.nodes:
        try:
            node_cls = registry.get(node.type_used)
        except Exception:
            continue
        contract = getattr(node_cls, "CONTRACT", None)
        schema = getattr(contract, "output_schema", None)
        if not isinstance(schema, Mapping):
            continue
        values: set[object] = set()
        for provider in node.provides:
            spec = schema.get(provider.key)
            if not isinstance(spec, Mapping):
                continue
            enum = spec.get("enum")
            if isinstance(enum, (list, tuple)):
                values.update(enum)
            elif spec.get("type") == "boolean":
                values.update((True, False))
        values_by_node[node.name] = values or None
    return values_by_node

__all__ = [
    "append_data_contract_warnings",
    "append_flowchart_health",
    "append_join_policy_health",
]
