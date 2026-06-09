from __future__ import annotations

import inspect
from pathlib import Path

from .base_lib import node_base_lib_imports, scan_base_lib, summarize_base_lib_dependency_chain
from .boundary import BoundaryRegistry
from .compiler import GraphCompiler, GraphCompileError
from .graph_config import GraphConfig
from .health_base_lib import append_dependency_chain_findings, base_lib_finding_to_health, matching_unhealthy_base_module
from .health_boundary import boundary_info, validate_boundary_health
from .health_nodesets import append_nodeset_finding, validate_nodesets
from .health_types import HealthFinding, HealthReport
from .plugin import PluginRegistry, plugin_error
from .purity import PurityPolicy, collect_node_metrics, validate_node_class
from .registry import NodeRegistry, NodeRegistryError


def validate_graph_health(
    graph: GraphConfig,
    *,
    registry: NodeRegistry,
    boundary_registry: BoundaryRegistry | None = None,
    plugin_registry: PluginRegistry | None = None,
    purity_policy: PurityPolicy | None = None,
) -> HealthReport:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    node_metrics: dict[str, dict[str, object]] = {}
    nodeset_findings: dict[str, list[dict[str, object]]] = {}
    fingerprints: dict[str, str] = {}
    scanned_base_roots: set[str] = set()
    unhealthy_base_modules: set[str] = set()
    boundary_findings: list[dict[str, object]] = []
    try:
        compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
    except GraphCompileError as exc:
        return HealthReport(
            status="FAIL",
            errors=(
                HealthFinding(
                    rule_id="GRAPH.COMPILE",
                    severity="error",
                    object_type="pipeline",
                    object_id="pipeline",
                    failure_layer="topology",
                    message=str(exc),
                    suggested_fix_type="fix_config",
                ),
            ),
        )

    for spec in graph.nodes:
        if spec.node_type.startswith("nodeset."):
            continue
        try:
            node_cls = registry.get(spec.node_type)
        except NodeRegistryError as exc:
            errors.append(
                HealthFinding(
                    rule_id="NODE.TYPE.UNKNOWN",
                    severity="error",
                    object_type="node",
                    object_id=spec.name,
                    failure_layer="topology",
                    message=str(exc),
                    suggested_fix_type="fix_config",
                    details={"node_type": spec.node_type},
                )
            )
            continue
        metrics = collect_node_metrics(node_cls)
        node_metrics[spec.name] = metrics.to_dict()
        _validate_plugin_schema_extensions(plugin_registry, errors, spec.name, node_cls, purity_policy)
        if metrics.run_pure_fingerprint:
            fingerprints[spec.name] = metrics.run_pure_fingerprint
        base_report = _scan_base_lib_for_node(node_cls, purity_policy=purity_policy, scanned=scanned_base_roots)
        if base_report is not None:
            dependency_summary = summarize_base_lib_dependency_chain(node_base_lib_imports(node_cls), base_report)
            node_metrics[spec.name]["base_lib_dependency_chain"] = dependency_summary.to_dict()
            append_dependency_chain_findings(errors, warnings, spec.name, dependency_summary, purity_policy or PurityPolicy())
            for finding in base_report.findings:
                health_finding = base_lib_finding_to_health(finding)
                if finding.severity == "warning":
                    warnings.append(health_finding)
                else:
                    errors.append(health_finding)
            unhealthy_base_modules.update(finding.object_id for finding in base_report.findings)
            for imported in node_base_lib_imports(node_cls):
                matched = matching_unhealthy_base_module(imported, unhealthy_base_modules)
                if matched:
                    errors.append(
                        HealthFinding(
                            rule_id="NODE.BASE_LIB.INDIRECT_VIOLATION",
                            severity="error",
                            object_type="node",
                            object_id=spec.name,
                            failure_layer="base_lib",
                            message=f"node imports unhealthy base_lib module: {imported} -> {matched}",
                            suggested_fix_type="fix_base_lib",
                            details={"imported_module": imported, "unhealthy_base_lib": matched},
                        )
                    )
        if not _looks_node_name(spec.name):
            warnings.append(
                HealthFinding(
                    rule_id="GRAPH.SMELL.CONFUSING_NODE_NAME",
                    severity="warning",
                    object_type="node",
                    object_id=spec.name,
                    failure_layer="topology",
                    message=f"node name should use lowercase snake_case: {spec.name}",
                    suggested_fix_type="fix_config",
                )
            )
        known_classes = tuple(cls.__name__ for cls in _registry_node_classes(registry) if cls is not node_cls)
        known_modules = tuple((getattr(cls, "__module__", "") or "") for cls in _registry_node_classes(registry) if cls is not node_cls)
        for violation in validate_node_class(
            node_cls,
            policy=purity_policy,
            expected_type=spec.node_type,
            known_node_class_names=known_classes,
            known_node_modules=known_modules,
        ):
            finding = HealthFinding(
                rule_id=violation.rule_id,
                severity=violation.severity,
                object_type="node",
                object_id=spec.name,
                source_location=violation.source_location,
                failure_layer=violation.failure_layer,
                message=violation.message,
                suggested_fix_type=violation.suggested_fix_type,
                details={"legacy_code": violation.code, **dict(violation.details)},
            )
            if violation.severity == "warning":
                warnings.append(finding)
            else:
                errors.append(finding)
        _append_plugin_findings(
            plugin_registry,
            "validate_node",
            errors,
            warnings,
            spec,
            node_cls,
            metrics.to_dict(),
        )

    boundary_errors = validate_boundary_health(graph, boundary_registry=boundary_registry)
    for finding in boundary_errors:
        errors.append(finding)
        boundary_findings.append(finding.to_dict())

    consumed = {key for node in graph.nodes for key in node.requires}
    if graph.boundary is not None:
        consumed.update(graph.boundary.consumes)
    provided = {key for node in graph.nodes for key in node.provides}
    for key in sorted(provided - consumed):
        warnings.append(
            HealthFinding(
                rule_id="GRAPH.OUTPUT.UNCONSUMED",
                severity="warning",
                object_type="contract_key",
                object_id=key,
                failure_layer="topology",
                message=f"output key is not consumed: {key}",
                suggested_fix_type="fix_contract",
            )
        )

    for first, second in _duplicate_fingerprints(fingerprints):
        warnings.append(
            HealthFinding(
                rule_id="GRAPH.SMELL.DUPLICATE_LOGIC",
                severity="warning",
                object_type="node",
                object_id=f"{first},{second}",
                failure_layer="implementation",
                message=f"nodes appear to have duplicate run_pure logic: {first}, {second}",
                suggested_fix_type="split_node",
            )
        )

    for nodeset in graph.nodesets.values():
        if len(nodeset.graph.nodes) > 10:
            append_nodeset_finding(
                warnings,
                nodeset_findings,
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
        append_nodeset_finding(errors, nodeset_findings, finding)
    for finding in nodeset_warnings:
        append_nodeset_finding(warnings, nodeset_findings, finding)
    _append_plugin_findings(plugin_registry, "validate_graph", errors, warnings, graph, compiled)
    _append_plugin_findings(plugin_registry, "validate_compiled_graph", errors, warnings, graph, compiled, plugin_types=("compiler",))
    _append_plugin_findings(plugin_registry, "validate_runtime_plan", errors, warnings, graph, compiled, plugin_types=("runtime",))
    for nodeset in graph.nodesets.values():
        _append_plugin_findings(plugin_registry, "validate_nodeset", errors, warnings, nodeset)
    if graph.boundary is not None:
        _append_plugin_findings(plugin_registry, "validate_boundary", errors, warnings, graph.boundary)
        _append_plugin_findings(plugin_registry, "validate_boundary", errors, warnings, graph.boundary, plugin_types=("boundary",))

    status = "ERROR" if any(finding.failure_layer == "plugin" for finding in errors) else "FAIL" if errors else "CONCERNS" if warnings else "PASS"
    return HealthReport(
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        info={
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "edge_execution_limits": {f"{edge.source}->{edge.target}": edge.max_executions for edge in compiled.effective_edges},
            "loops": [loop.name for loop in compiled.loops],
            "loop_orders": {name: list(order) for name, order in compiled.loop_orders.items()},
            "node_metrics": node_metrics,
            "nodeset_findings": nodeset_findings,
            "boundary": boundary_info(graph),
            "boundary_findings": boundary_findings,
            "plugins": plugin_registry.to_dict() if plugin_registry is not None else {"plugins": []},
        },
    )


def _append_plugin_findings(
    plugin_registry: PluginRegistry | None,
    hook: str,
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
    *args,
    plugin_types: tuple[str, ...] = ("policy",),
) -> None:
    if plugin_registry is None:
        return
    plugins: list[object] = []
    if "policy" in plugin_types:
        plugins.extend(plugin_registry.policy_plugins())
    if "compiler" in plugin_types:
        plugins.extend(plugin_registry.compiler_plugins())
    if "runtime" in plugin_types:
        plugins.extend(plugin_registry.runtime_plugins())
    if "boundary" in plugin_types:
        plugins.extend(plugin_registry.boundary_plugins())
    for plugin in plugins:
        method = getattr(plugin, hook, None)
        if not callable(method):
            continue
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        try:
            findings = method(*args)
        except Exception as exc:
            errors.append(plugin_error("PLUGIN.EXECUTION", f"PolicyPlugin.{hook} failed: {exc}", plugin_name))
            continue
        if findings is None:
            continue
        if not isinstance(findings, (list, tuple)):
            errors.append(plugin_error("PLUGIN.FINDINGS.SHAPE", f"PolicyPlugin.{hook} must return a list/tuple of findings", plugin_name))
            continue
        for finding in findings:
            if not isinstance(finding, HealthFinding):
                errors.append(plugin_error("PLUGIN.FINDINGS.SHAPE", f"PolicyPlugin.{hook} returned non-HealthFinding", plugin_name))
                continue
            if finding.severity == "warning":
                warnings.append(finding)
            else:
                errors.append(finding)


def _validate_plugin_schema_extensions(
    plugin_registry: PluginRegistry | None,
    errors: list[HealthFinding],
    node_name: str,
    node_cls: type,
    purity_policy: PurityPolicy | None,
) -> None:
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


def _purity_rule_id(code: str) -> str:
    return f"NODE.PURITY.{code.upper()}"


def _purity_fix_type(code: str) -> str:
    if code in {"source_too_large", "source_bytes_too_large"}:
        return "split_node"
    if code in {"missing_node_info", "missing_contract", "missing_run_pure", "non_pure_node"}:
        return "fix_contract"
    if code in {"banned_import", "banned_call", "global_state", "context_run_forbidden"}:
        return "move_to_boundary"
    return "fix_node"


def _registry_node_classes(registry: NodeRegistry) -> tuple[type, ...]:
    values = getattr(registry, "_registry", {}).values()
    return tuple(value for value in values if isinstance(value, type))


def _looks_node_name(value: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    return bool(value) and value == value.lower() and all(char in allowed for char in value)


def _duplicate_fingerprints(fingerprints: dict[str, str]) -> tuple[tuple[str, str], ...]:
    grouped: dict[str, list[str]] = {}
    for node_name, fingerprint in fingerprints.items():
        grouped.setdefault(fingerprint, []).append(node_name)
    duplicates: list[tuple[str, str]] = []
    for names in grouped.values():
        if len(names) < 2:
            continue
        names = sorted(names)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                duplicates.append((first, second))
    return tuple(duplicates)


def _scan_base_lib_for_node(node_cls: type, *, purity_policy: PurityPolicy | None, scanned: set[str]):
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

