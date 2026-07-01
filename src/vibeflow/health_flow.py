from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .graph_algorithms import strongly_connected_components
from .graph_config import STATUS_PLANNED
from .health_types import HealthFinding
from .node import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL


@dataclass(frozen=True)
class _DecisionFlow:
    registry: object
    outgoing: dict[str, list[str]]
    outgoing_edges: dict[str, list[object]]
    can_reach_end: set[str]


def append_flowchart_health(graph, compiled, state, *, registry, owner: str = "pipeline") -> None:
    active_nodes = [node for node in graph.nodes if node.status != STATUS_PLANNED]
    if not active_nodes:
        return
    active_names = {node.name for node in active_nodes}
    incoming, outgoing, outgoing_edges = _flow_maps(compiled, active_names)
    starts = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not incoming[name]}
    ends = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not outgoing[name]}
    _append_boundary_findings(starts, ends, state, owner=owner)
    _append_reachability_findings(starts, active_names, outgoing, state)
    can_reach_end = _append_end_reachability_findings(ends, active_names, incoming, state)
    if ends:
        decision_flow = _DecisionFlow(registry, outgoing, outgoing_edges, can_reach_end)
        _append_decision_branch_health(graph, compiled, state, decision_flow)
        _append_decision_cycle_exit_health(compiled, state, outgoing=outgoing, can_reach_end=can_reach_end)
    _append_explicit_edge_duplicate_warnings(graph, state)
    _append_orphan_findings(active_names, incoming, outgoing, state)
    _append_nodeset_flow_health(graph, state, registry=registry)


def _flow_maps(compiled, active_names: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[object]]]:
    incoming = {name: [] for name in active_names}
    outgoing = {name: [] for name in active_names}
    outgoing_edges = {name: [] for name in active_names}
    for edge in compiled.effective_edges:
        if edge.source not in active_names or edge.target not in active_names:
            continue
        outgoing[edge.source].append(edge.target)
        outgoing_edges[edge.source].append(edge)
        incoming[edge.target].append(edge.source)
    return incoming, outgoing, outgoing_edges


def _append_boundary_findings(starts: set[str], ends: set[str], state, *, owner: str) -> None:
    if not starts:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_START", owner, "graph must have a terminal start node with no incoming flow edge"))
    if not ends:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_END", owner, "graph must have a terminal end node with no outgoing flow edge"))


def _append_reachability_findings(starts: set[str], active_names: set[str], outgoing: dict[str, list[str]], state) -> None:
    if not starts:
        return
    reachable = _walk(starts, outgoing)
    for name in sorted(active_names - reachable):
        state.errors.append(_flow_finding("GRAPH.FLOW.UNREACHABLE_FROM_START", name, f"node '{name}' is not reachable from a start node", object_type="node"))


def _append_end_reachability_findings(ends: set[str], active_names: set[str], incoming: dict[str, list[str]], state) -> set[str]:
    if not ends:
        return set()
    can_reach_end = _walk(ends, incoming)
    for name in sorted(active_names - can_reach_end):
        state.errors.append(_flow_finding("GRAPH.FLOW.CANNOT_REACH_END", name, f"node '{name}' cannot reach an end node", object_type="node"))
    return can_reach_end


def _append_orphan_findings(active_names: set[str], incoming: dict[str, list[str]], outgoing: dict[str, list[str]], state) -> None:
    if len(active_names) <= 1:
        return
    for name in sorted(active_names):
        if not incoming[name] and not outgoing[name]:
            state.errors.append(_flow_finding("GRAPH.FLOW.ORPHAN_NODE", name, f"node '{name}' has no flow edges", object_type="node"))


def append_data_contract_warnings(graph, compiled, state) -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    incoming = {node.name: [] for node in graph.nodes}
    outgoing = {node.name: [] for node in graph.nodes}
    for edge in compiled.effective_edges:
        incoming.setdefault(edge.target, []).append(edge.source)
        outgoing.setdefault(edge.source, []).append(edge.target)
    condition_keys_by_source: dict[str, set[str]] = {node.name: set() for node in graph.nodes}
    for edge in compiled.effective_edges:
        parsed = _parse_when(edge.when)
        if parsed is not None:
            condition_keys_by_source.setdefault(edge.source, set()).add(parsed[0])
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            continue
        _append_missing_provider_warnings(node, graph, nodes_by_name, incoming, state)
        _append_unconsumed_provider_warnings(node, compiled, nodes_by_name, outgoing, condition_keys_by_source, state)


def _append_nodeset_flow_health(graph, state, *, registry) -> None:
    from .compiler import GraphCompiler, GraphCompileError

    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        try:
            nested = GraphCompiler().compile(nodeset.graph, registry=registry)
        except GraphCompileError:
            continue
        append_flowchart_health(nodeset.graph, nested, state, registry=registry, owner=f"nodeset:{nodeset.name}")


def _append_missing_provider_warnings(node, graph, nodes_by_name, incoming, state) -> None:
    upstream_names = _walk(set(incoming.get(node.name, ())), incoming)
    upstream = [nodes_by_name[name] for name in upstream_names if name in nodes_by_name]
    for key in node.requires:
        if key in graph.inputs:
            continue
        if not any(key in parent.provides for parent in upstream):
            state.warnings.append(_data_finding("GRAPH.DATA.MISSING_UPSTREAM_PROVIDER", key, f"node '{node.name}' requires '{key}' but no upstream flow predecessor provides it", node=node.name))


def _append_unconsumed_provider_warnings(node, compiled, nodes_by_name, outgoing, condition_keys_by_source, state) -> None:
    downstream_names = _walk(set(outgoing.get(node.name, ())), outgoing)
    downstream = [nodes_by_name[name] for name in downstream_names if name in nodes_by_name]
    is_end = compiled.flow_kinds.get(node.name) == FLOW_KIND_TERMINAL and not outgoing.get(node.name)
    if is_end:
        return
    for key in node.provides:
        if key in condition_keys_by_source.get(node.name, set()):
            continue
        if not any(key in child.requires for child in downstream):
            state.warnings.append(_data_finding("GRAPH.DATA.UNCONSUMED_PROVIDER", key, f"node '{node.name}' provides '{key}' but no downstream flow successor requires it", node=node.name))


def _append_decision_branch_health(graph, compiled, state, flow: _DecisionFlow) -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    for node in graph.nodes:
        if node.status == STATUS_PLANNED or compiled.flow_kinds.get(node.name) != FLOW_KIND_DECISION:
            continue
        _append_single_decision_health(node, nodes_by_name, state, flow)


def _append_single_decision_health(node, nodes_by_name, state, flow: _DecisionFlow) -> None:
    schema_values = _decision_schema_values(node, flow.registry)
    equality_values: set[object] = set()
    for edge in flow.outgoing_edges.get(node.name, ()):
        parsed = _parse_when(getattr(edge, "when", ""))
        if parsed is not None:
            equality_values.update(_validate_branch_value(node, parsed, schema_values, state))
        target = getattr(edge, "target", "")
        if target in nodes_by_name and not _is_loop_branch(node.name, target, flow.outgoing) and target not in flow.can_reach_end:
            state.errors.append(_flow_finding("GRAPH.DECISION.BRANCH_CANNOT_REACH_END", node.name, f"decision branch {node.name}->{target} cannot reach a terminal end node", object_type="node"))
    _append_missing_schema_branches(node, schema_values, equality_values, state)


def _append_decision_cycle_exit_health(compiled, state, *, outgoing: dict[str, list[str]], can_reach_end: set[str]) -> None:
    for component in strongly_connected_components(outgoing):
        if len(component) == 1 and component[0] not in outgoing.get(component[0], ()):
            continue
        cycle = set(component)
        decision_nodes = [node for node in component if compiled.flow_kinds.get(node) == FLOW_KIND_DECISION]
        for decision in decision_nodes:
            has_exit = any(target not in cycle and target in can_reach_end for target in outgoing.get(decision, ()))
            if not has_exit:
                state.errors.append(_flow_finding("GRAPH.CYCLE.MISSING_DECISION_EXIT", decision, f"decision cycle containing '{decision}' needs an exit edge from a decision node to a terminal end", object_type="node"))


def _append_explicit_edge_duplicate_warnings(graph, state) -> None:
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
                details={"conditions": sorted(conditions)},
            )
        )


def _validate_branch_value(node, parsed: tuple[str, str, object], schema_values: set[object] | None, state) -> set[object]:
    key, operator, literal = parsed
    if operator != "==":
        return set()
    if schema_values is not None and literal not in schema_values:
        state.errors.append(_flow_finding("GRAPH.DECISION.UNKNOWN_BRANCH_VALUE", node.name, f"decision node '{node.name}' has branch {key} == {literal!r}, not declared in output_schema", object_type="node"))
    return {literal}


def _append_missing_schema_branches(node, schema_values: set[object] | None, equality_values: set[object], state) -> None:
    if schema_values is None or not equality_values:
        return
    missing = schema_values - equality_values
    if missing:
        state.errors.append(_flow_finding("GRAPH.DECISION.MISSING_BRANCH_VALUE", node.name, f"decision node '{node.name}' has no outgoing branch for schema values: {sorted(missing)!r}", object_type="node"))


def _is_loop_branch(node_name: str, target: str, outgoing: dict[str, list[str]]) -> bool:
    return node_name in _walk({target}, outgoing)


def _decision_schema_values(node: Any, registry) -> set[object] | None:
    if node.node_type.startswith("nodeset."):
        return None
    try:
        node_cls = registry.get(node.node_type)
    except Exception:
        return None
    contract = getattr(node_cls, "CONTRACT", None)
    schema = getattr(contract, "output_schema", None)
    if not isinstance(schema, Mapping):
        return None
    values: set[object] = set()
    for key in node.provides:
        spec = schema.get(key)
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



def _flow_finding(rule_id: str, object_id: str, message: str, *, object_type: str = "pipeline") -> HealthFinding:
    return HealthFinding(rule_id=rule_id, severity="error", object_type=object_type, object_id=object_id, failure_layer="topology", message=message, suggested_fix_type="fix_config")


def _data_finding(rule_id: str, key: str, message: str, *, node: str) -> HealthFinding:
    return HealthFinding(rule_id=rule_id, severity="warning", object_type="contract_key", object_id=key, failure_layer="topology", message=message, suggested_fix_type="fix_config", details={"node": node})
