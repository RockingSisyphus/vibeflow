"""Runtime inbox facts: initial input eligibility, transfers and bypass payloads."""
from typing import Mapping
from vibeflow.core.contracts import CARDINALITY_EXACTLY_ONE
from vibeflow.core.flow import STATUS_PLANNED
from vibeflow.core.constants import FLOW_KIND_TERMINAL
from vibeflow.targets.shared.quality_support.workflow_rules.helpers import _data_finding, _provider_source_details

def append_runtime_requirement_findings(
    graph,
    compiled,
    nodes_by_name,
    state,
    *,
    owner: str,
    runtime_flow_kinds: Mapping[str, str] | None = None,
) -> None:
    """Report required envelopes that the runtime can never place in a node inbox.

    Runtime input injection follows schedule edges, while output delivery follows all
    transfer edges.  Keeping those two edge sets separate is important: an explicit
    shortcut may be classified as transfer-only and therefore cannot make its target
    an initial-input node.
    """

    schedule_edges = tuple(compiled.resolved_schedule_edges)
    transfer_edges = tuple(compiled.resolved_transfer_edges)
    schedule_incoming = _edges_by_target(schedule_edges, nodes_by_name)
    transfer_incoming = _edges_by_target(transfer_edges, nodes_by_name)
    input_types = {item.type for item in graph.inputs}
    candidate_providers = _candidate_providers_by_type(nodes_by_name)
    flow_kinds = _runtime_flow_kinds(
        getattr(compiled, "flow_kinds", {}),
        runtime_flow_kinds,
    )

    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            continue
        accepts_initial = _runtime_accepts_initial_input(
            node.name,
            nodes_by_name,
            schedule_incoming,
            flow_kinds,
        )
        incoming = transfer_incoming.get(node.name, ())
        source_details = _provider_source_details(
            [nodes_by_name[edge.source] for edge in incoming if edge.source in nodes_by_name]
        )
        delivered_types = {
            provider.type
            for edge in incoming
            for provider in getattr(nodes_by_name.get(edge.source), "provides", ())
        }
        if accepts_initial:
            delivered_types.update(input_types)

        for requirement in node.requires:
            if requirement.cardinality != CARDINALITY_EXACTLY_ONE or requirement.type in delivered_types:
                continue
            state.errors.append(
                _data_finding(
                    "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE",
                    requirement.type,
                    (
                        f"node '{node.name}' requires type '{requirement.type}' exactly once, "
                        "but no runtime initial input or incoming transfer edge can deliver it"
                    ),
                    node=node.name,
                    severity="error",
                    details={
                        "owner": owner,
                        "required_type": requirement.type,
                        "required_cardinality": requirement.cardinality,
                        "accepts_initial_input": accepts_initial,
                        "entry_input_types": sorted(input_types),
                        "schedule_incoming": [_edge_details(edge) for edge in schedule_incoming.get(node.name, ())],
                        "transfer_incoming": [_edge_details(edge) for edge in incoming],
                        "incoming_provider_sources": source_details,
                        "candidate_providers": candidate_providers.get(requirement.type, []),
                        "suggestion": (
                            "Add a mainline or valid data-bypass edge from a node that actually provides "
                            f"type '{requirement.type}', or make '{node.name}' a true initial-input node."
                        ),
                    },
                )
            )


def append_data_bypass_payload_findings(compiled, nodes_by_name, state, *, owner: str) -> None:
    for edge in getattr(compiled, "data_bypass_edges", ()):
        source = nodes_by_name.get(edge.source)
        target = nodes_by_name.get(edge.target)
        if source is None or target is None:
            continue
        source_types = sorted({provider.type for provider in source.provides})
        target_types = sorted({requirement.type for requirement in target.requires})
        matching_types = sorted(set(source_types) & set(target_types))
        if matching_types:
            continue
        state.errors.append(
            _data_finding(
                "GRAPH.DATA.NO_PAYLOAD_BYPASS",
                f"{edge.source}->{edge.target}",
                (
                    f"data-bypass edge {edge.source}->{edge.target} cannot deliver any payload "
                    "required by its target"
                ),
                node=edge.target,
                severity="error",
                details={
                    "owner": owner,
                    "source": edge.source,
                    "target": edge.target,
                    "edge": _edge_details(edge),
                    "source_provider_types": source_types,
                    "target_required_types": target_types,
                    "matching_types": matching_types,
                    "candidate_providers": {
                        requirement.type: _candidate_providers_by_type(nodes_by_name).get(requirement.type, [])
                        for requirement in target.requires
                    },
                    "suggestion": (
                        "Remove the shortcut, or originate the bypass at a node whose provides.type "
                        "matches a target requirement. Data-bypass edges transfer data only and never trigger the target."
                    ),
                },
            )
        )


def _edges_by_target(edges, nodes_by_name) -> dict[str, list[object]]:
    incoming: dict[str, list[object]] = {name: [] for name in nodes_by_name}
    for edge in edges:
        if edge.target in nodes_by_name:
            incoming[edge.target].append(edge)
    return incoming


def _runtime_accepts_initial_input(node_name: str, nodes_by_name, schedule_incoming, flow_kinds) -> bool:
    node = nodes_by_name[node_name]
    if not node.requires:
        return False
    incoming = schedule_incoming.get(node_name, ())
    if not incoming:
        return True
    return any(
        _is_empty_runtime_start(edge.source, nodes_by_name, schedule_incoming, flow_kinds)
        for edge in incoming
    )


def _is_empty_runtime_start(node_name: str, nodes_by_name, schedule_incoming, flow_kinds) -> bool:
    source = nodes_by_name.get(node_name)
    return bool(
        source is not None
        and flow_kinds.get(node_name) == FLOW_KIND_TERMINAL
        and not schedule_incoming.get(node_name)
        and not source.requires
        and not source.provides
    )


def _candidate_providers_by_type(nodes_by_name) -> dict[str, list[dict[str, str]]]:
    candidates: dict[str, list[dict[str, str]]] = {}
    for node in nodes_by_name.values():
        for provider in node.provides:
            candidates.setdefault(provider.type, []).append({"node": node.name, "key": provider.key})
    return {key: sorted(values, key=lambda item: (item["node"], item["key"])) for key, values in candidates.items()}


def _runtime_flow_kinds(
    compiled_flow_kinds,
    supplied_flow_kinds: Mapping[str, str] | None,
) -> dict[str, str]:
    kinds = {str(name): str(value) for name, value in dict(compiled_flow_kinds or {}).items() if value}
    for name, flow_kind in dict(supplied_flow_kinds or {}).items():
        if flow_kind and str(name) not in kinds:
            kinds[str(name)] = str(flow_kind)
    return kinds


def _edge_details(edge) -> dict[str, object]:
    return {
        "from": str(getattr(edge, "source", "")),
        "to": str(getattr(edge, "target", "")),
        "when": str(getattr(edge, "when", "")),
    }


def initial_input_nodes(graph, compiled, runtime_flow_kinds=None) -> set[str]:
    nodes = {node.name: node for node in graph.nodes}
    incoming = _edges_by_target(compiled.resolved_schedule_edges, nodes)
    kinds = _runtime_flow_kinds(compiled.flow_kinds, runtime_flow_kinds)
    return {name for name in nodes if _runtime_accepts_initial_input(name, nodes, incoming, kinds)}
