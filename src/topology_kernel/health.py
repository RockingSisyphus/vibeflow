from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .base_lib import BaseLibDependencySummary, BaseLibFinding, node_base_lib_imports, scan_base_lib, summarize_base_lib_dependency_chain
from .boundary import BoundaryRegistry, BoundaryRegistryError
from .compiler import GraphCompiler, GraphCompileError
from .graph_config import GraphConfig
from .plugin import PluginRegistry, plugin_error
from .purity import PurityPolicy, collect_node_metrics, validate_node_class
from .registry import NodeRegistry, NodeRegistryError


@dataclass(frozen=True)
class HealthFinding:
    rule_id: str
    message: str
    severity: str
    object_type: str = ""
    object_id: str = ""
    source_location: Mapping[str, object] = field(default_factory=dict)
    rule_source: str = "kernel.default_policy"
    failure_layer: str = ""
    suggested_fix_type: str = ""
    details: Mapping[str, object] = field(default_factory=dict)

    @property
    def code(self) -> str:
        return self.rule_id

    @property
    def subject(self) -> str:
        return self.object_id

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "source_location": dict(self.source_location),
            "rule_source": self.rule_source,
            "failure_layer": self.failure_layer,
            "message": self.message,
            "suggested_fix_type": self.suggested_fix_type,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class HealthReport:
    status: str
    errors: tuple[HealthFinding, ...] = ()
    warnings: tuple[HealthFinding, ...] = ()
    skipped: tuple[HealthFinding, ...] = ()
    info: dict[str, object] = field(default_factory=dict)
    effective_policy: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "errors": [finding.to_dict() for finding in self.errors],
            "warnings": [finding.to_dict() for finding in self.warnings],
            "skipped": [finding.to_dict() for finding in self.skipped],
            "info": self.info,
            "effective_policy": self.effective_policy,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


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
            _append_dependency_chain_findings(errors, warnings, spec.name, dependency_summary, purity_policy or PurityPolicy())
            for finding in base_report.findings:
                health_finding = _base_lib_finding_to_health(finding)
                if finding.severity == "warning":
                    warnings.append(health_finding)
                else:
                    errors.append(health_finding)
            unhealthy_base_modules.update(finding.object_id for finding in base_report.findings)
            for imported in node_base_lib_imports(node_cls):
                matched = _matching_unhealthy_base_module(imported, unhealthy_base_modules)
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

    boundary_errors = _validate_boundary_health(graph, boundary_registry=boundary_registry)
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
            _append_nodeset_finding(
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
    nodeset_errors, nodeset_warnings = _validate_nodesets(graph, registry=registry)
    for finding in nodeset_errors:
        _append_nodeset_finding(errors, nodeset_findings, finding)
    for finding in nodeset_warnings:
        _append_nodeset_finding(warnings, nodeset_findings, finding)
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
            "boundary": _boundary_info(graph),
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


def _validate_boundary_health(
    graph: GraphConfig,
    *,
    boundary_registry: BoundaryRegistry | None,
) -> tuple[HealthFinding, ...]:
    spec = graph.boundary
    if spec is None:
        return ()
    findings: list[HealthFinding] = []
    if boundary_registry is None:
        findings.append(
            _boundary_finding(
                "BOUNDARY.TYPE.UNRESOLVED",
                "graph declares boundary but no boundary registry was provided",
                spec.boundary_type,
            )
        )
    else:
        try:
            boundary_registry.get(spec.boundary_type)
        except BoundaryRegistryError as exc:
            findings.append(_boundary_finding("BOUNDARY.TYPE.UNKNOWN", str(exc), spec.boundary_type))
    for key in spec.consumes:
        if not (key.startswith("effects.") or key.startswith("outbox.")):
            findings.append(
                _boundary_finding(
                    "BOUNDARY.CONTRACT.CONSUMES_KEY",
                    f"boundary consumes key must start with effects. or outbox.: {key}",
                    key,
                )
            )
    for key in spec.provides:
        if not key.startswith("io."):
            findings.append(
                _boundary_finding(
                    "BOUNDARY.CONTRACT.PROVIDES_KEY",
                    f"boundary provides key must start with io.: {key}",
                    key,
                )
            )
    configured_run_dir = spec.config.get("run_dir")
    if configured_run_dir is not None and not (isinstance(configured_run_dir, str) and configured_run_dir.strip()):
        findings.append(_boundary_finding("BOUNDARY.CONFIG.RUN_DIR", "boundary.config.run_dir must be a non-empty string", spec.boundary_type))
    configured_allowed_paths = spec.config.get("allowed_paths")
    if configured_allowed_paths is not None and not (
        isinstance(configured_allowed_paths, list) and all(isinstance(path, str) and path.strip() for path in configured_allowed_paths)
    ):
        findings.append(
            _boundary_finding(
                "BOUNDARY.CONFIG.ALLOWED_PATHS",
                "boundary.config.allowed_paths must be a list of non-empty strings",
                spec.boundary_type,
            )
        )
    return tuple(findings)


def _boundary_info(graph: GraphConfig) -> dict[str, object]:
    spec = graph.boundary
    if spec is None:
        return {}
    return {
        "type": spec.boundary_type,
        "consumes": list(spec.consumes),
        "provides": list(spec.provides),
        "allowed_paths": list(spec.allowed_paths),
        "run_dir": spec.config.get("run_dir", ""),
    }


def _boundary_finding(rule_id: str, message: str, object_id: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="boundary",
        object_id=object_id,
        failure_layer="boundary",
        message=message,
        suggested_fix_type="fix_boundary",
    )


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


def _base_lib_finding_to_health(finding: BaseLibFinding) -> HealthFinding:
    return HealthFinding(
        rule_id=finding.rule_id,
        severity=finding.severity,
        object_type=finding.object_type,
        object_id=finding.object_id,
        source_location=finding.source_location,
        failure_layer=finding.failure_layer,
        message=finding.message,
        suggested_fix_type=finding.suggested_fix_type,
        details=finding.details,
    )


def _append_dependency_chain_findings(
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
    node_name: str,
    summary: BaseLibDependencySummary,
    policy: PurityPolicy,
) -> None:
    if summary.longest_chain_length > policy.max_dependency_chain_length:
        target = errors
        severity = "error"
        limit = policy.max_dependency_chain_length
    elif summary.longest_chain_length > policy.warn_dependency_chain_length:
        target = warnings
        severity = "warning"
        limit = policy.warn_dependency_chain_length
    else:
        return
    target.append(
        HealthFinding(
            rule_id="NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP",
            severity=severity,
            object_type="node",
            object_id=node_name,
            failure_layer="base_lib",
            message=f"node base_lib dependency chain length is {summary.longest_chain_length} > {limit}",
            suggested_fix_type="fix_base_lib",
            details=summary.to_dict() | {"limit": limit},
        )
    )


def _matching_unhealthy_base_module(imported: str, unhealthy: set[str]) -> str:
    for module in unhealthy:
        if imported == module or imported.startswith(f"{module}.") or module.startswith(f"{imported}."):
            return module
    return ""


def _validate_nodesets(graph: GraphConfig, *, registry: NodeRegistry) -> tuple[tuple[HealthFinding, ...], tuple[HealthFinding, ...]]:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    references = _nodeset_references(graph)
    for nodeset in graph.nodesets.values():
        errors.extend(_validate_nodeset_metadata(nodeset))
        errors.extend(_validate_nodeset_contract(nodeset))
        errors.extend(_validate_nodeset_key_scope(nodeset))
        try:
            GraphCompiler().compile(nodeset.graph)
        except GraphCompileError as exc:
            errors.append(
                _nodeset_finding(
                    "NODESET.GRAPH.COMPILE",
                    nodeset.name,
                    f"nodeset internal graph failed to compile: {exc}",
                    details={"compile_error": str(exc)},
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


def _validate_node_types_in_scope(nodes, nodesets, *, registry: NodeRegistry, owner: str) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for node in nodes:
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
                    details={
                        "expected_requires": list(nodeset.requires),
                        "actual_requires": list(node.requires),
                        "owner": owner,
                    },
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
                    details={
                        "expected_provides": list(nodeset.provides),
                        "actual_provides": list(node.provides),
                        "owner": owner,
                    },
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
    for field_name in ("requires", "provides", "exports"):
        values = tuple(getattr(nodeset, field_name, ()))
        if any(not str(value).strip() for value in values) or len(set(values)) != len(values):
            findings.append(_nodeset_finding("NODESET.CONTRACT.KEYS", nodeset.name, f"nodeset.{field_name} must contain unique non-empty keys", details={"field": field_name}))
    if not nodeset.provides:
        findings.append(_nodeset_finding("NODESET.CONTRACT.PROVIDES", nodeset.name, "nodeset.provides must declare at least one output key"))
    if not nodeset.exports:
        findings.append(_nodeset_finding("NODESET.CONTRACT.EXPORTS", nodeset.name, "nodeset.exports must declare at least one exported key"))
    if not set(nodeset.exports) <= set(nodeset.provides):
        findings.append(
            _nodeset_finding(
                "NODESET.CONTRACT.EXPORTS_NOT_PROVIDES",
                nodeset.name,
                "nodeset.exports must be a subset of nodeset.provides",
                details={"exports": list(nodeset.exports), "provides": list(nodeset.provides)},
            )
        )
    return tuple(findings)


def _validate_nodeset_key_scope(nodeset) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    internal_provided = {key for node in nodeset.graph.nodes for key in node.provides}
    internal_required = {key for node in nodeset.graph.nodes for key in node.requires}
    if not set(nodeset.exports) <= internal_provided:
        findings.append(
            _nodeset_finding(
                "NODESET.EXPORT.UNKNOWN_KEY",
                nodeset.name,
                "nodeset exports keys not produced internally",
                details={"missing_exports": sorted(set(nodeset.exports) - internal_provided)},
            )
        )
    if not set(nodeset.provides) <= set(nodeset.exports):
        findings.append(
            _nodeset_finding(
                "NODESET.KEY_LEAK",
                nodeset.name,
                "nodeset.provides must not expose keys outside exports",
                details={"leaked_keys": sorted(set(nodeset.provides) - set(nodeset.exports))},
            )
        )
    external_inputs = set(nodeset.graph.inputs) | (internal_required - internal_provided)
    if not external_inputs <= set(nodeset.requires):
        findings.append(
            _nodeset_finding(
                "NODESET.INPUT_SCOPE",
                nodeset.name,
                "nodeset internal inputs must be declared in nodeset.requires",
                details={"undeclared_inputs": sorted(external_inputs - set(nodeset.requires))},
            )
        )
    internal_only = internal_provided - set(nodeset.exports)
    leaked = internal_only & set(nodeset.provides)
    if leaked:
        findings.append(
            _nodeset_finding(
                "NODESET.INTERNAL_KEY_LEAK",
                nodeset.name,
                "nodeset internal intermediate keys must not leak through provides",
                details={"leaked_keys": sorted(leaked)},
            )
        )
    return tuple(findings)


def _nodeset_references(graph: GraphConfig) -> dict[str, tuple[str, ...]]:
    refs: dict[str, tuple[str, ...]] = {}
    for name, nodeset in graph.nodesets.items():
        refs[name] = tuple(
            node.node_type.removeprefix("nodeset.")
            for node in nodeset.graph.nodes
            if node.node_type.startswith("nodeset.")
        )
    return refs


def _nodeset_cycles(references: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    cycles: list[tuple[str, ...]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def dfs(name: str) -> None:
        if name in visiting:
            index = visiting.index(name)
            cycle = tuple((*visiting[index:], name))
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


def _append_nodeset_finding(
    target: list[HealthFinding],
    grouped: dict[str, list[dict[str, object]]],
    finding: HealthFinding,
) -> None:
    target.append(finding)
    nodeset_name = str(finding.details.get("nodeset", finding.object_id))
    grouped.setdefault(nodeset_name, []).append(finding.to_dict())
