from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .graph_config import GraphConfig, LOOP_NODE_TYPES, NodeSpec, NodesetSpec, STATUS_PLANNED
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


@dataclass(frozen=True)
class _CompositeChild:
    kind: str
    type_key: str
    nodeset: NodesetSpec | None


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
        if nodeset.type_key in called_nodesets:
            continue
        _validate_graph_node_configs(
            nodeset.graph,
            registry=registry,
            findings=findings,
            owner=f"nodeset:{nodeset.type_key}",
            global_scope=normalize_config_scope(nodeset.global_config),
            overrides={},
            called_nodesets=called_nodesets,
            stack=(nodeset.type_key,),
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
        if node.type_used in LOOP_NODE_TYPES:
            _validate_nodeset_call_config(node, graph, registry=registry, findings=findings, owner=owner, global_scope=global_scope, overrides=overrides, called_nodesets=called_nodesets, stack=stack, nodeset_name=node.loop.body)
            continue
        if node.type_used in graph.nodesets:
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
        object_id=node.id,
        message=f"global config overrides local node config: {node.id}",
        base=node.params,
        override=global_scope.values,
        allow=global_scope.allow_config_override,
        details={"owner": owner, "type_used": node.type_used},
    )
    try:
        config_spec = registry.get_config_spec(node.type_used)
        scoped_params = scoped_node_params(node.params, global_scope, declared_keys=set(config_spec.schema))
        registry.merge_config(node.type_used, {**scoped_params, **dict(overrides.get(node.id, {}))})
    except NodeRegistryError as exc:
        findings.append(
            _node_config_finding(
                "NODE.CONFIG.INVALID",
                node.id,
                str(exc),
                details={"type_used": node.type_used, "owner": owner, "params": dict(node.params), "global_config": dict(global_scope.values)},
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
    nodeset_name: str | None = None,
) -> None:
    nodeset_name = nodeset_name or node.type_used
    nodeset = graph.nodesets.get(nodeset_name)
    if nodeset is None or nodeset_name in stack:
        return
    called_nodesets.add(nodeset_name)
    _append_override_warning(
        findings,
        rule_id="CONFIG.GLOBAL_CONFIG.OVERRIDES_NODESET_CONFIG",
        object_id=node.id,
        message=f"global config overrides nodeset call config: {node.id}",
        base=node.params,
        override=global_scope.values,
        allow=global_scope.allow_config_override,
        details={"owner": owner, "nodeset": nodeset_name},
    )
    caller_values = {**dict(node.params), **dict(global_scope.values), **dict(overrides.get(node.id, {}))}
    caller_scope = node_invocation_scope(caller_values, allow_config_override=node.allow_config_override)
    internal_scope = normalize_config_scope(nodeset.global_config)
    _append_override_warning(
        findings,
        rule_id="NODESET.CONFIG.OVERRIDES_GLOBAL_CONFIG",
        object_id=node.id,
        message=f"nodeset call config overrides nodeset global_config: {node.id}",
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
        owner=f"nodeset:{nodeset.type_key}",
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
    visited_nodesets: set[str] | None = None,
) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    for node in graph.nodes:
        child = _resolve_composite_child(node, graph)
        if child is not None:
            if child.nodeset is None:
                continue
            _validate_override_map(node.id, child.nodeset, node.node_config_overrides, registry=registry, findings=findings)
    for nodeset in graph.nodesets.values():
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        _validate_nodeset_override_paths(nodeset.graph, registry=registry, findings=findings, visited_nodesets=visited_nodesets)


def _validate_override_map(
    caller_name: str,
    nodeset: NodesetSpec,
    overrides: Mapping[str, Mapping[str, object]],
    *,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    nodes_by_name = {node.id: node for node in nodeset.graph.nodes}
    context = _OverrideContext(caller_name, nodeset, nodes_by_name, registry, findings)
    for path, value in overrides.items():
        _validate_override_path(str(path), dict(value), context)


def _validate_override_path(path: str, value: dict[str, object], context: _OverrideContext) -> None:
    head, sep, tail = path.partition(".")
    target = context.nodes_by_name.get(head)
    if target is None:
        context.findings.append(_node_config_finding("NODESET.CONFIG.UNKNOWN_NODE", context.caller_name, f"nodeset override references unknown node: {path}", details={"nodeset": context.nodeset.type_key, "path": path}))
        return
    if not sep:
        _validate_direct_override(context.caller_name, target, value, nodeset=context.nodeset, registry=context.registry, findings=context.findings)
        return
    child = _resolve_composite_child(target, context.nodeset.graph)
    if child is None:
        context.findings.append(
            _node_config_finding(
                "NODESET.CONFIG.INVALID_PATH",
                context.caller_name,
                f"override path passes through non-composite node: {path}",
                details={
                    "owner": f"nodeset:{context.nodeset.type_key}",
                    "nodeset": context.nodeset.type_key,
                    "path": path,
                    "node": target.id,
                    "type_used": target.type_used,
                    "composite_kind": "none",
                },
            )
        )
        return
    if child.nodeset is None:
        context.findings.append(
            _node_config_finding(
                "NODESET.CONFIG.INVALID_PATH",
                context.caller_name,
                f"override path passes through unresolved {child.kind} node: {path}",
                details=_override_path_details(context.nodeset, path, target, child),
            )
        )
        return
    _validate_override_map(context.caller_name, child.nodeset, {tail: value}, registry=context.registry, findings=context.findings)


def _validate_direct_override(
    caller_name: str,
    target: NodeSpec,
    value: dict[str, object],
    *,
    nodeset: NodesetSpec,
    registry: NodeRegistry,
    findings: list[HealthFinding],
) -> None:
    child = _resolve_composite_child(target, nodeset.graph)
    if child is not None:
        findings.append(
            _node_config_finding(
                "NODESET.CONFIG.NESTED_PATH_REQUIRED",
                caller_name,
                f"override for nested {child.kind} must use a dotted path: {target.id}",
                details=_override_path_details(nodeset, target.id, target, child),
            )
        )
        return
    if target.status == STATUS_PLANNED:
        return
    try:
        registry.merge_config(target.type_used, {**target.params, **value})
    except NodeRegistryError as exc:
        findings.append(_node_config_finding("NODESET.CONFIG.INVALID", caller_name, str(exc), details={"nodeset": nodeset.type_key, "node": target.id, "type_used": target.type_used}))


def _resolve_composite_child(target: NodeSpec, graph: GraphConfig) -> _CompositeChild | None:
    if target.type_used in LOOP_NODE_TYPES:
        body = target.loop.body
        return _CompositeChild("loop", body, graph.nodesets.get(body))
    if target.type_used in graph.nodesets:
        return _CompositeChild("nodeset", target.type_used, graph.nodesets.get(target.type_used))
    return None


def _override_path_details(nodeset: NodesetSpec, path: str, target: NodeSpec, child: _CompositeChild) -> dict[str, object]:
    details: dict[str, object] = {
        "owner": f"nodeset:{nodeset.type_key}",
        "nodeset": nodeset.type_key,
        "path": path,
        "node": target.id,
        "type_used": target.type_used,
        "composite_kind": child.kind,
    }
    if child.kind == "loop":
        details["loop_body"] = child.type_key
    else:
        details["child_nodeset"] = child.type_key
    return details


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
