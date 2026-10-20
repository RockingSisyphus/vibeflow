from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from typing import Mapping, Sequence

from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.findings import HealthFinding
from vibeflow.core.constants import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL
from vibeflow.core.planned import PLANNED_BEHAVIOR_PYTHON_STUB, PLANNED_BEHAVIOR_TRANSPARENT, effective_planned_behavior


@dataclass(frozen=True)
class _DecisionFlow:
    outgoing: dict[str, list[str]]
    outgoing_edges: dict[str, list[object]]
    incoming_edges: dict[str, list[object]]
    can_reach_end: set[str]


def _flowchart_health_facts(
    graph,
    compiled,
    state,
    *,
    owner: str = "pipeline",
    entry_starts: set[str] | None = None,
) -> None:
    active_nodes = [node for node in graph.nodes if _node_participates_in_flow(graph, node)]
    if not active_nodes:
        return
    active_names = {node.name for node in active_nodes}
    incoming, outgoing, outgoing_edges, incoming_edges = _flow_maps(compiled, active_names)
    node_by_name = {node.name: node for node in active_nodes}
    starts = {
        name
        for name in active_names
        if (
            compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL
        )
        and not incoming[name]
    }
    if entry_starts is not None:
        starts &= entry_starts
    ends = {
        name
        for name in active_names
        if (
            compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL
            or _is_permanent_loop(node_by_name[name])
        )
        and not outgoing[name]
    }
    _append_boundary_findings(starts, ends, state, owner=owner)
    _append_reachability_findings(starts, active_names, incoming_edges, outgoing_edges, outgoing, state, owner=owner)
    can_reach_end = _append_end_reachability_findings(ends, active_names, incoming_edges, outgoing_edges, incoming, state, owner=owner)
    if ends:
        decision_flow = _DecisionFlow(
            outgoing,
            outgoing_edges,
            incoming_edges,
            can_reach_end,
        )
        _append_decision_branch_health(graph, compiled, state, decision_flow, owner=owner)
    _append_explicit_edge_duplicate_warnings(graph, state, owner=owner)
    _append_orphan_findings(active_names, incoming_edges, outgoing_edges, incoming, outgoing, state, owner=owner)


def append_flowchart_health(graph, compiled, state, *, owner="pipeline"):
    _flowchart_health_facts(graph, compiled, state, owner=owner)



def _flow_maps(compiled, active_names: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[object]], dict[str, list[object]]]:
    incoming = {name: [] for name in active_names}
    outgoing = {name: [] for name in active_names}
    outgoing_edges = {name: [] for name in active_names}
    incoming_edges = {name: [] for name in active_names}
    for edge in compiled.resolved_schedule_edges:
        if edge.source not in active_names or edge.target not in active_names:
            continue
        outgoing[edge.source].append(edge.target)
        outgoing_edges[edge.source].append(edge)
        incoming[edge.target].append(edge.source)
        incoming_edges[edge.target].append(edge)
    return incoming, outgoing, outgoing_edges, incoming_edges


def _node_participates_in_flow(graph, node) -> bool:
    if node.status != STATUS_PLANNED:
        return True
    nodeset = graph.nodesets.get(node.type_used)
    return effective_planned_behavior(node, nodeset).kind in {PLANNED_BEHAVIOR_TRANSPARENT, PLANNED_BEHAVIOR_PYTHON_STUB}


def _is_permanent_loop(node: object) -> bool:
    if getattr(node, "type_used", "") not in LOOP_NODE_TYPES:
        return False
    loop = getattr(node, "loop", None)
    stop_when = getattr(loop, "stop_when", None)
    return (
        getattr(loop, "max_iterations", 1000) is None
        and not getattr(loop, "stop_after", 0)
        and not getattr(stop_when, "source", "")
    )




def _append_boundary_findings(starts: set[str], ends: set[str], state, *, owner: str) -> None:
    if not starts:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_START", owner, "graph must have a terminal start node with no incoming flow edge", details={"owner": owner}))
    if not ends:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_END", owner, "graph must have a terminal end node with no outgoing flow edge", details={"owner": owner}))


def _append_reachability_findings(
    starts: set[str],
    active_names: set[str],
    incoming_edges: dict[str, list[object]],
    outgoing_edges: dict[str, list[object]],
    outgoing: dict[str, list[str]],
    state,
    *,
    owner: str,
) -> None:
    if not starts:
        return
    reachable = _walk(starts, outgoing)
    for name in sorted(active_names - reachable):
        state.errors.append(
            _flow_finding(
                "GRAPH.FLOW.UNREACHABLE_FROM_START",
                name,
                f"node '{name}' is not reachable from a start node",
                object_type="node",
                details=_node_flow_details(owner, name, incoming_edges, outgoing_edges),
            )
        )


def _append_end_reachability_findings(
    ends: set[str],
    active_names: set[str],
    incoming_edges: dict[str, list[object]],
    outgoing_edges: dict[str, list[object]],
    incoming: dict[str, list[str]],
    state,
    *,
    owner: str,
) -> set[str]:
    if not ends:
        return set()
    can_reach_end = _walk(ends, incoming)
    for name in sorted(active_names - can_reach_end):
        state.errors.append(
            _flow_finding(
                "GRAPH.FLOW.CANNOT_REACH_END",
                name,
                f"node '{name}' cannot reach an end node",
                object_type="node",
                details=_node_flow_details(owner, name, incoming_edges, outgoing_edges),
            )
        )
    return can_reach_end


def _append_orphan_findings(
    active_names: set[str],
    incoming_edges: dict[str, list[object]],
    outgoing_edges: dict[str, list[object]],
    incoming: dict[str, list[str]],
    outgoing: dict[str, list[str]],
    state,
    *,
    owner: str,
) -> None:
    if len(active_names) <= 1:
        return
    for name in sorted(active_names):
        if not incoming[name] and not outgoing[name]:
            state.errors.append(
                _flow_finding(
                    "GRAPH.FLOW.ORPHAN_NODE",
                    name,
                    f"node '{name}' has no flow edges",
                    object_type="node",
                    details=_node_flow_details(owner, name, incoming_edges, outgoing_edges),
                )
            )


def _append_decision_branch_health(graph, compiled, state, flow: _DecisionFlow, *, owner: str) -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    for node in graph.nodes:
        if node.status == STATUS_PLANNED or compiled.flow_kinds.get(node.name) != FLOW_KIND_DECISION:
            continue
        _append_single_decision_health(node, nodes_by_name, state, flow, owner=owner)


def _append_single_decision_health(node, nodes_by_name, state, flow: _DecisionFlow, *, owner: str) -> None:
    for edge in flow.outgoing_edges.get(node.name, ()):
        target = getattr(edge, "target", "")
        if target in nodes_by_name and not _is_loop_branch(node.name, target, flow.outgoing) and target not in flow.can_reach_end:
            state.errors.append(
                _flow_finding(
                    "GRAPH.DECISION.BRANCH_CANNOT_REACH_END",
                    node.name,
                    f"decision branch {node.name}->{target} cannot reach a terminal end node",
                    object_type="node",
                    details={
                        **_node_flow_details(owner, node.name, flow.incoming_edges, flow.outgoing_edges),
                        "branch_edge": _edge_summary(edge),
                        "target": target,
                    },
                )
            )


def _append_explicit_edge_duplicate_warnings(graph, state, *, owner: str) -> None:
    for edge, count in Counter(graph.edges).items():
        if count <= 1:
            continue
        state.warnings.append(
            HealthFinding(
                rule_id="GRAPH.EDGE.DUPLICATE",
                severity="warning",
                object_type="edge",
                object_id=f"{edge.source}->{edge.target}",
                failure_layer="topology",
                message=f"identical explicit edge {edge.source}->{edge.target} is declared {count} times and will be collapsed",
                suggested_fix_type="fix_config",
                details={
                    "owner": owner,
                    "conditions": [edge.when],
                    "edges": [_edge_summary(edge)] * count,
                },
            )
        )


def _is_loop_branch(node_name: str, target: str, outgoing: dict[str, list[str]]) -> bool:
    return node_name in _walk({target}, outgoing)


def _node_flow_details(
    owner: str,
    node_name: str,
    incoming_edges: Mapping[str, Sequence[object]],
    outgoing_edges: Mapping[str, Sequence[object]],
) -> dict[str, object]:
    return {
        "owner": owner,
        "node": node_name,
        "incoming_edges": [_edge_summary(edge) for edge in incoming_edges.get(node_name, ())],
        "outgoing_edges": [_edge_summary(edge) for edge in outgoing_edges.get(node_name, ())],
    }


def _edge_summary(edge) -> dict[str, object]:
    return {
        "source": str(getattr(edge, "source", "")),
        "target": str(getattr(edge, "target", "")),
        "when": str(getattr(edge, "when", "")),
    }


def _walk(starts: set[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen = set(starts)
    queue = list(starts)
    while queue:
        node = queue.pop(0)
        for target in adjacency.get(node, ()):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return seen


def _flow_finding(rule_id: str, object_id: str, message: str, *, object_type: str = "pipeline", details: Mapping[str, object] | None = None) -> HealthFinding:
    return HealthFinding(rule_id=rule_id, severity="error", object_type=object_type, object_id=object_id, failure_layer="topology", message=message, suggested_fix_type="fix_config", details=details or {})


__all__ = [
    "append_flowchart_health",
]
