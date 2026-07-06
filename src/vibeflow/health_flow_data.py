from __future__ import annotations

from typing import Mapping

from .data_contract import CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE
from .graph_config import JOIN_POLICY_ALL, STATUS_PLANNED
from .health_types import HealthFinding
from .node import FLOW_KIND_TERMINAL

def append_data_contract_warnings(graph, compiled, state, *, owner: str = "pipeline") -> None:
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
        _append_missing_provider_warnings(node, graph, nodes_by_name, incoming, state, owner=owner)
        _append_unconsumed_provider_warnings(node, compiled, nodes_by_name, outgoing, condition_keys_by_source, state, owner=owner)

def _append_nodeset_flow_health(graph, state, *, registry, visited_nodesets: set[str]) -> None:
    from .compiler import GraphCompiler, GraphCompileError
    from .health_flow import append_flowchart_health, append_join_policy_health

    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        try:
            nested = GraphCompiler().compile(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.type_key}")
        except GraphCompileError:
            continue
        append_flowchart_health(nodeset.graph, nested, state, registry=registry, owner=f"nodeset:{nodeset.type_key}", visited_nodesets=visited_nodesets)
        append_data_contract_warnings(nodeset.graph, nested, state, owner=f"nodeset:{nodeset.type_key}")
        append_join_policy_health(nodeset.graph, nested, state, owner=f"nodeset:{nodeset.type_key}")

def _append_missing_provider_warnings(node, graph, nodes_by_name, incoming, state, *, owner: str) -> None:
    direct = [nodes_by_name[name] for name in incoming.get(node.name, ()) if name in nodes_by_name]
    input_types = {item.type for item in graph.inputs} if _is_initial_input_node(node, graph, incoming, nodes_by_name) else set()
    direct_source_details = _provider_source_details(direct)
    direct_provider_types = sorted({provider["type"] for source in direct_source_details for provider in source["provides"]})
    for requirement in node.requires:
        matches = [provider for parent in direct for provider in parent.provides if provider.type == requirement.type]
        if requirement.type in input_types:
            matches.append(None)
        base_details = {
            "owner": owner,
            "required_type": requirement.type,
            "required_cardinality": requirement.cardinality,
            "direct_sources": [source["node"] for source in direct_source_details],
            "direct_source_providers": direct_source_details,
            "available_provider_types": direct_provider_types,
            "entry_input_types": sorted(input_types),
        }
        if not matches:
            state.errors.append(
                _data_finding(
                    "GRAPH.DATA.MISSING_DIRECT_PROVIDER",
                    requirement.type,
                    f"node '{node.name}' requires type '{requirement.type}' but no direct incoming flow predecessor or entry input provides it",
                    node=node.name,
                    severity="error",
                    details=base_details,
                )
            )
            continue
        if requirement.cardinality in {CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE} and len(matches) > 1:
            matched_sources = [_source_name(item, direct) for item in matches]
            if _sources_are_mutually_exclusive(matched_sources, graph):
                continue
            finding = _data_finding(
                "GRAPH.DATA.TYPE_CARDINALITY_AMBIGUOUS",
                requirement.type,
                f"node '{node.name}' requires type '{requirement.type}' with {requirement.cardinality} but {len(matches)} direct sources may provide it",
                node=node.name,
                details={**base_details, "matched_sources": matched_sources},
            )
            if _sources_are_cyclic_alternatives(node.name, matched_sources, graph):
                state.warnings.append(finding)
            elif _direct_sources_are_unconditional(node.name, incoming.get(node.name, ()), graph):
                state.errors.append(_replace_severity(finding, "error"))
            else:
                state.warnings.append(finding)

def _append_unconsumed_provider_warnings(node, compiled, nodes_by_name, outgoing, condition_keys_by_source, state, *, owner: str) -> None:
    downstream = [nodes_by_name[name] for name in outgoing.get(node.name, ()) if name in nodes_by_name]
    is_end = compiled.flow_kinds.get(node.name) == FLOW_KIND_TERMINAL and not outgoing.get(node.name)
    if is_end:
        return
    downstream_required_types = {
        child.name: sorted({requirement.type for requirement in child.requires})
        for child in downstream
    }
    for provider in node.provides:
        if provider.key in condition_keys_by_source.get(node.name, set()):
            continue
        if not any(provider.type == requirement.type for child in downstream for requirement in child.requires):
            state.warnings.append(
                _data_finding(
                    "GRAPH.DATA.UNCONSUMED_PROVIDER",
                    provider.key,
                    f"node '{node.name}' provides key '{provider.key}' type '{provider.type}' but no direct downstream flow successor requires that type",
                    node=node.name,
                    details={
                        "owner": owner,
                        "provider_key": provider.key,
                        "provider_type": provider.type,
                        "downstream_nodes": sorted(outgoing.get(node.name, ())),
                        "downstream_required_types": downstream_required_types,
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

def _is_initial_input_node(node, graph, incoming, nodes_by_name) -> bool:
    if not node.requires:
        return False
    parents = [nodes_by_name[name] for name in incoming.get(node.name, ()) if name in nodes_by_name]
    if not parents:
        return True
    return any(not parent.requires and not parent.provides for parent in parents)

def _direct_sources_are_unconditional(node_name: str, sources: list[str], graph) -> bool:
    relevant = [edge for edge in graph.edges if edge.target == node_name and edge.source in sources]
    return bool(relevant) and all(not edge.when for edge in relevant)

def _sources_are_mutually_exclusive(sources: list[str], graph) -> bool:
    source_set = set(sources)
    if len(source_set) != len(sources) or len(source_set) <= 1 or "pipeline.input" in source_set:
        return False
    by_decision: dict[tuple[str, str], dict[str, set[object]]] = {}
    for source in source_set:
        for edge in graph.edges:
            if edge.target != source or not edge.when:
                continue
            parsed = _parse_when(edge.when)
            if parsed is None:
                continue
            key, operator, value = parsed
            if operator != "==":
                continue
            by_decision.setdefault((edge.source, key), {}).setdefault(source, set()).add(value)
    for by_source in by_decision.values():
        if set(by_source) != source_set:
            continue
        values = {value for source_values in by_source.values() for value in source_values}
        if len(values) >= len(source_set):
            return True
    return False

def _sources_are_cyclic_alternatives(node_name: str, sources: list[str], graph) -> bool:
    source_set = {source for source in sources if source != "pipeline.input"}
    if not source_set:
        return False
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source, []).append(edge.target)
    reachable_from_node = _walk({node_name}, outgoing)
    return any(source in reachable_from_node and node_name in _walk({source}, outgoing) for source in source_set)

def _source_name(provider, direct) -> str:
    if provider is None:
        return "pipeline.input"
    for node in direct:
        if provider in node.provides:
            return node.name
    return str(getattr(provider, "key", provider))

def _provider_source_details(nodes) -> list[dict[str, object]]:
    return [
        {
            "node": node.name,
            "provides": [
                {
                    "key": provider.key,
                    "type": provider.type,
                }
                for provider in node.provides
            ],
        }
        for node in nodes
    ]

def _replace_severity(finding: HealthFinding, severity: str) -> HealthFinding:
    return HealthFinding(
        rule_id=finding.rule_id,
        severity=severity,
        object_type=finding.object_type,
        object_id=finding.object_id,
        source_location=finding.source_location,
        rule_source=finding.rule_source,
        failure_layer=finding.failure_layer,
        message=finding.message,
        suggested_fix_type=finding.suggested_fix_type,
        details=finding.details,
    )

def _data_finding(rule_id: str, key: str, message: str, *, node: str, severity: str = "warning", details: Mapping[str, object] | None = None) -> HealthFinding:
    payload = {"node": node}
    if details:
        payload.update(details)
    return HealthFinding(rule_id=rule_id, severity=severity, object_type="contract_key", object_id=key, failure_layer="topology", message=message, suggested_fix_type="fix_config", details=payload)


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
