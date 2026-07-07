from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from vibeflow.data_contract import CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE, provider_keys
from vibeflow.graph_config import JOIN_POLICY_ALL, STATUS_PLANNED
from vibeflow.health.flow_data import _append_nodeset_flow_health, _data_finding, _incoming_sources_providing_type, append_data_contract_warnings
from vibeflow.health.types import HealthFinding
from vibeflow.node import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL
from vibeflow.graph_config.planned_behavior import PLANNED_BEHAVIOR_PYTHON_STUB, PLANNED_BEHAVIOR_TRANSPARENT, effective_planned_behavior


@dataclass(frozen=True)
class _DecisionFlow:
    registry: object
    outgoing: dict[str, list[str]]
    outgoing_edges: dict[str, list[object]]
    incoming_edges: dict[str, list[object]]
    can_reach_end: set[str]


def append_flowchart_health(graph, compiled, state, *, registry, owner: str = "pipeline", visited_nodesets: set[str] | None = None) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    active_nodes = [node for node in graph.nodes if _node_participates_in_flow(graph, node)]
    if not active_nodes:
        return
    active_names = {node.name for node in active_nodes}
    incoming, outgoing, outgoing_edges, incoming_edges = _flow_maps(compiled, active_names)
    starts = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not incoming[name]}
    ends = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not outgoing[name]}
    _append_boundary_findings(starts, ends, state, owner=owner)
    _append_reachability_findings(starts, active_names, incoming_edges, outgoing_edges, outgoing, state, owner=owner)
    can_reach_end = _append_end_reachability_findings(ends, active_names, incoming_edges, outgoing_edges, incoming, state, owner=owner)
    if ends:
        decision_flow = _DecisionFlow(registry, outgoing, outgoing_edges, incoming_edges, can_reach_end)
        _append_decision_branch_health(graph, compiled, state, decision_flow, owner=owner)
    _append_explicit_edge_duplicate_warnings(graph, state, owner=owner)
    _append_orphan_findings(active_names, incoming_edges, outgoing_edges, incoming, outgoing, state, owner=owner)
    _append_nodeset_flow_health(graph, state, registry=registry, visited_nodesets=visited_nodesets)


def _flow_maps(compiled, active_names: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[object]], dict[str, list[object]]]:
    incoming = {name: [] for name in active_names}
    outgoing = {name: [] for name in active_names}
    outgoing_edges = {name: [] for name in active_names}
    incoming_edges = {name: [] for name in active_names}
    for edge in getattr(compiled, "schedule_edges", ()) or compiled.effective_edges:
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
    incoming_edges: dict[str, list[object]] = {node.name: [] for node in graph.nodes}
    for edge in getattr(compiled, "schedule_edges", ()) or compiled.effective_edges:
        incoming_edges.setdefault(edge.target, []).append(edge)
    for node in graph.nodes:
        if node.join_policy == JOIN_POLICY_ALL:
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


def _append_decision_branch_health(graph, compiled, state, flow: _DecisionFlow, *, owner: str) -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    for node in graph.nodes:
        if node.status == STATUS_PLANNED or compiled.flow_kinds.get(node.name) != FLOW_KIND_DECISION:
            continue
        _append_single_decision_health(node, nodes_by_name, state, flow, owner=owner)


def _append_single_decision_health(node, nodes_by_name, state, flow: _DecisionFlow, *, owner: str) -> None:
    schema_values = _decision_schema_values(node, flow.registry)
    equality_values: set[object] = set()
    for edge in flow.outgoing_edges.get(node.name, ()):
        parsed = _parse_when(getattr(edge, "when", ""))
        if parsed is not None:
            equality_values.update(_validate_branch_value(node, parsed, schema_values, state, owner=owner, flow=flow))
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
    _append_missing_schema_branches(node, schema_values, equality_values, state, owner=owner, flow=flow)


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


def _validate_branch_value(node, parsed: tuple[str, str, object], schema_values: set[object] | None, state, *, owner: str, flow: _DecisionFlow) -> set[object]:
    key, operator, literal = parsed
    if operator != "==":
        return set()
    if schema_values is not None and literal not in schema_values:
        state.errors.append(
            _flow_finding(
                "GRAPH.DECISION.UNKNOWN_BRANCH_VALUE",
                node.name,
                f"decision node '{node.name}' has branch {key} == {literal!r}, not declared in output_schema",
                object_type="node",
                details={
                    **_node_flow_details(owner, node.name, flow.incoming_edges, flow.outgoing_edges),
                    "branch_key": key,
                    "branch_value": literal,
                    "declared_values": sorted(schema_values, key=str),
                },
            )
        )
    return {literal}


def _append_missing_schema_branches(node, schema_values: set[object] | None, equality_values: set[object], state, *, owner: str, flow: _DecisionFlow) -> None:
    if schema_values is None or not equality_values:
        return
    missing = schema_values - equality_values
    if missing:
        state.errors.append(
            _flow_finding(
                "GRAPH.DECISION.MISSING_BRANCH_VALUE",
                node.name,
                f"decision node '{node.name}' has no outgoing branch for schema values: {sorted(missing)!r}",
                object_type="node",
                details={
                    **_node_flow_details(owner, node.name, flow.incoming_edges, flow.outgoing_edges),
                    "declared_values": sorted(schema_values, key=str),
                    "covered_values": sorted(equality_values, key=str),
                    "missing_values": sorted(missing, key=str),
                },
            )
        )


def _is_loop_branch(node_name: str, target: str, outgoing: dict[str, list[str]]) -> bool:
    return node_name in _walk({target}, outgoing)


def _decision_schema_values(node: Any, registry) -> set[object] | None:
    try:
        node_cls = registry.get(node.type_used)
    except Exception:
        return None
    contract = getattr(node_cls, "CONTRACT", None)
    schema = getattr(contract, "output_schema", None)
    if not isinstance(schema, Mapping):
        return None
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
    return values or None


def _parse_when(expression: str) -> tuple[str, str, object] | None:
    if not expression:
        return None
    for operator in ("==", "!="):
        if operator not in expression:
            continue
        left, right = (part.strip() for part in expression.split(operator, 1))
        if not left or not right:
            return None
        return left, operator, _literal_value(right)
    return None


def _literal_value(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


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
