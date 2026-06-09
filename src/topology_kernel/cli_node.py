from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from .base_lib import node_base_lib_imports, scan_base_lib, summarize_base_lib_dependency_chain
from .cli_reports import error_report, fail_report
from .health_base_lib import append_dependency_chain_findings, base_lib_finding_to_health, matching_unhealthy_base_module
from .health_types import HealthFinding, HealthReport
from .node import NodeContract, NodeInfo, PureNode
from .policy import resolve_effective_policy
from .purity import collect_node_metrics, validate_node_class


def inspect_node_payload(
    *,
    node_type: str,
    module_path: Path | None,
    class_name: str | None,
    policy_path: Path | None,
) -> tuple[dict[str, object], int]:
    if module_path is None:
        report = fail_report(
            "NODE.INSPECT.MODULE_REQUIRED",
            "inspect-node currently requires --module because no project registry loader is configured",
            "node",
            node_type,
            "schema",
        )
        return {"health": report.to_dict()}, 1
    try:
        node_cls = load_node_class(module_path, node_type=node_type, class_name=class_name)
    except (OSError, ImportError, AttributeError, TypeError, ValueError) as exc:
        report = error_report("NODE.INSPECT.LOAD_ERROR", str(exc), "node", node_type, "schema")
        return {"health": report.to_dict()}, 1

    policy_result = resolve_effective_policy({}, config_path=module_path, explicit_policy_path=policy_path)
    effective_policy = policy_result.effective_policy.to_dict()
    if policy_result.findings:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax"} for finding in policy_result.findings) else "FAIL"
        report = HealthReport(status=status, errors=tuple(policy_result.findings), effective_policy=effective_policy)
        return {"health": report.to_dict()}, 1

    report, base_report, dependency_summary = _inspect_node_health(node_cls, node_type, policy_result)
    source = class_source(node_cls)
    metrics = collect_node_metrics(node_cls)
    payload = {
        "health": report.to_dict(),
        "node": {
            "class_name": node_cls.__name__,
            "type_key": getattr(getattr(node_cls, "NODE_INFO", None), "type_key", ""),
            "metadata": node_info_payload(getattr(node_cls, "NODE_INFO", None)),
            "contract": contract_payload(getattr(node_cls, "CONTRACT", None)),
            "source": {"path": inspect.getsourcefile(node_cls) or "", "lines": len(source.splitlines()) if source else 0, "bytes": len(source.encode("utf-8")) if source else 0},
            "metrics": metrics.to_dict(),
        },
        "base_lib": base_report.to_dict(),
        "base_lib_dependency_chain": dependency_summary.to_dict(),
    }
    return payload, 0 if report.status in {"PASS", "CONCERNS"} else 1


def load_node_class(module_path: Path, *, node_type: str, class_name: str | None) -> type[PureNode]:
    if not module_path.exists():
        raise OSError(f"module file does not exist: {module_path}")
    module_name = f"_topology_kernel_inspect_{abs(hash(module_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if class_name:
        node_cls = getattr(module, class_name)
        if not isinstance(node_cls, type):
            raise TypeError(f"{class_name} is not a class")
        return node_cls
    matches = []
    for value in module.__dict__.values():
        info = getattr(value, "NODE_INFO", None)
        if isinstance(value, type) and isinstance(info, NodeInfo) and info.type_key == node_type:
            matches.append(value)
    if not matches:
        raise ValueError(f"no node class with NODE_INFO.type_key={node_type!r}")
    if len(matches) > 1:
        raise ValueError(f"multiple node classes with NODE_INFO.type_key={node_type!r}; pass --class")
    return matches[0]


def node_info_payload(info: object) -> dict[str, object]:
    if not isinstance(info, NodeInfo):
        return {}
    return {
        "type_key": info.type_key,
        "display_name": info.display_name,
        "category": info.category,
        "description": info.description,
        "version": info.version,
        "purity": info.purity,
    }


def contract_payload(contract: object) -> dict[str, object]:
    if not isinstance(contract, NodeContract):
        return {}
    return {
        "requires": list(contract.requires),
        "provides": list(contract.provides),
        "input_semantics": {key: list(value) for key, value in contract.input_semantics.items()},
        "output_semantics": {key: list(value) for key, value in contract.output_semantics.items()},
        "params_schema": dict(contract.params_schema),
        "output_schema": dict(contract.output_schema),
        "examples": [dict(example) for example in contract.examples],
    }


def class_source(node_cls: type[PureNode]) -> str:
    try:
        return inspect.getsource(node_cls)
    except (OSError, TypeError):
        return ""


def _inspect_node_health(node_cls: type[PureNode], node_type: str, policy_result) -> tuple[HealthReport, object, BaseLibDependencySummary]:
    policy = policy_result.effective_policy.to_purity_policy()
    known_classes = _module_node_class_names(node_cls)
    violations = validate_node_class(
        node_cls,
        policy=policy,
        expected_type=node_type,
        known_node_class_names=tuple(name for name in known_classes if name != node_cls.__name__),
        scan_module=True,
    )
    errors, warnings = _violation_findings(violations, node_type)
    base_report = scan_base_lib(Path(inspect.getsourcefile(node_cls) or ".").parent, policy=policy)
    unhealthy_base_modules = {finding.object_id for finding in base_report.findings}
    dependency_summary = summarize_base_lib_dependency_chain(node_base_lib_imports(node_cls), base_report)
    append_dependency_chain_findings(errors, warnings, node_type, dependency_summary, policy)
    _append_base_lib_findings(errors, warnings, base_report.findings)
    _append_indirect_base_lib_findings(errors, node_type, node_base_lib_imports(node_cls), unhealthy_base_modules)
    report = HealthReport(status="FAIL" if errors else "CONCERNS" if warnings else "PASS", errors=tuple(errors), warnings=tuple(warnings), effective_policy=policy_result.effective_policy.to_dict())
    return report, base_report, dependency_summary


def _violation_findings(violations, node_type: str) -> tuple[list[HealthFinding], list[HealthFinding]]:
    errors: list[HealthFinding] = []
    warnings: list[HealthFinding] = []
    for violation in violations:
        finding = HealthFinding(
            rule_id=violation.rule_id,
            severity=violation.severity,
            object_type="node",
            object_id=node_type,
            source_location=violation.source_location,
            failure_layer=violation.failure_layer,
            message=violation.message,
            suggested_fix_type=violation.suggested_fix_type,
            details={"legacy_code": violation.code, **dict(violation.details)},
        )
        (warnings if violation.severity == "warning" else errors).append(finding)
    return errors, warnings


def _append_base_lib_findings(errors: list[HealthFinding], warnings: list[HealthFinding], findings: tuple[BaseLibFinding, ...]) -> None:
    for base_finding in findings:
        finding = base_lib_finding_to_health(base_finding)
        (warnings if base_finding.severity == "warning" else errors).append(finding)


def _append_indirect_base_lib_findings(errors: list[HealthFinding], node_type: str, imports: tuple[str, ...], unhealthy: set[str]) -> None:
    for imported in imports:
        matched = matching_unhealthy_base_module(imported, unhealthy)
        if matched:
            errors.append(
                HealthFinding(
                    rule_id="NODE.BASE_LIB.INDIRECT_VIOLATION",
                    severity="error",
                    object_type="node",
                    object_id=node_type,
                    failure_layer="base_lib",
                    message=f"node imports unhealthy base_lib module: {imported} -> {matched}",
                    suggested_fix_type="fix_base_lib",
                    details={"imported_module": imported, "unhealthy_base_lib": matched},
                )
            )


def _module_node_class_names(node_cls: type[PureNode]) -> tuple[str, ...]:
    module = sys.modules.get(node_cls.__module__)
    if module is None:
        return ()
    names = [value.__name__ for value in module.__dict__.values() if isinstance(value, type) and isinstance(getattr(value, "NODE_INFO", None), NodeInfo)]
    return tuple(sorted(set(names)))
