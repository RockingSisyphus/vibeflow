from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .config_loader import ConfigLoadError
from .graph_config import GraphConfigError
from .health_types import HealthFinding, HealthReport
from .policy import default_effective_policy


def error_report(
    rule_id: str,
    message: str,
    object_type: str,
    object_id: str,
    failure_layer: str,
    *,
    source_location: dict[str, object] | None = None,
    effective_policy: Mapping[str, object] | None = None,
) -> HealthReport:
    return HealthReport(
        status="ERROR",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type=object_type,
                object_id=object_id,
                source_location=source_location or {},
                failure_layer=failure_layer,
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=dict(effective_policy or {}),
    )


def fail_report(
    rule_id: str,
    message: str,
    object_type: str,
    object_id: str,
    failure_layer: str,
    *,
    effective_policy: Mapping[str, object] | None = None,
) -> HealthReport:
    return HealthReport(
        status="FAIL",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type=object_type,
                object_id=object_id,
                failure_layer=failure_layer,
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=dict(effective_policy or {}),
    )


def config_load_error_report(exc: ConfigLoadError, *, object_type: str, object_id: str) -> HealthReport:
    return error_report(
        exc.rule_id,
        exc.message,
        object_type,
        object_id,
        exc.failure_layer,
        source_location=exc.source_location,
        effective_policy=default_effective_policy().to_dict(),
    )


def graph_config_error_report(
    exc: GraphConfigError,
    *,
    path: Path,
    effective_policy: Mapping[str, object],
) -> HealthReport:
    detail = getattr(exc, "detail", str(exc))
    if "unknown node" in detail or "references unknown" in detail:
        return fail_report(
            "CONFIG.TOPOLOGY",
            str(exc),
            "pipeline",
            "pipeline",
            "topology",
            effective_policy=effective_policy,
        )
    return fail_report(
        "CONFIG.SCHEMA.PARSE",
        str(exc),
        "config",
        str(path),
        "schema",
        effective_policy=effective_policy,
    )


def dedupe_findings(findings: tuple[HealthFinding, ...]) -> tuple[HealthFinding, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[HealthFinding] = []
    for finding in findings:
        key = (finding.rule_id, finding.object_type, finding.object_id, finding.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return tuple(unique)


def format_finding_text(finding: HealthFinding) -> str:
    location = location_text(finding.source_location)
    suffix = f" [{location}]" if location else ""
    return f"{finding.severity}: {finding.rule_id}: {finding.message}{suffix}"


def location_text(source_location: Mapping[str, object]) -> str:
    path = str(source_location.get("path", "")).strip()
    line = source_location.get("line")
    column = source_location.get("column")
    parts: list[str] = []
    if path:
        parts.append(path)
    if line:
        parts.append(f"line {line}")
    if column:
        parts.append(f"column {column}")
    return ":".join(parts)
