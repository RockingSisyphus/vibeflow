from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .health_types import HealthFinding, HealthReport
from .purity_types import PurityPolicy
from .graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from .node import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL

if TYPE_CHECKING:
    from .compiler import CompiledGraph, GraphCompileError
    from .graph_config import GraphConfig
    from .plugin import PluginRegistry
    from .registry import NodeRegistry, NodeRegistryError

@dataclass
class _HealthValidationState:
    errors: list[HealthFinding] = field(default_factory=list)
    warnings: list[HealthFinding] = field(default_factory=list)
    node_metrics: dict[str, dict[str, object]] = field(default_factory=dict)
    nodeset_findings: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    scanned_base_roots: set[str] = field(default_factory=set)
    unhealthy_base_modules: set[str] = field(default_factory=set)


def validate_graph_health(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    boundary_registry: object | None = None,
    plugin_registry: PluginRegistry | None = None,
    purity_policy: PurityPolicy | None = None,
) -> HealthReport:
    from .compiler import GraphCompiler, GraphCompileError

    state = _HealthValidationState()
    if boundary_registry is not None:
        state.errors.append(
            HealthFinding(
                rule_id="CONFIG.BOUNDARY.REMOVED",
                severity="error",
                object_type="boundary",
                object_id="boundary",
                failure_layer="topology",
                message="boundary_registry is removed; use flowchart nodes",
                suggested_fix_type="fix_config",
            )
        )
    try:
        compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
    except GraphCompileError as exc:
        return _compile_error_report(exc)

    _append_planned_findings(graph, state)
    _validate_graph_nodes(graph, registry, plugin_registry, purity_policy, state)
    if not state.errors:
        try:
            compiled = GraphCompiler().compile(graph, registry=registry)
        except GraphCompileError as exc:
            return _compile_error_report(exc)
        _append_flowchart_health(graph, compiled, state, registry=registry)
    _append_node_config_health(graph, registry, state)
    _append_data_contract_warnings(graph, compiled, state)
    _append_registry_namespace_smells(registry, state)
    _append_duplicate_logic_findings(state)
    _append_nodeset_health(graph, registry, state)
    _append_graph_plugin_findings(graph, compiled, plugin_registry, state)
    return _build_health_report(graph, compiled, plugin_registry, state)


def _compile_error_report(exc: GraphCompileError) -> HealthReport:
    return HealthReport(
        status="FAIL",
        errors=(
            HealthFinding(
                rule_id=exc.rule_id,
                severity="error",
                object_type="pipeline",
                object_id="pipeline",
                failure_layer="topology",
                message=str(exc),
                suggested_fix_type="fix_config",
            ),
        ),
    )


def _validate_graph_nodes(
    graph: GraphConfig,
    registry: NodeRegistry,
    plugin_registry: PluginRegistry | None,
    purity_policy: PurityPolicy | None,
    state: _HealthValidationState,
) -> None:
    for spec in graph.nodes:
        if spec.status == STATUS_PLANNED:
            continue
        if spec.node_type.startswith("nodeset."):
            continue
        _validate_graph_node(spec, registry, plugin_registry, purity_policy, state)


def _validate_graph_node(
    spec,
    registry: NodeRegistry,
    plugin_registry: PluginRegistry | None,
    purity_policy: PurityPolicy | None,
    state: _HealthValidationState,
) -> None:
    from .health_plugins import append_plugin_findings
    from .registry import NodeRegistryError

    try:
        node_cls = registry.get(spec.node_type)
    except NodeRegistryError as exc:
        state.errors.append(_unknown_node_finding(spec, exc))
        return
    from .purity import collect_node_metrics

    metrics = collect_node_metrics(node_cls)
    state.node_metrics[spec.name] = metrics.to_dict()
    _validate_plugin_schema_extensions(plugin_registry, state.errors, spec.name, node_cls, purity_policy)
    _record_node_fingerprint(spec.name, metrics, state)
    _append_base_lib_health(spec.name, node_cls, purity_policy, state)
    _append_node_name_smell(spec.name, state)
    _append_node_purity_findings(spec, node_cls, registry, purity_policy, state)
    append_plugin_findings(plugin_registry, "validate_node", state.errors, state.warnings, spec, node_cls, metrics.to_dict())


def _unknown_node_finding(spec, exc: NodeRegistryError) -> HealthFinding:
    return HealthFinding(
        rule_id="NODE.TYPE.UNKNOWN",
        severity="error",
        object_type="node",
        object_id=spec.name,
        failure_layer="topology",
        message=str(exc),
        suggested_fix_type="fix_config",
        details={"node_type": spec.node_type},
    )


def _record_node_fingerprint(node_name: str, metrics, state: _HealthValidationState) -> None:
    if metrics.run_pure_fingerprint:
        state.fingerprints[node_name] = metrics.run_pure_fingerprint


def _append_base_lib_health(
    node_name: str,
    node_cls: type,
    purity_policy: PurityPolicy | None,
    state: _HealthValidationState,
) -> None:
    from .base_lib import node_base_lib_imports, summarize_base_lib_dependency_chain
    from .health_base_lib import append_dependency_chain_findings, matching_unhealthy_base_module

    base_report = _scan_base_lib_for_node(node_cls, purity_policy=purity_policy, scanned=state.scanned_base_roots)
    if base_report is None:
        return
    imported_modules = node_base_lib_imports(node_cls)
    dependency_summary = summarize_base_lib_dependency_chain(imported_modules, base_report)
    state.node_metrics[node_name]["base_lib_dependency_chain"] = dependency_summary.to_dict()
    append_dependency_chain_findings(state.errors, state.warnings, node_name, dependency_summary, purity_policy or PurityPolicy())
    _append_base_report_findings(base_report.findings, state)
    state.unhealthy_base_modules.update(finding.object_id for finding in base_report.findings)
    _append_indirect_base_lib_findings(node_name, imported_modules, state)


def _append_base_report_findings(findings, state: _HealthValidationState) -> None:
    from .health_base_lib import base_lib_finding_to_health

    for finding in findings:
        health_finding = base_lib_finding_to_health(finding)
        if finding.severity == "warning":
            state.warnings.append(health_finding)
        else:
            state.errors.append(health_finding)


def _append_indirect_base_lib_findings(node_name: str, imported_modules: tuple[str, ...], state: _HealthValidationState) -> None:
    from .health_base_lib import matching_unhealthy_base_module

    for imported in imported_modules:
        matched = matching_unhealthy_base_module(imported, state.unhealthy_base_modules)
        if matched:
            state.errors.append(_indirect_base_lib_finding(node_name, imported, matched))


def _indirect_base_lib_finding(node_name: str, imported: str, matched: str) -> HealthFinding:
    return HealthFinding(
        rule_id="NODE.BASE_LIB.INDIRECT_VIOLATION",
        severity="error",
        object_type="node",
        object_id=node_name,
        failure_layer="base_lib",
        message=f"node imports unhealthy base_lib module: {imported} -> {matched}",
        suggested_fix_type="fix_base_lib",
        details={"imported_module": imported, "unhealthy_base_lib": matched},
    )


def _append_node_name_smell(node_name: str, state: _HealthValidationState) -> None:
    if _looks_node_name(node_name):
        return
    state.warnings.append(
        HealthFinding(
            rule_id="GRAPH.SMELL.CONFUSING_NODE_NAME",
            severity="warning",
            object_type="node",
            object_id=node_name,
            failure_layer="topology",
            message=f"node name should use lowercase snake_case: {node_name}",
            suggested_fix_type="fix_config",
        )
    )


def _append_node_purity_findings(
    spec,
    node_cls: type,
    registry: NodeRegistry,
    purity_policy: PurityPolicy | None,
    state: _HealthValidationState,
) -> None:
    from .purity import validate_node_class
    from .health_plugins import append_finding_by_severity

    known_classes, known_modules = _known_node_identifiers(registry, node_cls)
    for violation in validate_node_class(
        node_cls,
        policy=purity_policy,
        expected_type=spec.node_type,
        known_node_class_names=known_classes,
        known_node_modules=known_modules,
    ):
        append_finding_by_severity(_node_violation_finding(spec.name, violation), state.errors, state.warnings)


def _known_node_identifiers(registry: NodeRegistry, current_cls: type) -> tuple[tuple[str, ...], tuple[str, ...]]:
    other_classes = tuple(cls for cls in _registry_node_classes(registry) if cls is not current_cls)
    return (
        tuple(cls.__name__ for cls in other_classes),
        tuple((getattr(cls, "__module__", "") or "") for cls in other_classes),
    )


def _node_violation_finding(node_name: str, violation) -> HealthFinding:
    return HealthFinding(
        rule_id=violation.rule_id,
        severity=violation.severity,
        object_type="node",
        object_id=node_name,
        source_location=violation.source_location,
        failure_layer=violation.failure_layer,
        message=violation.message,
        suggested_fix_type=violation.suggested_fix_type,
        details={"legacy_code": violation.code, **dict(violation.details)},
    )


def _append_node_config_health(graph: GraphConfig, registry: NodeRegistry, state: _HealthValidationState) -> None:
    from .health_node_config import validate_node_config_health

    state.errors.extend(validate_node_config_health(graph, registry=registry))


def _append_planned_findings(graph: GraphConfig, state: _HealthValidationState) -> None:
    _append_planned_findings_for_graph(graph, state, owner="pipeline")
    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            state.warnings.append(
                HealthFinding(
                    rule_id="GRAPH.PLANNED.NODESET",
                    severity="warning",
                    object_type="nodeset",
                    object_id=nodeset.name,
                    failure_layer="topology",
                    message=f"nodeset '{nodeset.name}' is planned and cannot run yet",
                    suggested_fix_type="implement_nodeset",
                )
            )
        _append_planned_findings_for_graph(nodeset.graph, state, owner=f"nodeset:{nodeset.name}")
        if nodeset.status == STATUS_IMPLEMENTED and _graph_has_planned(nodeset.graph):
            state.errors.append(
                HealthFinding(
                    rule_id="GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD",
                    severity="error",
                    object_type="nodeset",
                    object_id=nodeset.name,
                    failure_layer="topology",
                    message=f"implemented nodeset '{nodeset.name}' contains planned child nodes",
                    suggested_fix_type="implement_nodeset",
                )
            )


def _append_planned_findings_for_graph(graph: GraphConfig, state: _HealthValidationState, *, owner: str) -> None:
    for node in graph.nodes:
        if node.status != STATUS_PLANNED:
            continue
        state.warnings.append(
            HealthFinding(
                rule_id="GRAPH.PLANNED.NODE",
                severity="warning",
                object_type="node",
                object_id=node.name,
                failure_layer="topology",
                message=f"node '{node.name}' is planned and cannot run yet",
                suggested_fix_type="implement_node",
                details={"owner": owner, "flow_kind": node.flow_kind},
            )
        )


def _graph_has_planned(graph: GraphConfig) -> bool:
    return any(node.status == STATUS_PLANNED for node in graph.nodes) or any(nodeset.status == STATUS_PLANNED or _graph_has_planned(nodeset.graph) for nodeset in graph.nodesets.values())


def _append_flowchart_health(graph: GraphConfig, compiled: CompiledGraph, state: _HealthValidationState, *, registry: NodeRegistry, owner: str = "pipeline") -> None:
    active_nodes = [node for node in graph.nodes if node.status != STATUS_PLANNED]
    if not active_nodes:
        return
    active_names = {node.name for node in active_nodes}
    edges = [edge for edge in compiled.effective_edges if edge.source in active_names and edge.target in active_names]
    incoming = {name: [] for name in active_names}
    outgoing = {name: [] for name in active_names}
    outgoing_edges = {name: [] for name in active_names}
    for edge in edges:
        outgoing[edge.source].append(edge.target)
        outgoing_edges[edge.source].append(edge)
        incoming[edge.target].append(edge.source)
    starts = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not incoming[name]}
    ends = {name for name in active_names if compiled.flow_kinds.get(name) == FLOW_KIND_TERMINAL and not outgoing[name]}
    if not starts:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_START", owner, "graph must have a terminal start node with no incoming flow edge"))
    if not ends:
        state.errors.append(_flow_finding("GRAPH.FLOW.MISSING_END", owner, "graph must have a terminal end node with no outgoing flow edge"))
    if starts:
        reachable = _walk(starts, outgoing)
        for name in sorted(active_names - reachable):
            state.errors.append(_flow_finding("GRAPH.FLOW.UNREACHABLE_FROM_START", name, f"node '{name}' is not reachable from a start node", object_type="node"))
    if ends:
        can_reach_end = _walk(ends, incoming)
        for name in sorted(active_names - can_reach_end):
            state.errors.append(_flow_finding("GRAPH.FLOW.CANNOT_REACH_END", name, f"node '{name}' cannot reach an end node", object_type="node"))
        _append_decision_branch_health(graph, compiled, state, registry=registry, outgoing=outgoing, outgoing_edges=outgoing_edges, can_reach_end=can_reach_end)
    if len(active_names) > 1:
        for name in sorted(active_names):
            if not incoming[name] and not outgoing[name]:
                state.errors.append(_flow_finding("GRAPH.FLOW.ORPHAN_NODE", name, f"node '{name}' has no flow edges", object_type="node"))
    from .compiler import GraphCompiler, GraphCompileError

    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            continue
        try:
            nested = GraphCompiler().compile(nodeset.graph, registry=registry)
        except GraphCompileError:
            continue
        _append_flowchart_health(nodeset.graph, nested, state, registry=registry, owner=f"nodeset:{nodeset.name}")


def _append_data_contract_warnings(graph: GraphConfig, compiled: CompiledGraph, state: _HealthValidationState) -> None:
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
        upstream_names = _walk(set(incoming.get(node.name, ())), incoming)
        upstream = [nodes_by_name[name] for name in upstream_names if name in nodes_by_name]
        for key in node.requires:
            if key in graph.inputs:
                continue
            if not any(key in parent.provides for parent in upstream):
                state.warnings.append(_data_finding("GRAPH.DATA.MISSING_UPSTREAM_PROVIDER", key, f"node '{node.name}' requires '{key}' but no upstream flow predecessor provides it", node=node.name))
        downstream_names = _walk(set(outgoing.get(node.name, ())), outgoing)
        downstream = [nodes_by_name[name] for name in downstream_names if name in nodes_by_name]
        is_end = compiled.flow_kinds.get(node.name) == FLOW_KIND_TERMINAL and not outgoing.get(node.name)
        if is_end:
            continue
        for key in node.provides:
            if key in condition_keys_by_source.get(node.name, set()):
                continue
            if not any(key in child.requires for child in downstream):
                state.warnings.append(_data_finding("GRAPH.DATA.UNCONSUMED_PROVIDER", key, f"node '{node.name}' provides '{key}' but no downstream flow successor requires it", node=node.name))


def _append_decision_branch_health(
    graph: GraphConfig,
    compiled: CompiledGraph,
    state: _HealthValidationState,
    *,
    registry: NodeRegistry,
    outgoing: dict[str, list[str]],
    outgoing_edges: dict[str, list[object]],
    can_reach_end: set[str],
) -> None:
    nodes_by_name = {node.name: node for node in graph.nodes}
    for node in graph.nodes:
        if node.status == STATUS_PLANNED or compiled.flow_kinds.get(node.name) != FLOW_KIND_DECISION:
            continue
        schema_values = _decision_schema_values(node, registry)
        equality_values: set[object] = set()
        for edge in outgoing_edges.get(node.name, ()):
            parsed = _parse_when(getattr(edge, "when", ""))
            if parsed is not None and schema_values is not None:
                key, operator, literal = parsed
                if operator == "==" and literal not in schema_values:
                    state.errors.append(
                        _flow_finding(
                            "GRAPH.DECISION.UNKNOWN_BRANCH_VALUE",
                            node.name,
                            f"decision node '{node.name}' has branch {key} == {literal!r}, not declared in output_schema",
                            object_type="node",
                        )
                    )
                if operator == "==":
                    equality_values.add(literal)
            target = getattr(edge, "target", "")
            if target not in nodes_by_name:
                continue
            # A back-edge branch is the loop itself; end reachability is checked on the exit branches.
            if node.name in _walk({target}, outgoing):
                continue
            if target not in can_reach_end:
                state.errors.append(
                    _flow_finding(
                        "GRAPH.DECISION.BRANCH_CANNOT_REACH_END",
                        node.name,
                        f"decision branch {node.name}->{target} cannot reach a terminal end node",
                        object_type="node",
                    )
                )
        if schema_values is not None and equality_values:
            missing = schema_values - equality_values
            if missing:
                state.errors.append(
                    _flow_finding(
                        "GRAPH.DECISION.MISSING_BRANCH_VALUE",
                        node.name,
                        f"decision node '{node.name}' has no outgoing branch for schema values: {sorted(missing)!r}",
                        object_type="node",
                    )
                )


def _decision_schema_values(node: Any, registry: NodeRegistry) -> set[object] | None:
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
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=object_type,
        object_id=object_id,
        failure_layer="topology",
        message=message,
        suggested_fix_type="fix_config",
    )


def _data_finding(rule_id: str, key: str, message: str, *, node: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="warning",
        object_type="contract_key",
        object_id=key,
        failure_layer="topology",
        message=message,
        suggested_fix_type="fix_config",
        details={"node": node},
    )


def _append_registry_namespace_smells(registry: NodeRegistry, state: _HealthValidationState) -> None:
    from .health_registry import registry_namespace_findings

    state.warnings.extend(registry_namespace_findings(registry))


def _append_duplicate_logic_findings(state: _HealthValidationState) -> None:
    from .health_duplicates import duplicate_logic_findings

    state.warnings.extend(duplicate_logic_findings(state.fingerprints, state.node_metrics))


def _append_nodeset_health(graph: GraphConfig, registry: NodeRegistry, state: _HealthValidationState) -> None:
    from .health_nodesets import append_nodeset_finding, validate_nodesets

    for nodeset in graph.nodesets.values():
        if len(nodeset.graph.nodes) > 10:
            append_nodeset_finding(
                state.warnings,
                state.nodeset_findings,
                HealthFinding(
                    rule_id="NODESET.SMELL.TOO_WIDE",
                    severity="warning",
                    object_type="nodeset",
                    object_id=nodeset.name,
                    failure_layer="topology",
                    message=f"nodeset has {len(nodeset.graph.nodes)} internal nodes; consider splitting it",
                    suggested_fix_type="fix_nodeset",
                    details={"node_count": len(nodeset.graph.nodes), "limit": 10},
                ),
            )
    nodeset_errors, nodeset_warnings = validate_nodesets(graph, registry=registry)
    for finding in nodeset_errors:
        append_nodeset_finding(state.errors, state.nodeset_findings, finding)
    for finding in nodeset_warnings:
        append_nodeset_finding(state.warnings, state.nodeset_findings, finding)


def _append_graph_plugin_findings(
    graph: GraphConfig,
    compiled: CompiledGraph,
    plugin_registry: PluginRegistry | None,
    state: _HealthValidationState,
) -> None:
    from .health_plugins import append_plugin_findings

    append_plugin_findings(plugin_registry, "validate_graph", state.errors, state.warnings, graph, compiled)
    append_plugin_findings(plugin_registry, "validate_compiled_graph", state.errors, state.warnings, graph, compiled, plugin_types=("compiler",))
    append_plugin_findings(plugin_registry, "validate_runtime_plan", state.errors, state.warnings, graph, compiled, plugin_types=("runtime",))
    for nodeset in graph.nodesets.values():
        append_plugin_findings(plugin_registry, "validate_nodeset", state.errors, state.warnings, nodeset)


def _build_health_report(
    graph: GraphConfig,
    compiled: CompiledGraph,
    plugin_registry: PluginRegistry | None,
    state: _HealthValidationState,
) -> HealthReport:
    return HealthReport(
        status=_health_status(state.errors, state.warnings),
        errors=tuple(state.errors),
        warnings=tuple(state.warnings),
        info={
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "node_metrics": state.node_metrics,
            "nodeset_findings": state.nodeset_findings,
            "plugins": plugin_registry.to_dict() if plugin_registry is not None else {"plugins": []},
        },
    )


def _health_status(errors: list[HealthFinding], warnings: list[HealthFinding]) -> str:
    if any(finding.failure_layer == "plugin" for finding in errors):
        return "ERROR"
    if errors:
        return "FAIL"
    return "CONCERNS" if warnings else "PASS"


def _validate_plugin_schema_extensions(
    plugin_registry: PluginRegistry | None,
    errors: list[HealthFinding],
    node_name: str,
    node_cls: type,
    purity_policy: PurityPolicy | None,
) -> None:
    from .plugin import plugin_error

    if plugin_registry is None:
        return
    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)
    schema_payloads = {
        "extend_node_metadata_schema": {"node": node_name, "metadata": info},
        "extend_contract_schema": {"node": node_name, "contract": contract},
        "extend_purity_rules": {"node": node_name, "policy": purity_policy},
    }
    for plugin in plugin_registry.policy_plugins():
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        for hook, payload in schema_payloads.items():
            method = getattr(plugin, hook, None)
            if not callable(method):
                continue
            try:
                result = method(dict(payload))
            except Exception as exc:
                errors.append(plugin_error("PLUGIN.EXECUTION", f"PolicyPlugin.{hook} failed: {exc}", plugin_name))
                continue
            if result is not None and not isinstance(result, Mapping):
                errors.append(plugin_error("PLUGIN.SCHEMA_EXTENSION.SHAPE", f"PolicyPlugin.{hook} must return an object or None", plugin_name))


def _registry_node_classes(registry: NodeRegistry) -> tuple[type, ...]:
    values = getattr(registry, "_registry", {}).values()
    return tuple(value for value in values if isinstance(value, type))


def _looks_node_name(value: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    return bool(value) and value == value.lower() and all(char in allowed for char in value)


def _scan_base_lib_for_node(node_cls: type, *, purity_policy: PurityPolicy | None, scanned: set[str]):
    from .base_lib import scan_base_lib

    source_file = inspect.getsourcefile(node_cls)
    if not source_file:
        return None
    root = Path(source_file).parent
    policy = purity_policy or PurityPolicy()
    key = str(root.resolve())
    if key in scanned:
        return None
    default_base_lib = root / "base_lib"
    if not policy.allowed_base_lib_paths and not default_base_lib.exists():
        return None
    scanned.add(key)
    return scan_base_lib(root, policy=policy)
