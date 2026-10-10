from __future__ import annotations

from typing import Mapping

from vibeflow.core.flow import (
    GraphConfig,
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    STATUS_PLANNED,
)
from vibeflow.core.findings import HealthFinding
from vibeflow.core.contracts import provider_keys, providers_to_dicts, requirement_types, requirements_to_dicts
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError


def current_nodeset_declaration_findings(graph, *, definition, registry, owner):
    """Declaration belongs to its own graph; parent owns external call contracts."""
    findings = list(_validate_nodeset_usages(graph.nodes, graph.nodesets, owner=owner))
    if definition is not None and definition.status != STATUS_PLANNED:
        findings.extend(_validate_nodeset_metadata(definition))
        findings.extend(_validate_nodeset_contract(definition))
        findings.extend(_validate_nodeset_key_scope(definition))
    if registry is not None:
        findings.extend(_validate_node_types_in_scope(graph.nodes, graph.nodesets, registry=registry, owner=owner))
    return tuple(findings)


def _validate_node_types_in_scope(nodes, nodesets, *, registry: NodeRegistry, owner: str) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.type_used in LOOP_NODE_TYPES or node.type_used == IO_NODE_TYPE:
            continue
        if node.type_used in nodesets:
            continue
        try:
            registry.descriptor(node.type_used)
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

__all__ = [
    "current_nodeset_declaration_findings",
]
