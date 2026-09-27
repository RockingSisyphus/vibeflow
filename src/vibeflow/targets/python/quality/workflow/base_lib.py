from __future__ import annotations

from vibeflow.targets.python.project.base_lib_types import BaseLibDependencySummary, BaseLibFinding
from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.implementation import (
    CallChain, ImplementationLimits, evaluate_base_lib_dependency_chain,
)


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
    finding = evaluate_base_lib_dependency_chain(
        CallChain(summary.longest_chain_length, summary.longest_chain, summary.recursive_chains),
        ImplementationLimits.from_policy(policy),
    )
    if finding is None:
        return
    target = errors if finding.severity == "error" else warnings
    target.append(
        HealthFinding(
            rule_id=finding.rule_id,
            severity=finding.severity,
            object_type="node",
            object_id=node_name,
            failure_layer="base_lib",
            message=finding.message,
            suggested_fix_type=finding.suggested_fix_type,
            details=summary.to_dict() | {"limit": finding.details["limit"]},
        )
    )


def matching_unhealthy_base_module(imported: str, unhealthy: set[str]) -> str:
    for module in unhealthy:
        if imported == module or imported.startswith(f"{module}.") or module.startswith(f"{imported}."):
            return module
    return ""

__all__ = [
    "append_dependency_chain_findings",
    "base_lib_finding_to_health",
    "matching_unhealthy_base_module",
]
