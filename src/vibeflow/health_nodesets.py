from __future__ import annotations

from typing import Mapping

from .compiler import GraphCompiler, GraphCompileError
from .graph_config import GraphConfig, LOOP_NODE_TYPES, STATUS_PLANNED
from .health_types import HealthFinding
from .data_contract import provider_keys, providers_to_dicts, requirement_types, requirements_to_dicts
from .registry import NodeRegistry, NodeRegistryError


def validate_nodesets(graph: GraphConfig, *, registry: NodeRegistry) -> tuple[tuple[HealthFinding, ...], tuple[HealthFinding, ...]]:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    references = _nodeset_references(graph)
    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        errors.extend(_validate_nodeset_metadata(nodeset))
        errors.extend(_validate_nodeset_contract(nodeset))
        errors.extend(_validate_nodeset_key_scope(nodeset))
        try:
            GraphCompiler().compile(nodeset.graph, owner=f"nodeset:{nodeset.name}")
        except GraphCompileError as exc:
            errors.append(
                _nodeset_finding(
                    "NODESET.GRAPH.COMPILE",
                    nodeset.name,
                    f"nodeset internal graph failed to compile: {exc}",
                    details={"compile_error": str(exc), "compile_rule_id": exc.rule_id, **dict(exc.details or {})},
                )
            )
        errors.extend(_validate_node_types_in_scope(nodeset.graph.nodes, graph.nodesets, registry=registry, owner=f"nodeset:{nodeset.name}"))
        for ref_name in references.get(nodeset.name, ()):
            if ref_name not in graph.nodesets:
                errors.append(
                    _nodeset_finding(
                        "NODESET.REFERENCE.UNKNOWN",
                        nodeset.name,
                        f"nodeset references unknown nested nodeset: {ref_name}",
                        details={"referenced_nodeset": ref_name},
                    )
                )
    for cycle in _nodeset_cycles(references):
        errors.append(
            _nodeset_finding(
                "NODESET.RECURSION",
                cycle[0],
                "nodeset recursion is forbidden: " + " -> ".join(cycle),
                details={"cycle": cycle},
            )
        )
    errors.extend(_validate_nodeset_usages(graph.nodes, graph.nodesets, owner="pipeline"))
    for nodeset in graph.nodesets.values():
        errors.extend(_validate_nodeset_usages(nodeset.graph.nodes, graph.nodesets, owner=f"nodeset:{nodeset.name}"))
    return tuple(errors), tuple(warnings)


def append_nodeset_finding(
    target: list[HealthFinding],
    grouped: dict[str, list[dict[str, object]]],
    finding: HealthFinding,
) -> None:
    target.append(finding)
    nodeset_name = str(finding.details.get("nodeset", finding.object_id))
    grouped.setdefault(nodeset_name, []).append(finding.to_dict())


def _validate_node_types_in_scope(nodes, nodesets, *, registry: NodeRegistry, owner: str) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.node_type in LOOP_NODE_TYPES:
            continue
        if node.node_type.startswith("nodeset."):
            continue
        try:
            registry.get(node.node_type)
        except NodeRegistryError as exc:
            findings.append(
                HealthFinding(
                    rule_id="NODE.TYPE.UNKNOWN",
                    severity="error",
                    object_type="node",
                    object_id=node.name,
                    failure_layer="topology",
                    message=str(exc),
                    suggested_fix_type="fix_config",
                    details={"node_type": node.node_type, "owner": owner},
                )
            )
    return tuple(findings)


def _validate_nodeset_usages(nodes, nodesets, *, owner: str) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if not node.node_type.startswith("nodeset."):
            continue
        nodeset_name = node.node_type.removeprefix("nodeset.")
        nodeset = nodesets.get(nodeset_name)
        if nodeset is None:
            findings.append(
                _nodeset_finding(
                    "NODESET.REFERENCE.UNKNOWN",
                    nodeset_name,
                    f"pipeline node references unknown nodeset: {nodeset_name}",
                    object_type="node",
                    object_id=node.name,
                    details={"nodeset": nodeset_name, "owner": owner},
                )
            )
            continue
        if set(node.requires) != set(nodeset.requires):
            findings.append(
                _nodeset_finding(
                    "NODESET.CONTRACT.EXTERNAL_MISMATCH",
                    nodeset.name,
                    f"nodeset node '{node.name}' requires must match nodeset requires",
                    object_type="node",
                    object_id=node.name,
                    details={"expected_requires": requirements_to_dicts(nodeset.requires), "actual_requires": requirements_to_dicts(node.requires), "owner": owner},
                )
            )
        if set(node.provides) != set(nodeset.provides):
            findings.append(
                _nodeset_finding(
                    "NODESET.CONTRACT.EXTERNAL_MISMATCH",
                    nodeset.name,
                    f"nodeset node '{node.name}' provides must match nodeset provides",
                    object_type="node",
                    object_id=node.name,
                    details={"expected_provides": providers_to_dicts(nodeset.provides), "actual_provides": providers_to_dicts(node.provides), "owner": owner},
                )
            )
    return tuple(findings)


def _validate_nodeset_metadata(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for field_name in ("name", "display_name", "category", "description", "version", "purity"):
        if not str(getattr(nodeset, field_name, "")).strip():
            findings.append(_nodeset_finding("NODESET.METADATA.MISSING", nodeset.name, f"nodeset.{field_name} must be non-empty", details={"field": field_name}))
    if getattr(nodeset, "purity", "") != "pure":
        findings.append(_nodeset_finding("NODESET.METADATA.PURITY", nodeset.name, "nodeset.purity must be 'pure'"))
    return tuple(findings)


def _validate_nodeset_contract(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    if len(set(requirement_types(nodeset.requires))) != len(nodeset.requires):
        findings.append(_nodeset_finding("NODESET.CONTRACT.REQUIRES", nodeset.name, "nodeset.requires must contain unique non-empty types"))
    for field_name in ("provides", "exports"):
        values = provider_keys(getattr(nodeset, field_name, ()))
        if any(not value.strip() for value in values) or len(set(values)) != len(values):
            findings.append(_nodeset_finding("NODESET.CONTRACT.KEYS", nodeset.name, f"nodeset.{field_name} must contain unique non-empty keys", details={"field": field_name}))
    if not nodeset.provides:
        findings.append(_nodeset_finding("NODESET.CONTRACT.PROVIDES", nodeset.name, "nodeset.provides must declare at least one output key"))
    if not nodeset.exports:
        findings.append(_nodeset_finding("NODESET.CONTRACT.EXPORTS", nodeset.name, "nodeset.exports must declare at least one exported key"))
    if not set(provider_keys(nodeset.exports)) <= set(provider_keys(nodeset.provides)):
        findings.append(
            _nodeset_finding(
                "NODESET.CONTRACT.EXPORTS_NOT_PROVIDES",
                nodeset.name,
                "nodeset.exports must be a subset of nodeset.provides",
                details={"exports": providers_to_dicts(nodeset.exports), "provides": providers_to_dicts(nodeset.provides)},
            )
        )
    return tuple(findings)


def _validate_nodeset_key_scope(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    internal_provided = {provider.key for node in nodeset.graph.nodes for provider in node.provides}
    internal_required = {requirement.type for node in nodeset.graph.nodes for requirement in node.requires}
    export_keys = set(provider_keys(nodeset.exports))
    provide_keys = set(provider_keys(nodeset.provides))
    if not export_keys <= internal_provided:
        findings.append(
            _nodeset_finding(
                "NODESET.EXPORT.UNKNOWN_KEY",
                nodeset.name,
                "nodeset exports keys not produced internally",
                details={"missing_exports": sorted(export_keys - internal_provided)},
            )
        )
    if not provide_keys <= export_keys:
        findings.append(
            _nodeset_finding(
                "NODESET.KEY_LEAK",
                nodeset.name,
                "nodeset.provides must not expose keys outside exports",
                details={"leaked_keys": sorted(provide_keys - export_keys)},
            )
        )
    external_inputs = {provider.type for provider in nodeset.graph.inputs} | (internal_required - {provider.type for node in nodeset.graph.nodes for provider in node.provides})
    declared_inputs = set(requirement_types(nodeset.requires))
    if not external_inputs <= declared_inputs:
        findings.append(
            _nodeset_finding(
                "NODESET.INPUT_SCOPE",
                nodeset.name,
                "nodeset internal inputs must be declared in nodeset.requires",
                details={"undeclared_inputs": sorted(external_inputs - declared_inputs)},
            )
        )
    internal_only = internal_provided - export_keys
    leaked = internal_only & provide_keys
    if leaked:
        findings.append(_nodeset_finding("NODESET.INTERNAL_KEY_LEAK", nodeset.name, "nodeset internal intermediate keys must not leak through provides", details={"leaked_keys": sorted(leaked)}))
    return tuple(findings)


def _nodeset_references(graph: GraphConfig) -> dict[str, tuple[str, ...]]:
    refs: dict[str, tuple[str, ...]] = {}
    for name, nodeset in graph.nodesets.items():
        targets: list[str] = []
        for node in nodeset.graph.nodes:
            if node.node_type.startswith("nodeset."):
                targets.append(node.node_type.removeprefix("nodeset."))
            elif node.node_type in LOOP_NODE_TYPES and node.loop.body:
                targets.append(node.loop.body)
        refs[name] = tuple(sorted(set(targets)))
    return refs


def _nodeset_cycles(references: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    cycles: list[tuple[str, ...]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def dfs(name: str) -> None:
        if name in visiting:
            cycle = tuple((*visiting[visiting.index(name) :], name))
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if name in visited:
            return
        visiting.append(name)
        for child in references.get(name, ()):
            if child in references:
                dfs(child)
        visiting.pop()
        visited.add(name)

    for name in sorted(references):
        dfs(name)
    return tuple(cycles)


def _nodeset_finding(
    rule_id: str,
    nodeset_name: str,
    message: str,
    *,
    object_type: str = "nodeset",
    object_id: str | None = None,
    details: Mapping[str, object] | None = None,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=object_type,
        object_id=object_id or nodeset_name,
        failure_layer="topology",
        message=message,
        suggested_fix_type="fix_nodeset",
        details={"nodeset": nodeset_name, **dict(details or {})},
    )
