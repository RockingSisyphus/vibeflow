from __future__ import annotations

from typing import Mapping

from vibeflow.compiler import GraphCompiler, GraphCompileError
from vibeflow.graph_config import GraphConfig, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.graph_config.nodeset_dependencies import (
    analyze_nodeset_dependencies,
    nodeset_dependency_cycles,
    nodeset_depth_violations,
)
from vibeflow.health.types import HealthFinding, HealthReport
from vibeflow.data_contract import provider_keys, providers_to_dicts, requirement_types, requirements_to_dicts
from vibeflow.registry import NodeRegistry, NodeRegistryError


def validate_nodesets(graph: GraphConfig, *, registry: NodeRegistry) -> tuple[tuple[HealthFinding, ...], tuple[HealthFinding, ...]]:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    dependencies = analyze_nodeset_dependencies(graph)
    references = {
        name: tuple(sorted({dependency.target for dependency in items}))
        for name, items in dependencies.nodesets.items()
    }
    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        errors.extend(_validate_nodeset_metadata(nodeset))
        errors.extend(_validate_nodeset_contract(nodeset))
        errors.extend(_validate_nodeset_key_scope(nodeset))
        try:
            GraphCompiler().compile(nodeset.graph, owner=f"nodeset:{nodeset.type_key}")
        except GraphCompileError as exc:
            errors.append(
                _nodeset_finding(
                    "NODESET.GRAPH.COMPILE",
                    nodeset.type_key,
                    f"nodeset internal graph failed to compile: {exc}",
                    details={"compile_error": str(exc), "compile_rule_id": exc.rule_id, **dict(exc.details or {})},
                )
            )
        errors.extend(_validate_node_types_in_scope(nodeset.graph.nodes, graph.nodesets, registry=registry, owner=f"nodeset:{nodeset.type_key}"))
        for ref_name in references.get(nodeset.type_key, ()):
            if ref_name not in graph.nodesets:
                errors.append(
                    _nodeset_finding(
                        "NODESET.REFERENCE.UNKNOWN",
                        nodeset.type_key,
                        f"nodeset references unknown nested nodeset: {ref_name}",
                        details={"referenced_nodeset": ref_name},
                    )
                )
    for cycle in nodeset_dependency_cycles(dependencies):
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
        errors.extend(_validate_nodeset_usages(nodeset.graph.nodes, graph.nodesets, owner=f"nodeset:{nodeset.type_key}"))
    return tuple(errors), tuple(warnings)


def validate_nodeset_depth(graph: GraphConfig, *, max_depth: int) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for violation in nodeset_depth_violations(graph, max_depth=max_depth):
        chain_text = " -> ".join(violation.chain)
        findings.append(
            _nodeset_finding(
                "NODESET.NESTING.DEPTH_EXCEEDED",
                violation.chain[0],
                f"nodeset nesting depth {violation.actual_depth} exceeds configured maximum {max_depth}: {chain_text}",
                details=violation.to_details(),
            )
        )
    return tuple(findings)


def nodeset_depth_error_report(graph: GraphConfig, compiled, *, max_depth: int) -> HealthReport | None:
    findings = validate_nodeset_depth(graph, max_depth=max_depth)
    if not findings:
        return None
    grouped: dict[str, list[dict[str, object]]] = {}
    for finding in findings:
        grouped.setdefault(finding.object_id, []).append(finding.to_dict())
    return HealthReport(
        status="FAIL",
        errors=findings,
        info={
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "nodeset_findings": grouped,
        },
    )


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
        if node.type_used in LOOP_NODE_TYPES:
            continue
        if node.type_used in nodesets:
            continue
        try:
            registry.get(node.type_used)
        except NodeRegistryError as exc:
            findings.append(
                HealthFinding(
                    rule_id="NODE.TYPE.UNKNOWN",
                    severity="error",
                    object_type="node",
                    object_id=node.id,
                    failure_layer="topology",
                    message=str(exc),
                    suggested_fix_type="fix_config",
                    details={"type_used": node.type_used, "owner": owner},
                )
            )
    return tuple(findings)


def _validate_nodeset_usages(nodes, nodesets, *, owner: str) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.type_used not in nodesets:
            continue
        nodeset_name = node.type_used
        nodeset = nodesets.get(nodeset_name)
        if nodeset is None:
            findings.append(
                _nodeset_finding(
                    "NODESET.REFERENCE.UNKNOWN",
                    nodeset_name,
                    f"pipeline node references unknown nodeset: {nodeset_name}",
                    object_type="node",
                    object_id=node.id,
                    details={"nodeset": nodeset_name, "owner": owner},
                )
            )
            continue
        if set(node.requires) != set(nodeset.requires):
            findings.append(
                _nodeset_finding(
                    "NODESET.CONTRACT.EXTERNAL_MISMATCH",
                    nodeset.type_key,
                    f"nodeset node '{node.id}' requires must match nodeset requires",
                    object_type="node",
                    object_id=node.id,
                    details={"expected_requires": requirements_to_dicts(nodeset.requires), "actual_requires": requirements_to_dicts(node.requires), "owner": owner},
                )
            )
        if set(node.provides) != set(nodeset.provides):
            findings.append(
                _nodeset_finding(
                    "NODESET.CONTRACT.EXTERNAL_MISMATCH",
                    nodeset.type_key,
                    f"nodeset node '{node.id}' provides must match nodeset provides",
                    object_type="node",
                    object_id=node.id,
                    details={"expected_provides": providers_to_dicts(nodeset.provides), "actual_provides": providers_to_dicts(node.provides), "owner": owner},
                )
            )
    return tuple(findings)


def _validate_nodeset_metadata(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for field_name in ("type_key", "display_name", "description"):
        if not str(getattr(nodeset, field_name, "")).strip():
            findings.append(_nodeset_finding("NODESET.METADATA.MISSING", nodeset.type_key, f"nodeset.{field_name} must be non-empty", details={"field": field_name}))
    return tuple(findings)


def _validate_nodeset_contract(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    if len(set(requirement_types(nodeset.requires))) != len(nodeset.requires):
        findings.append(_nodeset_finding("NODESET.CONTRACT.REQUIRES", nodeset.type_key, "nodeset.requires must contain unique non-empty types"))
    for field_name in ("provides",):
        values = provider_keys(getattr(nodeset, field_name, ()))
        if any(not value.strip() for value in values) or len(set(values)) != len(values):
            findings.append(_nodeset_finding("NODESET.CONTRACT.KEYS", nodeset.type_key, f"nodeset.{field_name} must contain unique non-empty keys", details={"field": field_name}))
    if not nodeset.provides:
        findings.append(_nodeset_finding("NODESET.CONTRACT.PROVIDES", nodeset.type_key, "nodeset.provides must declare at least one output key"))
    return tuple(findings)


def _validate_nodeset_key_scope(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    internal_provided = {provider.key for node in nodeset.graph.nodes for provider in node.provides}
    internal_required = {requirement.type for node in nodeset.graph.nodes for requirement in node.requires}
    provide_keys = set(provider_keys(nodeset.provides))
    if not provide_keys <= internal_provided:
        findings.append(
            _nodeset_finding(
                "NODESET.PROVIDES.UNKNOWN_KEY",
                nodeset.type_key,
                "nodeset provides keys not produced internally",
                details={"missing_provides": sorted(provide_keys - internal_provided)},
            )
        )
    external_inputs = {provider.type for provider in nodeset.graph.inputs} | (internal_required - {provider.type for node in nodeset.graph.nodes for provider in node.provides})
    declared_inputs = set(requirement_types(nodeset.requires))
    if not external_inputs <= declared_inputs:
        findings.append(
            _nodeset_finding(
                "NODESET.INPUT_SCOPE",
                nodeset.type_key,
                "nodeset internal inputs must be declared in nodeset.requires",
                details={"undeclared_inputs": sorted(external_inputs - declared_inputs)},
            )
        )
    return tuple(findings)


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
