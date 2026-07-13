from __future__ import annotations

from typing import Mapping, Sequence

from vibeflow.health.flow_data import _data_finding, _parse_when
from vibeflow.node import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL


def append_all_join_mutual_exclusion_finding(
    node,
    schedule_incoming,
    transfer_incoming,
    schedule_edges,
    nodes_by_name,
    flow_kinds,
    state,
    *,
    owner: str,
) -> None:
    if len(schedule_incoming) < 2:
        return
    evidence = _mutually_exclusive_join_evidence(
        schedule_incoming,
        schedule_edges,
        nodes_by_name,
        flow_kinds,
    )
    if not evidence:
        return
    state.errors.append(
        _data_finding(
            "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE",
            node.name,
            (
                f"node '{node.name}' declares join_policy='all', but at least two required schedule "
                "predecessors are controlled by mutually exclusive branches of the same decision"
            ),
            node=node.name,
            severity="error",
            details={
                "owner": owner,
                "join_policy": node.join_policy,
                "required_types": sorted({requirement.type for requirement in node.requires}),
                "schedule_incoming": [_edge_summary(edge) for edge in schedule_incoming],
                "transfer_incoming": [_edge_summary(edge) for edge in transfer_incoming],
                "candidate_providers": [
                    {
                        "node": source.name,
                        "provides": [{"key": item.key, "type": item.type} for item in source.provides],
                    }
                    for source in (nodes_by_name.get(edge.source) for edge in transfer_incoming)
                    if source is not None
                ],
                "exclusive_branch_pairs": evidence,
                "suggestion": (
                    "Use the default safe_any join for mutually exclusive alternatives, or merge each "
                    "decision alternative before an 'all' join that waits only for independently active branches."
                ),
            },
        )
    )


def _mutually_exclusive_join_evidence(schedule_incoming, schedule_edges, nodes_by_name, flow_kinds) -> list[dict[str, object]]:
    node_names = set(nodes_by_name)
    outgoing: dict[str, list[str]] = {name: [] for name in node_names}
    outgoing_edges: dict[str, list[object]] = {name: [] for name in node_names}
    incoming: dict[str, list[str]] = {name: [] for name in node_names}
    for edge in schedule_edges:
        if edge.source not in node_names or edge.target not in node_names:
            continue
        outgoing[edge.source].append(edge.target)
        outgoing_edges[edge.source].append(edge)
        incoming[edge.target].append(edge.source)

    starts = {
        name
        for name in node_names
        if flow_kinds.get(name) == FLOW_KIND_TERMINAL and not incoming.get(name)
    }
    dominators = _schedule_dominators(starts, incoming, outgoing)
    if not dominators:
        return []

    reachability = {name: _walk({name}, outgoing) for name in node_names}
    decision_nodes = sorted(
        name
        for name in node_names
        if flow_kinds.get(name) == FLOW_KIND_DECISION
    )
    evidence: list[dict[str, object]] = []
    for left_index, left_edge in enumerate(schedule_incoming):
        for right_edge in schedule_incoming[left_index + 1 :]:
            left_source = str(left_edge.source)
            right_source = str(right_edge.source)
            if left_source == right_source:
                continue
            for decision in decision_nodes:
                if decision not in dominators.get(left_source, set()) or decision not in dominators.get(right_source, set()):
                    continue
                left_restriction = _decision_branch_restriction(
                    decision,
                    left_source,
                    outgoing_edges,
                    reachability,
                )
                right_restriction = _decision_branch_restriction(
                    decision,
                    right_source,
                    outgoing_edges,
                    reachability,
                )
                if left_restriction is None or right_restriction is None:
                    continue
                left_key, left_conditions = left_restriction
                right_key, right_conditions = right_restriction
                if left_key != right_key:
                    continue
                if not all(
                    _branch_conditions_are_mutually_exclusive(left, right)
                    for left in left_conditions
                    for right in right_conditions
                ):
                    continue
                evidence.append(
                    {
                        "decision": decision,
                        "condition_key": left_key,
                        "left_predecessor": left_source,
                        "right_predecessor": right_source,
                        "left_conditions": [_branch_condition_details(item) for item in left_conditions],
                        "right_conditions": [_branch_condition_details(item) for item in right_conditions],
                    }
                )
    return evidence


def _schedule_dominators(
    starts: set[str],
    incoming: Mapping[str, Sequence[str]],
    outgoing: Mapping[str, Sequence[str]],
) -> dict[str, set[str]]:
    if not starts:
        return {}
    reachable = _walk(starts, outgoing)
    dominators = {
        name: ({name} if name in starts else set(reachable))
        for name in reachable
    }
    changed = True
    while changed:
        changed = False
        for name in sorted(reachable - starts):
            predecessors = [source for source in incoming.get(name, ()) if source in reachable]
            if not predecessors:
                new_value = {name}
            else:
                shared = set(dominators[predecessors[0]])
                for predecessor in predecessors[1:]:
                    shared.intersection_update(dominators[predecessor])
                new_value = {name, *shared}
            if new_value != dominators[name]:
                dominators[name] = new_value
                changed = True
    return dominators


def _decision_branch_restriction(
    decision: str,
    source: str,
    outgoing_edges,
    reachability,
) -> tuple[str, tuple[tuple[str, object, object], ...]] | None:
    relevant = [
        edge
        for edge in outgoing_edges.get(decision, ())
        if source in reachability.get(str(edge.target), set())
    ]
    if not relevant:
        return None
    parsed = [_parse_when(str(getattr(edge, "when", ""))) for edge in relevant]
    if any(item is None for item in parsed):
        return None
    conditions = tuple(
        (str(item[1]), item[2], edge)
        for edge, item in zip(relevant, parsed)
        if item is not None
    )
    keys = {str(item[0]) for item in parsed if item is not None}
    if len(keys) != 1 or not conditions:
        return None
    return next(iter(keys)), conditions


def _branch_conditions_are_mutually_exclusive(
    left: tuple[str, object, object],
    right: tuple[str, object, object],
) -> bool:
    left_operator, left_value, _ = left
    right_operator, right_value, _ = right
    if left_operator == "==" and right_operator == "==":
        return left_value != right_value
    if left_operator == "==" and right_operator == "!=":
        return left_value == right_value
    if left_operator == "!=" and right_operator == "==":
        return left_value == right_value
    return False


def _branch_condition_details(condition: tuple[str, object, object]) -> dict[str, object]:
    operator, value, edge = condition
    return {
        "edge": _edge_summary(edge),
        "operator": operator,
        "value": value,
    }


def _edge_summary(edge) -> dict[str, object]:
    return {
        "source": str(getattr(edge, "source", "")),
        "target": str(getattr(edge, "target", "")),
        "when": str(getattr(edge, "when", "")),
    }


def _walk(starts: set[str], adjacency: Mapping[str, Sequence[str]]) -> set[str]:
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
