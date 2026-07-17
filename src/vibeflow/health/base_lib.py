from __future__ import annotations

from vibeflow.base_lib_types import BaseLibDependencySummary, BaseLibFinding
from vibeflow.health.types import HealthFinding


def base_lib_finding_to_health(finding: BaseLibFinding) -> HealthFinding:
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


def append_dependency_chain_findings(
    errors: list[HealthFinding],
    warnings: list[HealthFinding],
    node_name: str,
    summary: BaseLibDependencySummary,
    policy,
) -> None:
    if summary.longest_chain_length > policy.max_dependency_chain_length:
        target, severity, limit = errors, "error", policy.max_dependency_chain_length
    elif summary.longest_chain_length > policy.warn_dependency_chain_length:
        target, severity, limit = warnings, "warning", policy.warn_dependency_chain_length
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


def matching_unhealthy_base_module(imported: str, unhealthy: set[str]) -> str:
    for module in unhealthy:
        if imported == module or imported.startswith(f"{module}.") or module.startswith(f"{imported}."):
            return module
    return ""
