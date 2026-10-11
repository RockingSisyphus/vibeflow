"""Stable, serialisable result models for repository checks."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Mapping, Sequence


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True, slots=True)
class SourceLocation:
    path: str
    line: int = 1
    column: int = 0

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line, "column": self.column}


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    subject_type: str
    subject_id: str
    source_location: SourceLocation
    message: str
    suggested_fix: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITY_ORDER:
            raise ValueError(f"unsupported severity: {self.severity}")

    def identity(self) -> tuple[object, ...]:
        location = self.source_location
        return (
            self.code,
            self.severity,
            self.subject_type,
            self.subject_id,
            location.path,
            location.line,
            location.column,
            self.message,
        )

    def sort_key(self) -> tuple[object, ...]:
        location = self.source_location
        return (
            _SEVERITY_ORDER[self.severity],
            location.path,
            location.line,
            location.column,
            self.code,
            self.subject_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "source_location": self.source_location.to_dict(),
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class Report:
    profile: str
    findings: tuple[Finding, ...]
    schema_version: str = "vibeflow.repository-quality.v1"

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    @property
    def summary(self) -> dict[str, int]:
        counts = {"error": 0, "warning": 0, "info": 0}
        for finding in self.findings:
            counts[finding.severity] += 1
        return {"total": len(self.findings), **counts}

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "ok": self.ok,
            "summary": self.summary,
            "findings": [item.to_dict() for item in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        )

    def to_text(self) -> str:
        summary = self.summary
        status = "PASS" if self.ok else "FAIL"
        lines = [
            f"[{self.profile}] {status} "
            f"({summary['error']} error, {summary['warning']} warning, "
            f"{summary['info']} info)"
        ]
        for finding in self.findings:
            location = finding.source_location
            lines.append(
                f"{finding.severity.upper()} {finding.code} "
                f"{location.path}:{location.line}:{location.column} "
                f"{finding.message}"
            )
            if finding.suggested_fix:
                lines.append(f"  fix: {finding.suggested_fix}")
        return "\n".join(lines)


def make_report(profile: str, findings: Sequence[Finding]) -> Report:
    unique = {item.identity(): item for item in findings}
    return Report(
        profile=profile,
        findings=tuple(sorted(unique.values(), key=Finding.sort_key)),
    )


__all__ = ["Finding", "Report", "SourceLocation", "make_report"]

