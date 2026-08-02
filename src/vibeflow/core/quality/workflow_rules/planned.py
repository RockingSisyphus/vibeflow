"""Language-neutral planned-node and planned-nodeset health rules."""

from __future__ import annotations

from dataclasses import dataclass

from vibeflow.core.findings import HealthFinding
from vibeflow.core.flow import (
    LOOP_NODE_TYPES,
    STATUS_IMPLEMENTED,
    STATUS_PLANNED,
)
from vibeflow.core.planned import (
    PLANNED_BEHAVIOR_BLOCKING,
    PLANNED_BEHAVIOR_PYTHON_STUB,
    PlannedBehavior,
    effective_planned_behavior,
    planned_behavior_label,
)


@dataclass(frozen=True)
class PlannedImplementationCheck:
    behavior: PlannedBehavior
    object_type: str
    object_id: str
    project_root: str


def planned_health_events(
    graph,
) -> tuple[HealthFinding | PlannedImplementationCheck, ...]:
    events: list[HealthFinding | PlannedImplementationCheck] = []
    visited_nodesets: set[str] = set()
    _append_graph_events(graph, events, owner="pipeline")
    for nodeset in graph.nodesets.values():
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        if nodeset.status == STATUS_PLANNED:
            events.append(_planned_nodeset_finding(nodeset))
            _append_implementation_check(
                nodeset.planned_behavior,
                events,
                object_type="nodeset",
                object_id=nodeset.type_key,
                project_root=graph.project_root,
            )
        _append_graph_events(
            nodeset.graph,
            events,
            owner=f"nodeset:{nodeset.type_key}",
        )
        if nodeset.status == STATUS_IMPLEMENTED:
            if graph_has_blocking_planned(nodeset.graph):
                events.append(
                    _planned_child_finding(nodeset.type_key, severity="error")
                )
            elif graph_has_planned(nodeset.graph):
                events.append(
                    _planned_child_finding(nodeset.type_key, severity="warning")
                )
    return tuple(events)


def graph_has_planned(graph, *, visited_nodesets: set[str] | None = None) -> bool:
    if visited_nodesets is None:
        visited_nodesets = set()
    if any(node.status == STATUS_PLANNED for node in graph.nodes):
        return True
    for nodeset_name in _referenced_nodeset_names(graph):
        nodeset = graph.nodesets.get(nodeset_name)
        if nodeset is None or nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        if nodeset.status == STATUS_PLANNED or graph_has_planned(
            nodeset.graph,
            visited_nodesets=visited_nodesets,
        ):
            return True
    return False


def graph_has_blocking_planned(
    graph,
    *,
    visited_nodesets: set[str] | None = None,
) -> bool:
    if visited_nodesets is None:
        visited_nodesets = set()
    for node in graph.nodes:
        nodeset = graph.nodesets.get(node.type_used)
        if (
            node.status == STATUS_PLANNED
            and effective_planned_behavior(node, nodeset).kind
            == PLANNED_BEHAVIOR_BLOCKING
        ):
            return True
    for nodeset_name in _referenced_nodeset_names(graph):
        nodeset = graph.nodesets.get(nodeset_name)
        if nodeset is None or nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        if nodeset.status == STATUS_PLANNED:
            if nodeset.planned_behavior.kind == PLANNED_BEHAVIOR_BLOCKING:
                return True
            continue
        if graph_has_blocking_planned(
            nodeset.graph,
            visited_nodesets=visited_nodesets,
        ):
            return True
    return False


def _append_graph_events(graph, events, *, owner: str) -> None:
    for node in graph.nodes:
        if node.status != STATUS_PLANNED:
            continue
        nodeset = graph.nodesets.get(node.type_used)
        behavior = effective_planned_behavior(node, nodeset)
        events.append(_planned_node_finding(node, behavior=behavior, owner=owner))
        _append_implementation_check(
            behavior,
            events,
            object_type="node",
            object_id=node.id,
            project_root=graph.project_root,
        )


def _append_implementation_check(
    behavior,
    events,
    *,
    object_type: str,
    object_id: str,
    project_root: str,
) -> None:
    if behavior.kind == PLANNED_BEHAVIOR_PYTHON_STUB:
        events.append(
            PlannedImplementationCheck(
                behavior=behavior,
                object_type=object_type,
                object_id=object_id,
                project_root=project_root,
            )
        )


def _planned_nodeset_finding(nodeset) -> HealthFinding:
    behavior = nodeset.planned_behavior
    return HealthFinding(
        rule_id="GRAPH.PLANNED.NODESET",
        severity="warning",
        object_type="nodeset",
        object_id=nodeset.type_key,
        failure_layer="topology",
        message=(
            f"nodeset '{nodeset.type_key}' is "
            f"{planned_behavior_label(behavior)} and cannot run as production"
        ),
        suggested_fix_type="implement_nodeset",
        details=_behavior_details(behavior),
    )


def _planned_child_finding(name: str, *, severity: str) -> HealthFinding:
    return HealthFinding(
        rule_id="GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD",
        severity=severity,
        object_type="nodeset",
        object_id=name,
        failure_layer="topology",
        message=f"implemented nodeset '{name}' contains planned child nodes",
        suggested_fix_type="implement_nodeset",
    )


def _planned_node_finding(node, *, behavior, owner: str) -> HealthFinding:
    return HealthFinding(
        rule_id="GRAPH.PLANNED.NODE",
        severity="warning",
        object_type="node",
        object_id=node.id,
        failure_layer="topology",
        message=(
            f"node '{node.id}' is {planned_behavior_label(behavior)} "
            "and cannot run as production"
        ),
        suggested_fix_type="implement_node",
        details={
            "owner": owner,
            "flow_kind": node.flow_kind,
            **_behavior_details(behavior),
        },
    )


def behavior_details(behavior) -> dict[str, object]:
    return _behavior_details(behavior)


def _behavior_details(behavior) -> dict[str, object]:
    details = {"planned_behavior": behavior.kind}
    if behavior.stub_module:
        details["stub_module"] = behavior.stub_module
    return details


def _referenced_nodeset_names(graph) -> tuple[str, ...]:
    refs: list[str] = []
    for node in graph.nodes:
        if node.type_used in graph.nodesets:
            refs.append(node.type_used)
        elif node.type_used in LOOP_NODE_TYPES and node.loop.body:
            refs.append(node.loop.body)
    return tuple(sorted(set(refs)))


__all__ = [
    "PlannedImplementationCheck",
    "behavior_details",
    "graph_has_blocking_planned",
    "graph_has_planned",
    "planned_health_events",
]
