from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from vibeflow.core.contracts import CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE, provider_keys
from vibeflow.core.flow import IO_NODE_TYPE, JOIN_POLICY_ALL, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.quality.workflow_rules.flow_data import _incoming_sources_providing_type
from vibeflow.core.quality.workflow_rules.helpers import _data_finding
from vibeflow.core.quality.workflow_rules.join_exclusivity import append_all_join_mutual_exclusion_finding
from vibeflow.core.findings import HealthFinding
from vibeflow.core.constants import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL
from vibeflow.core.planned import PLANNED_BEHAVIOR_PYTHON_STUB, PLANNED_BEHAVIOR_TRANSPARENT, effective_planned_behavior


@dataclass(frozen=True)
class _DecisionFlow:
    outgoing: dict[str, list[str]]
    outgoing_edges: dict[str, list[object]]
    incoming_edges: dict[str, list[object]]
    can_reach_end: set[str]


def append_flowchart_health(
    graph,
    compiled,
    state,
    *,
    owner: str = "pipeline",
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
            or _is_io_boundary(node_by_name[name], "receive")
        )
        and not incoming[name]
    }
    ends = {
        name
        for name in active_names
        if (
            compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL
            or _is_io_boundary(node_by_name[name], "send")
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
    if getattr(node, "async_mode", "") == "detached":
        return False
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


def _is_io_boundary(node: object, operation: str) -> bool:
    return (
        getattr(node, "type_used", "") == IO_NODE_TYPE
        and getattr(getattr(node, "io", None), "operation", "")
        == operation
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


def append_join_policy_health(graph, compiled, state, *, owner: str = "pipeline") -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    schedule_edges = tuple(compiled.resolved_schedule_edges)
    transfer_edges = tuple(compiled.resolved_transfer_edges)
    incoming_edges: dict[str, list[object]] = {node.name: [] for node in graph.nodes}
    transfer_incoming: dict[str, list[object]] = {node.name: [] for node in graph.nodes}
    for edge in schedule_edges:
        incoming_edges.setdefault(edge.target, []).append(edge)
    for edge in transfer_edges:
        transfer_incoming.setdefault(edge.target, []).append(edge)
    for node in graph.nodes:
        if node.join_policy == JOIN_POLICY_ALL:
            _append_all_join_edge_class_findings(
                node,
                incoming_edges.get(node.name, ()),
                transfer_incoming.get(node.name, ()),
                nodes_by_name,
                state,
                owner=owner,
            )
            append_all_join_mutual_exclusion_finding(
                node,
                incoming_edges.get(node.name, ()),
                transfer_incoming.get(node.name, ()),
                schedule_edges,
                nodes_by_name,
                getattr(compiled, "flow_kinds", {}),
                state,
                owner=owner,
            )
            continue
        edges = incoming_edges.get(node.name, [])
        if not edges or not any(edge.when for edge in edges) or not any(not edge.when for edge in edges):
            continue
        for requirement in node.requires:
            unconditional = _incoming_sources_providing_type(edges, nodes_by_name, requirement.type, conditional=False)
            conditional = _incoming_sources_providing_type(edges, nodes_by_name, requirement.type, conditional=True)
            if not unconditional or not conditional:
                continue
            state.errors.append(
                _data_finding(
                    "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL",
                    requirement.type,
                    f"node '{node.name}' mixes conditional and unconditional incoming providers for type '{requirement.type}', which can trigger safe OR join before the selected branch is ready",
                    node=node.name,
                    severity="error",
                    details={
                        "join_policy": node.join_policy,
                        "owner": owner,
                        "required_type": requirement.type,
                        "unconditional_sources": unconditional,
                        "conditional_sources": conditional,
                        "suggestion": "Make the sources mutually conditional, set join_policy='all' when all inputs are required, or add an explicit merge/select node.",
                    },
                )
            )


def _append_all_join_edge_class_findings(node, schedule_incoming, transfer_incoming, nodes_by_name, state, *, owner: str) -> None:
    schedule_pairs = {edge.pair for edge in schedule_incoming}
    transfer_only = [edge for edge in transfer_incoming if edge.pair not in schedule_pairs]
    schedule_details = [_edge_summary(edge) for edge in schedule_incoming]
    transfer_details = [_edge_summary(edge) for edge in transfer_incoming]
    provider_details = [
        {
            "node": source.name,
            "provides": [{"key": item.key, "type": item.type} for item in source.provides],
        }
        for source in (nodes_by_name.get(edge.source) for edge in transfer_incoming)
        if source is not None
    ]
    base_details = {
        "owner": owner,
        "node": node.name,
        "join_policy": node.join_policy,
        "required_types": sorted({requirement.type for requirement in node.requires}),
        "schedule_incoming": schedule_details,
        "transfer_incoming": transfer_details,
        "transfer_only_incoming": [_edge_summary(edge) for edge in transfer_only],
        "candidate_providers": provider_details,
    }
    if len(schedule_incoming) < 2 and transfer_only:
        state.errors.append(
            _data_finding(
                "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
                node.name,
                (
                    f"node '{node.name}' declares join_policy='all', but only {len(schedule_incoming)} "
                    "incoming edge participates in scheduling; transfer-only edges never activate the join"
                ),
                node=node.name,
                severity="error",
                details={
                    **base_details,
                    "suggestion": (
                        "Keep join_policy='all' only for at least two real parallel schedule branches. "
                        "For a sequential chain, remove 'all' and keep payload shortcuts as valid data-bypass edges."
                    ),
                },
            )
        )
        return
    if len(schedule_incoming) == 1:
        state.warnings.append(
            _data_finding(
                "GRAPH.JOIN.REDUNDANT_ALL",
                node.name,
                f"node '{node.name}' has join_policy='all' but only one scheduling predecessor",
                node=node.name,
                details={
                    **base_details,
                    "suggestion": "Remove join_policy='all'; the default safe_any join is sufficient for one schedule incoming edge.",
                },
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
    seen: dict[tuple[str, str], set[str]] = {}
    for edge in graph.edges:
        seen.setdefault(edge.pair, set()).add(edge.when)
    for pair, conditions in sorted(seen.items()):
        count = sum(1 for edge in graph.edges if edge.pair == pair)
        if count <= 1:
            continue
        rule_id = "GRAPH.EDGE.CONFLICTING_DUPLICATE" if len(conditions) > 1 else "GRAPH.EDGE.DUPLICATE"
        state.warnings.append(
            HealthFinding(
                rule_id=rule_id,
                severity="warning",
                object_type="edge",
                object_id=f"{pair[0]}->{pair[1]}",
                failure_layer="topology",
                message=f"explicit edge {pair[0]}->{pair[1]} is declared {count} times and will be collapsed",
                suggested_fix_type="fix_config",
                details={
                    "owner": owner,
                    "conditions": sorted(conditions),
                    "edges": [_edge_summary(edge) for edge in graph.edges if edge.pair == pair],
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
    "append_join_policy_health",
]
