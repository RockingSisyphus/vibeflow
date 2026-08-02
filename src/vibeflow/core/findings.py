"""Language-neutral findings and workflow-health reports.

``Finding`` is the common, target-neutral representation used by both
workflow-health validation and source-quality analysis.  The two public report
views intentionally keep their historical field names and JSON shapes; the
compatibility subclasses below only translate those names to the common model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping


_UNSET = object()


@dataclass(frozen=True)
class Finding:
    """A plain in-memory diagnostic with no language or I/O dependencies."""

    code: str
    severity: str
    subject_type: str
    subject_id: str
    message: str
    source_location: Mapping[str, object] = field(default_factory=dict)
    suggested_fix: str = ""
    details: Mapping[str, object] = field(default_factory=dict)
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    @property
    def rule_id(self) -> str:
        return self.code

    @property
    def object_type(self) -> str:
        return self.subject_type

    @property
    def object_id(self) -> str:
        return self.subject_id

    @property
    def subject(self) -> str:
        return self.subject_id

    @property
    def suggested_fix_type(self) -> str:
        return self.suggested_fix

    def common_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "rule_id": self.code,
            "severity": self.severity,
            "object_type": self.subject_type,
            "object_id": self.subject_id,
            "source_location": dict(self.source_location),
            "message": self.message,
            "suggested_fix_type": self.suggested_fix,
            "details": dict(self.details),
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


@dataclass(frozen=True, init=False)
class HealthFinding(Finding):
    rule_source: str = "kernel.default_policy"
    failure_layer: str = ""

    def __init__(
        self,
        rule_id: str | object = _UNSET,
        message: str = "",
        severity: str = "",
        object_type: str | object = _UNSET,
        object_id: str | object = _UNSET,
        source_location: Mapping[str, object] | None = None,
        rule_source: str = "kernel.default_policy",
        failure_layer: str = "",
        suggested_fix_type: str | object = _UNSET,
        details: Mapping[str, object] | None = None,
        root_id: str = "",
        root_path: str = "",
        source_path: str = "",
        *,
        code: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        suggested_fix: str | None = None,
    ) -> None:
        resolved_code = code if rule_id is _UNSET else str(rule_id)
        if resolved_code is None:
            raise TypeError("rule_id is required")
        resolved_type = subject_type if object_type is _UNSET else str(object_type)
        resolved_id = subject_id if object_id is _UNSET else str(object_id)
        resolved_fix = (
            suggested_fix
            if suggested_fix_type is _UNSET
            else str(suggested_fix_type)
        )
        object.__setattr__(self, "code", resolved_code)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "subject_type", resolved_type or "")
        object.__setattr__(self, "subject_id", resolved_id or "")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "source_location", source_location or {})
        object.__setattr__(self, "suggested_fix", resolved_fix or "")
        object.__setattr__(self, "details", details or {})
        object.__setattr__(self, "root_id", root_id)
        object.__setattr__(self, "root_path", root_path)
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "rule_source", rule_source)
        object.__setattr__(self, "failure_layer", failure_layer)

    def to_dict(self) -> dict[str, object]:
        common = self.common_dict()
        payload = {
            "rule_id": common["rule_id"],
            "severity": common["severity"],
            "object_type": common["object_type"],
            "object_id": common["object_id"],
            "source_location": common["source_location"],
            "rule_source": self.rule_source,
            "failure_layer": self.failure_layer,
            "message": common["message"],
            "suggested_fix_type": common["suggested_fix_type"],
            "details": common["details"],
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


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


__all__ = ["Finding", "HealthFinding", "HealthReport"]
