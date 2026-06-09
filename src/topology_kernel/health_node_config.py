from __future__ import annotations

from typing import Mapping

from .graph_config import GraphConfig, NodeSpec, NodesetSpec
from .health_types import HealthFinding
from .registry import NodeRegistry, NodeRegistryError


def validate_node_config_health(graph: GraphConfig, *, registry: NodeRegistry) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    _validate_graph_node_configs(graph, registry=registry, findings=findings, owner="pipeline")
    for nodeset in graph.nodesets.values():
        _validate_graph_node_configs(nodeset.graph, registry=registry, findings=findings, owner=f"nodeset:{nodeset.name}")
    _validate_nodeset_override_paths(graph, registry=registry, findings=findings)
    return tuple(findings)


def _validate_graph_node_configs(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
    owner: str,
) -> None:
    for node in graph.nodes:
        if node.node_type.startswith("nodeset."):
            continue
        _append_node_config_finding(node, registry=registry, findings=findings, owner=owner)


def _append_node_config_finding(
    node: NodeSpec,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
    owner: str,
) -> None:
    try:
        registry.merge_config(node.node_type, node.params)
    except NodeRegistryError as exc:
        findings.append(
            _node_config_finding(
                "NODE.CONFIG.INVALID",
                node.name,
                str(exc),
                details={"node_type": node.node_type, "owner": owner, "params": dict(node.params)},
            )
        )


def _validate_nodeset_override_paths(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    for node in graph.nodes:
        if node.node_type.startswith("nodeset."):
            nodeset_name = node.node_type.removeprefix("nodeset.")
            nodeset = graph.nodesets.get(nodeset_name)
            if nodeset is None:
                continue
            _validate_override_map(node.name, nodeset, node.node_config_overrides, registry=registry, findings=findings)
    for nodeset in graph.nodesets.values():
        _validate_nodeset_override_paths(nodeset.graph, registry=registry, findings=findings)


def _validate_override_map(
    caller_name: str,
    nodeset: NodesetSpec,
    overrides: Mapping[str, Mapping[str, object]],
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    nodes_by_name = {node.name: node for node in nodeset.graph.nodes}
    for path, value in overrides.items():
        _validate_override_path(caller_name, nodeset, str(path), dict(value), nodes_by_name, registry=registry, findings=findings)


def _validate_override_path(
    caller_name: str,
    nodeset: NodesetSpec,
    path: str,
    value: dict[str, object],
    nodes_by_name: dict[str, NodeSpec],
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    head, sep, tail = path.partition(".")
    target = nodes_by_name.get(head)
    if target is None:
        findings.append(_node_config_finding("NODESET.CONFIG.UNKNOWN_NODE", caller_name, f"nodeset override references unknown node: {path}", details={"nodeset": nodeset.name, "path": path}))
        return
    if not sep:
        _validate_direct_override(caller_name, target, value, nodeset=nodeset, registry=registry, findings=findings)
        return
    if not target.node_type.startswith("nodeset."):
        findings.append(_node_config_finding("NODESET.CONFIG.INVALID_PATH", caller_name, f"override path passes through non-nodeset node: {path}", details={"nodeset": nodeset.name, "path": path}))
        return
    child = nodeset.graph.nodesets.get(target.node_type.removeprefix("nodeset."))
    if child is None:
        return
    _validate_override_map(caller_name, child, {tail: value}, registry=registry, findings=findings)


def _validate_direct_override(
    caller_name: str,
    target: NodeSpec,
    value: dict[str, object],
    *,
    nodeset: NodesetSpec,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    if target.node_type.startswith("nodeset."):
        findings.append(_node_config_finding("NODESET.CONFIG.NESTED_PATH_REQUIRED", caller_name, f"override for nested nodeset must use a dotted path: {target.name}", details={"nodeset": nodeset.name, "node": target.name}))
        return
    try:
        registry.merge_config(target.node_type, {**target.params, **value})
    except NodeRegistryError as exc:
        findings.append(_node_config_finding("NODESET.CONFIG.INVALID", caller_name, str(exc), details={"nodeset": nodeset.name, "node": target.name, "node_type": target.node_type}))


def _node_config_finding(
    rule_id: str,
    object_id: str,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="node",
        object_id=object_id,
        failure_layer="config",
        message=message,
        suggested_fix_type="fix_config",
        details=dict(details or {}),
    )
