from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from .health_types import HealthFinding
from .registry import NodeRegistry, NodeRegistryError
from .runtime_config import ConfigScope, config_override_conflicts, merge_config_scopes, nested_node_config_overrides, node_invocation_scope, normalize_config_scope, scoped_node_params


@dataclass(frozen=True)
class _OverrideContext:
    caller_name: str
    nodeset: NodesetSpec
    nodes_by_name: dict[str, NodeSpec]
    registry: NodeRegistry
    findings: list[HealthFinding]


def validate_node_config_health(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    global_config: Mapping[str, object] | ConfigScope | None = None,
) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    called_nodesets: set[str] = set()
    _validate_graph_node_configs(
        graph,
        registry=registry,
        findings=findings,
        owner="pipeline",
        global_scope=normalize_config_scope(global_config),
        overrides={},
        called_nodesets=called_nodesets,
        stack=(),
    )
    for nodeset in graph.nodesets.values():
        if nodeset.name in called_nodesets:
            continue
        _validate_graph_node_configs(
            nodeset.graph,
            registry=registry,
            findings=findings,
            owner=f"nodeset:{nodeset.name}",
            global_scope=normalize_config_scope(nodeset.global_config),
            overrides={},
            called_nodesets=called_nodesets,
            stack=(nodeset.name,),
        )
    _validate_nodeset_override_paths(graph, registry=registry, findings=findings)
    return tuple(findings)


def _validate_graph_node_configs(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
    owner: str,
    global_scope: ConfigScope,
    overrides: Mapping[str, Mapping[str, object]],
    called_nodesets: set[str],
    stack: tuple[str, ...],
) -> None:
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.node_type.startswith("nodeset."):
            _validate_nodeset_call_config(node, graph, registry=registry, findings=findings, owner=owner, global_scope=global_scope, overrides=overrides, called_nodesets=called_nodesets, stack=stack)
            continue
        _append_node_config_finding(node, registry=registry, findings=findings, owner=owner, global_scope=global_scope, overrides=overrides)


def _append_node_config_finding(
    node: NodeSpec,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
    owner: str,
    global_scope: ConfigScope,
    overrides: Mapping[str, Mapping[str, object]],
) -> None:
    _append_override_warning(
        findings,
        rule_id="CONFIG.GLOBAL_CONFIG.OVERRIDES_LOCAL",
        object_id=node.name,
        message=f"global config overrides local node config: {node.name}",
        base=node.params,
        override=global_scope.values,
        allow=global_scope.allow_config_override,
        details={"owner": owner, "node_type": node.node_type},
    )
    try:
        config_spec = registry.get_config_spec(node.node_type)
        scoped_params = scoped_node_params(node.params, global_scope, declared_keys=set(config_spec.schema))
        registry.merge_config(node.node_type, {**scoped_params, **dict(overrides.get(node.name, {}))})
    except NodeRegistryError as exc:
        findings.append(
            _node_config_finding(
                "NODE.CONFIG.INVALID",
                node.name,
                str(exc),
                details={"node_type": node.node_type, "owner": owner, "params": dict(node.params), "global_config": dict(global_scope.values)},
            )
        )


def _validate_nodeset_call_config(
    node: NodeSpec,
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
    owner: str,
    global_scope: ConfigScope,
    overrides: Mapping[str, Mapping[str, object]],
    called_nodesets: set[str],
    stack: tuple[str, ...],
) -> None:
    nodeset_name = node.node_type.removeprefix("nodeset.")
    nodeset = graph.nodesets.get(nodeset_name)
    if nodeset is None or nodeset_name in stack:
        return
    called_nodesets.add(nodeset_name)
    _append_override_warning(
        findings,
        rule_id="CONFIG.GLOBAL_CONFIG.OVERRIDES_NODESET_CONFIG",
        object_id=node.name,
        message=f"global config overrides nodeset call config: {node.name}",
        base=node.params,
        override=global_scope.values,
        allow=global_scope.allow_config_override,
        details={"owner": owner, "nodeset": nodeset_name},
    )
    caller_values = {**dict(node.params), **dict(global_scope.values), **dict(overrides.get(node.name, {}))}
    caller_scope = node_invocation_scope(caller_values, allow_config_override=node.allow_config_override)
    internal_scope = normalize_config_scope(nodeset.global_config)
    _append_override_warning(
        findings,
        rule_id="NODESET.CONFIG.OVERRIDES_GLOBAL_CONFIG",
        object_id=node.name,
        message=f"nodeset call config overrides nodeset global_config: {node.name}",
        base=internal_scope.values,
        override=caller_scope.values,
        allow=caller_scope.allow_config_override,
        details={"owner": owner, "nodeset": nodeset_name},
    )
    child_scope = merge_config_scopes(internal_scope, caller_scope)
    _validate_graph_node_configs(
        nodeset.graph,
        registry=registry,
        findings=findings,
        owner=f"nodeset:{nodeset.name}",
        global_scope=child_scope,
        overrides=nested_node_config_overrides(node, overrides),
        called_nodesets=called_nodesets,
        stack=(*stack, nodeset_name),
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
    context = _OverrideContext(caller_name, nodeset, nodes_by_name, registry, findings)
    for path, value in overrides.items():
        _validate_override_path(str(path), dict(value), context)


def _validate_override_path(path: str, value: dict[str, object], context: _OverrideContext) -> None:
    head, sep, tail = path.partition(".")
    target = context.nodes_by_name.get(head)
    if target is None:
        context.findings.append(_node_config_finding("NODESET.CONFIG.UNKNOWN_NODE", context.caller_name, f"nodeset override references unknown node: {path}", details={"nodeset": context.nodeset.name, "path": path}))
        return
    if not sep:
        _validate_direct_override(context.caller_name, target, value, nodeset=context.nodeset, registry=context.registry, findings=context.findings)
        return
    if not target.node_type.startswith("nodeset."):
        context.findings.append(_node_config_finding("NODESET.CONFIG.INVALID_PATH", context.caller_name, f"override path passes through non-nodeset node: {path}", details={"nodeset": context.nodeset.name, "path": path}))
        return
    child = context.nodeset.graph.nodesets.get(target.node_type.removeprefix("nodeset."))
    if child is None:
        return
    _validate_override_map(context.caller_name, child, {tail: value}, registry=context.registry, findings=context.findings)


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
    if target.status == STATUS_PLANNED:
        return
    try:
        registry.merge_config(target.node_type, {**target.params, **value})
    except NodeRegistryError as exc:
        findings.append(_node_config_finding("NODESET.CONFIG.INVALID", caller_name, str(exc), details={"nodeset": nodeset.name, "node": target.name, "node_type": target.node_type}))


def _append_override_warning(
    findings: list[HealthFinding],
    *,
    rule_id: str,
    object_id: str,
    message: str,
    base: Mapping[str, object],
    override: Mapping[str, object],
    allow: bool,
    details: Mapping[str, object],
) -> None:
    conflicts = config_override_conflicts(base, override)
    if allow or not conflicts:
        return
    findings.append(
        HealthFinding(
            rule_id=rule_id,
            severity="warning",
            object_type="node",
            object_id=object_id,
            failure_layer="config",
            message=message,
            suggested_fix_type="review_config",
            details={**dict(details), "conflicts": conflicts},
        )
    )


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
