"""Pure composition of normalized workflow findings into a health report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from vibeflow.core.findings import Finding, HealthFinding, HealthReport


@dataclass(frozen=True)
class WorkflowQualityRequest:
    findings: tuple[Finding, ...] = ()
    skipped: tuple[Finding, ...] = ()
    info: Mapping[str, object] = field(default_factory=dict)
    effective_policy: Mapping[str, object] = field(default_factory=dict)


WorkflowHealthReport = HealthReport


def validate_workflow_quality(
    request: WorkflowQualityRequest,
) -> WorkflowHealthReport:
    """Build the workflow report from ordinary, already-normalized facts."""

    normalized = tuple(_as_health_finding(item) for item in request.findings)
    skipped = tuple(_as_health_finding(item) for item in request.skipped)
    errors = tuple(item for item in normalized if item.severity == "error")
    warnings = tuple(item for item in normalized if item.severity == "warning")
    if errors:
        status = "ERROR" if any(item.failure_layer == "plugin" for item in errors) else "FAIL"
    else:
        status = "CONCERNS" if warnings else "PASS"
    return HealthReport(
        status=status,
        errors=errors,
        warnings=warnings,
        skipped=skipped,
        info=dict(request.info),
        effective_policy=dict(request.effective_policy),
    )


def _as_health_finding(finding: Finding) -> HealthFinding:
    if isinstance(finding, HealthFinding):
        return finding
    return HealthFinding(
        rule_id=finding.code,
        severity=finding.severity,
        object_type=finding.subject_type,
        object_id=finding.subject_id,
        source_location=finding.source_location,
        message=finding.message,
        suggested_fix_type=finding.suggested_fix,
        details=finding.details,
        root_id=finding.root_id,
        root_path=finding.root_path,
        source_path=finding.source_path,
    )


__all__ = [
    "WorkflowHealthReport",
    "WorkflowQualityRequest",
    "validate_workflow_quality",
]
