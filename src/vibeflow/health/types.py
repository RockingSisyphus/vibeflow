from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping


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
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    @property
    def code(self) -> str:
        return self.rule_id

    @property
    def subject(self) -> str:
        return self.object_id

    def to_dict(self) -> dict[str, object]:
        payload = {
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
