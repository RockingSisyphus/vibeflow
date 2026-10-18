"""Scheduling join checks, separate from topology and payload checks."""
from typing import Mapping
from vibeflow.core.flow import JOIN_POLICY_ALL
from vibeflow.targets.shared.quality_support.workflow_rules.helpers import _data_finding
from vibeflow.targets.shared.quality_support.workflow_rules.join_exclusivity import append_all_join_mutual_exclusion_finding
from vibeflow.targets.shared.quality_support.workflow_rules.branch_paths import BranchPaths

def append_join_policy_health(graph, compiled, state, *, owner: str = "pipeline") -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    schedule_edges = tuple(compiled.resolved_schedule_edges)
    transfer_edges = tuple(compiled.resolved_transfer_edges)
    incoming_edges: dict[str, list[object]] = {node.name: [] for node in graph.nodes}
    outgoing_targets: dict[str, set[str]] = {}
    transfer_incoming: dict[str, list[object]] = {node.name: [] for node in graph.nodes}
    for edge in schedule_edges:
        incoming_edges.setdefault(edge.target, []).append(edge)
        outgoing_targets.setdefault(edge.source, set()).add(edge.target)
    for edge in transfer_edges:
        transfer_incoming.setdefault(edge.target, []).append(edge)
    paths = BranchPaths(graph, compiled)
    for node in graph.nodes:
        if node.join_policy == JOIN_POLICY_ALL:
            successors = outgoing_targets.get(node.name, set())
            predecessors = {edge.source for edge in incoming_edges.get(node.name, ())}
            if len(predecessors) > 1 and len(successors) > 1:
                state.errors.append(_data_finding(
                    "GRAPH.JOIN.FORK_CONFLICT", node.name,
                    f"node '{node.name}' cannot collect multiple branches and dispatch another fanout in the same call",
                    node=node.name, severity="error", details={"owner": owner,
                        "predecessors": sorted(predecessors), "successors": sorted(successors),
                        "suggestion": "Add a separate downstream dispatch node after the all-join."}))
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
            if not any(left != right for left in unconditional for right in conditional):
                continue
            relevant = [edge for edge in edges if edge.source in {*unconditional, *conditional}]
            if all(left.source == right.source or paths.exclusive(left, right)
                   for left in relevant if left.when for right in relevant if not right.when):
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
    predecessor_count = len(schedule_pairs)
    if predecessor_count < 2 and transfer_only:
        state.errors.append(
            _data_finding(
                "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY",
                node.name,
                (
                    f"node '{node.name}' declares join_policy='all', but only {predecessor_count} "
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
    if predecessor_count == 1:
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


def _incoming_sources_providing_type(edges: list[object], nodes_by_name: Mapping[str, object], data_type: str, *, conditional: bool) -> list[str]:
    sources: list[str] = []
    for edge in edges:
        if bool(edge.when) != conditional:
            continue
        source = nodes_by_name.get(edge.source)
        if source is None:
            continue
        if any(provider.type == data_type for provider in getattr(source, "provides", ())):
            sources.append(str(edge.source))
    return sorted(set(sources))

def _edge_summary(edge) -> dict[str, object]:
    return {
        "source": str(getattr(edge, "source", "")),
        "target": str(getattr(edge, "target", "")),
        "when": str(getattr(edge, "when", "")),
    }

