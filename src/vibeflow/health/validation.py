from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from vibeflow.health.types import HealthFinding, HealthReport
from vibeflow.purity.types import PurityPolicy
from vibeflow.graph_config import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.health.flow import append_data_contract_warnings, append_flowchart_health, append_join_policy_health
from vibeflow.health.planned import append_planned_findings
from vibeflow.health.report import _build_health_report
from vibeflow.policy import EffectivePolicy, apply_policy_to_findings

if TYPE_CHECKING:
    from vibeflow.compiler import CompiledGraph, GraphCompileError
    from vibeflow.graph_config import GraphConfig
    from vibeflow.plugin import PluginRegistry
    from vibeflow.registry import NodeRegistry, NodeRegistryError

@dataclass
class _HealthValidationState:
    errors: list[HealthFinding] = field(default_factory=list)
    warnings: list[HealthFinding] = field(default_factory=list)
    node_metrics: dict[str, dict[str, object]] = field(default_factory=dict)
    node_types: dict[str, str] = field(default_factory=dict)
    node_similarities: dict[str, dict[str, str]] = field(default_factory=dict)
    nodeset_findings: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    scanned_base_roots: set[str] = field(default_factory=set)
    unhealthy_base_modules: set[str] = field(default_factory=set)
    mainline: dict[str, dict[str, object]] = field(default_factory=dict)


def validate_graph_health(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    boundary_registry: object | None = None,
    plugin_registry: PluginRegistry | None = None,
    global_config: Mapping[str, object] | None = None,
    purity_policy: PurityPolicy | None = None,
    effective_policy: EffectivePolicy | None = None,
) -> HealthReport:
    from vibeflow.compiler import GraphCompiler, GraphCompileError

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

    append_planned_findings(graph, state)
    _validate_graph_nodes(graph, registry, plugin_registry, purity_policy, state)
    _append_node_visual_metadata_warnings(graph, state)
    if not state.errors:
        try:
            compiled = GraphCompiler().compile(graph, registry=registry)
        except GraphCompileError as exc:
            return _compile_error_report(exc)
        append_flowchart_health(graph, compiled, state, registry=registry)
        _append_mainline_health(graph, compiled, registry, state)
    _append_node_config_health(graph, registry, state, global_config=global_config)
    append_data_contract_warnings(graph, compiled, state)
    append_join_policy_health(graph, compiled, state)
    _append_registry_namespace_smells(registry, state)
    _append_duplicate_logic_findings(state)
    _append_nodeset_health(graph, registry, state)
    _append_graph_plugin_findings(graph, compiled, plugin_registry, state)
    return _build_health_report(graph, compiled, plugin_registry, state, effective_policy=effective_policy)


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
                details=dict(exc.details or {}),
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
        state.node_types[spec.id] = spec.type_used
        if spec.similar_to.node:
            state.node_similarities[spec.id] = spec.similar_to.to_dict()
        if spec.status == STATUS_PLANNED:
            continue
        if spec.type_used in LOOP_NODE_TYPES:
            continue
        if spec.type_used in graph.nodesets:
            continue
        _validate_graph_node(spec, registry, plugin_registry, purity_policy, state)


def _validate_graph_node(
    spec,
    registry: NodeRegistry,
    plugin_registry: PluginRegistry | None,
    purity_policy: PurityPolicy | None,
    state: _HealthValidationState,
) -> None:
    from vibeflow.health.plugins import append_plugin_findings
    from vibeflow.registry import NodeRegistryError

    try:
        node_cls = registry.get(spec.type_used)
    except NodeRegistryError as exc:
        state.errors.append(_unknown_node_finding(spec, exc))
        return
    from vibeflow.purity import collect_node_metrics

    metrics = collect_node_metrics(node_cls)
    state.node_metrics[spec.id] = metrics.to_dict()
    _validate_plugin_schema_extensions(plugin_registry, state.errors, spec.id, node_cls, purity_policy)
    _record_node_fingerprint(spec.id, metrics, state)
    _append_base_lib_health(spec.id, node_cls, purity_policy, state)
    _append_node_name_smell(spec.id, state)
    _append_node_purity_findings(spec, node_cls, registry, purity_policy, state)
    append_plugin_findings(plugin_registry, "validate_node", state.errors, state.warnings, spec, node_cls, metrics.to_dict())


def _unknown_node_finding(spec, exc: NodeRegistryError) -> HealthFinding:
    return HealthFinding(
        rule_id="NODE.TYPE.UNKNOWN",
        severity="error",
        object_type="node",
        object_id=spec.id,
        failure_layer="topology",
        message=str(exc),
        suggested_fix_type="fix_config",
        details={"type_used": spec.type_used},
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
    from vibeflow.base_lib import node_base_lib_imports, summarize_base_lib_dependency_chain
    from vibeflow.health.base_lib import append_dependency_chain_findings, matching_unhealthy_base_module

    base_report = _scan_base_lib_for_node(node_cls, purity_policy=purity_policy, scanned=state.scanned_base_roots)
    if base_report is None:
        return
    imported_modules = node_base_lib_imports(node_cls)
    dependency_summary = summarize_base_lib_dependency_chain(imported_modules, base_report)
    relevant_modules = _relevant_base_lib_modules(imported_modules, base_report)
    state.node_metrics[node_name]["base_lib_dependency_chain"] = dependency_summary.to_dict()
    append_dependency_chain_findings(state.errors, state.warnings, node_name, dependency_summary, purity_policy or PurityPolicy())
    _append_base_report_findings(base_report.findings, state, relevant_modules=relevant_modules)
    state.unhealthy_base_modules.update(finding.object_id for finding in base_report.findings if finding.object_id in relevant_modules)
    _append_indirect_base_lib_findings(node_name, imported_modules, state)


def _append_base_report_findings(findings, state: _HealthValidationState, *, relevant_modules: set[str]) -> None:
    from vibeflow.health.base_lib import base_lib_finding_to_health

    for finding in findings:
        if finding.object_id not in relevant_modules:
            continue
        health_finding = base_lib_finding_to_health(finding)
        if finding.severity == "warning":
            state.warnings.append(health_finding)
        else:
            state.errors.append(health_finding)


def _relevant_base_lib_modules(imported_modules: tuple[str, ...], base_report) -> set[str]:
    modules = {module.module for module in base_report.modules}
    adjacency: dict[str, set[str]] = {}
    for source, target in base_report.dependency_edges:
        adjacency.setdefault(source, set()).add(target)
    starts = tuple(dict.fromkeys(_resolve_base_module(imported, modules) for imported in imported_modules))
    relevant: set[str] = set()

    def visit(module: str) -> None:
        if not module or module in relevant:
            return
        relevant.add(module)
        for target in adjacency.get(module, ()):
            visit(target)

    for start in starts:
        visit(start)
    return relevant


def _resolve_base_module(imported: str, modules: set[str]) -> str:
    if imported in modules:
        return imported
    for module in sorted(modules):
        if module.startswith(f"{imported}."):
            return module
    return ""


def _append_indirect_base_lib_findings(node_name: str, imported_modules: tuple[str, ...], state: _HealthValidationState) -> None:
    from vibeflow.health.base_lib import matching_unhealthy_base_module

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
    from vibeflow.purity import validate_node_class
    from vibeflow.health.plugins import append_finding_by_severity

    known_classes, known_modules = _known_node_identifiers(registry, node_cls)
    for violation in validate_node_class(
        node_cls,
        policy=purity_policy,
        expected_type=spec.type_used,
        known_node_class_names=known_classes,
        known_node_modules=known_modules,
        scan_module=True,
    ):
        append_finding_by_severity(_node_violation_finding(spec.id, violation), state.errors, state.warnings)


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


def _append_node_config_health(graph: GraphConfig, registry: NodeRegistry, state: _HealthValidationState, *, global_config: Mapping[str, object] | None) -> None:
    from vibeflow.health.node_config import validate_node_config_health

    findings = validate_node_config_health(graph, registry=registry, global_config=global_config)
    for finding in findings:
        if finding.severity == "warning":
            state.warnings.append(finding)
        else:
            state.errors.append(finding)


def _append_node_visual_metadata_warnings(
    graph: GraphConfig,
    state: _HealthValidationState,
    *,
    owner: str = "pipeline",
    visited_nodesets: set[str] | None = None,
) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    for node in graph.nodes:
        if not node.metadata.display_name.strip():
            state.warnings.append(_node_visual_metadata_finding("GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME", node.id, "display_name", owner=owner))
        if not node.metadata.description.strip():
            state.warnings.append(_node_visual_metadata_finding("GRAPH.SMELL.MISSING_NODE_DESCRIPTION", node.id, "description", owner=owner))
    for nodeset in graph.nodesets.values():
        if nodeset.type_key in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.type_key)
        _append_node_visual_metadata_warnings(nodeset.graph, state, owner=f"nodeset:{nodeset.type_key}", visited_nodesets=visited_nodesets)


def _node_visual_metadata_finding(rule_id: str, node_name: str, field: str, *, owner: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="warning",
        object_type="node",
        object_id=node_name,
        failure_layer="topology",
        message=f"config node '{node_name}' should declare {field} for readable SVG diagrams",
        suggested_fix_type="fix_config",
        details={"field": field, "owner": owner},
    )


def _append_registry_namespace_smells(registry: NodeRegistry, state: _HealthValidationState) -> None:
    from vibeflow.health.registry import registry_namespace_findings

    state.warnings.extend(registry_namespace_findings(registry))


def _append_duplicate_logic_findings(state: _HealthValidationState) -> None:
    from vibeflow.health.duplicates import duplicate_logic_findings

    state.warnings.extend(
        duplicate_logic_findings(
            state.fingerprints,
            state.node_metrics,
            node_types=state.node_types,
            node_similarities=state.node_similarities,
        )
    )


def _append_nodeset_health(graph: GraphConfig, registry: NodeRegistry, state: _HealthValidationState) -> None:
    from vibeflow.health.nodesets import append_nodeset_finding, validate_nodesets

    for nodeset in graph.nodesets.values():
        if len(nodeset.graph.nodes) > 10:
            append_nodeset_finding(
                state.warnings,
                state.nodeset_findings,
                HealthFinding(
                    rule_id="NODESET.SMELL.TOO_WIDE",
                    severity="warning",
                    object_type="nodeset",
                    object_id=nodeset.type_key,
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


def _append_mainline_health(graph: GraphConfig, compiled: CompiledGraph, registry: NodeRegistry, state: _HealthValidationState) -> None:
    from vibeflow.health.mainline import append_mainline_health

    append_mainline_health(graph, compiled, state, registry=registry)


def _append_graph_plugin_findings(
    graph: GraphConfig,
    compiled: CompiledGraph,
    plugin_registry: PluginRegistry | None,
    state: _HealthValidationState,
) -> None:
    from vibeflow.health.plugins import append_plugin_findings

    append_plugin_findings(plugin_registry, "validate_graph", state.errors, state.warnings, graph, compiled)
    append_plugin_findings(plugin_registry, "validate_compiled_graph", state.errors, state.warnings, graph, compiled, plugin_types=("compiler",))
    append_plugin_findings(plugin_registry, "validate_runtime_plan", state.errors, state.warnings, graph, compiled, plugin_types=("runtime",))
    for nodeset in graph.nodesets.values():
        append_plugin_findings(plugin_registry, "validate_nodeset", state.errors, state.warnings, nodeset)


def _validate_plugin_schema_extensions(
    plugin_registry: PluginRegistry | None,
    errors: list[HealthFinding],
    node_name: str,
    node_cls: type,
    purity_policy: PurityPolicy | None,
) -> None:
    from vibeflow.plugin import plugin_error

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
    from vibeflow.base_lib import scan_base_lib

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
