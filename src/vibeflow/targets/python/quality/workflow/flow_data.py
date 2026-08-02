"""Python registry adapter for language-neutral data-flow health rules."""

from __future__ import annotations

from vibeflow.core.flow import STATUS_PLANNED
from vibeflow.core.quality.workflow_rules.flow_data import (
    append_data_contract_warnings as _append_core_data_contract_warnings,
)
from vibeflow.targets.python.project.compiler import GraphCompileError, GraphCompiler


def append_data_contract_warnings(
    graph,
    compiled,
    state,
    *,
    owner: str = "pipeline",
    registry=None,
) -> None:
    _append_core_data_contract_warnings(
        graph,
        compiled,
        state,
        owner=owner,
        runtime_flow_kinds=_registry_flow_kinds(graph, registry),
    )


def _registry_flow_kinds(graph, registry) -> dict[str, str]:
    if registry is None:
        return {}
    kinds: dict[str, str] = {}
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            continue
        try:
            node_cls = registry.get(node.type_used)
        except Exception:
            continue
        info = getattr(node_cls, "NODE_INFO", None)
        flow_kind = str(getattr(info, "flow_kind", ""))
        if flow_kind:
            kinds[node.name] = flow_kind
    return kinds


def _append_nodeset_flow_health(
    graph,
    state,
    *,
    registry,
    visited_nodesets: set[str],
) -> None:
    from vibeflow.targets.python.quality.workflow.flow import (
        append_flowchart_health,
        append_join_policy_health,
    )

    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        try:
            nested = GraphCompiler().compile(
                nodeset.graph,
                registry=registry,
                owner=f"nodeset:{nodeset.type_key}",
            )
        except GraphCompileError:
            continue
        nested_owner = f"nodeset:{nodeset.type_key}"
        append_flowchart_health(
            nodeset.graph,
            nested,
            state,
            registry=registry,
            owner=nested_owner,
            visited_nodesets=visited_nodesets,
        )
        append_data_contract_warnings(
            nodeset.graph,
            nested,
            state,
            owner=nested_owner,
            registry=registry,
        )
        append_join_policy_health(
            nodeset.graph,
            nested,
            state,
            owner=nested_owner,
        )

__all__ = ["append_data_contract_warnings"]
