"""Target-specific JS/TS completion and dependency contract checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from vibeflow.core.quality import QualityFinding
from vibeflow.targets.javascript.quality.models import (
    JavascriptImplementationQualityFacts,
    JavascriptImportFact,
)


def validate_javascript_quality(
    facts: Sequence[JavascriptImplementationQualityFacts],
) -> tuple[QualityFinding, ...]:
    findings: list[QualityFinding] = []
    for item in facts:
        findings.extend(_completion_findings(item))
        findings.extend(_ownership_findings(item))
        findings.extend(_import_findings(item))
    return tuple(findings)


def quality_findings_from_toolchain(
    rows: Sequence[Mapping[str, object]],
) -> tuple[QualityFinding, ...]:
    """Normalize Node-driver diagnostics into the shared finding model."""

    findings: list[QualityFinding] = []
    for row in rows:
        rule_id = str(row.get("code", row.get("rule_id", ""))).strip()
        if not rule_id:
            continue
        path = str(row.get("path", row.get("source_path", ""))).strip()
        location: dict[str, object] = {}
        if path:
            location["path"] = path
        if row.get("line") is not None:
            location["line"] = row["line"]
        if row.get("column") is not None:
            location["column"] = row["column"]
        findings.append(
            QualityFinding(
                rule_id=rule_id,
                severity=str(row.get("severity", "error")),
                object_type=str(row.get("object_type", "javascript_source")),
                object_id=str(row.get("object_id", path)),
                source_location=location,
                message=str(row.get("message", rule_id)),
                suggested_fix_type=str(row.get("suggested_fix_type", "fix_source")),
                details=(
                    dict(row["details"])
                    if isinstance(row.get("details"), Mapping)
                    else {}
                ),
            )
        )
    return tuple(findings)


def _completion_findings(
    item: JavascriptImplementationQualityFacts,
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    if item.completion not in {"immediate", "suspend"}:
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.COMPLETION.UNKNOWN",
                f"unsupported completion '{item.completion}'",
            )
        )
        return findings
    promise_implementation = item.declared_async or item.returns_promise
    if item.completion == "immediate" and promise_implementation:
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.COMPLETION.IMMEDIATE_PROMISE",
                "immediate implementation is async or returns a Promise",
            )
        )
    elif item.completion == "suspend" and not promise_implementation:
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.COMPLETION.SUSPEND_NON_PROMISE",
                "suspend implementation does not return a Promise",
            )
        )
    return findings


def _ownership_findings(
    item: JavascriptImplementationQualityFacts,
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    if item.hidden_promise_work:
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.PROMISE.UNOWNED",
                "implementation starts Promise work outside its declared completion or TaskPlan",
            )
        )
    if item.registers_listener and item.kind != "host_extension":
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.LISTENER.WRONG_OWNER",
                "event listeners belong in a host_extension",
            )
        )
    if item.has_dynamic_import:
        findings.append(
            _finding(
                item,
                "QUALITY.JAVASCRIPT.IMPORT.DYNAMIC",
                "dynamic import cannot be statically assigned to the build dependency graph",
            )
        )
    return findings


def _import_findings(
    item: JavascriptImplementationQualityFacts,
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for imported in item.imports:
        message = _illegal_import_message(item, imported)
        if message:
            findings.append(
                _finding(
                    item,
                    "QUALITY.JAVASCRIPT.IMPORT.BOUNDARY",
                    message,
                    imported,
                )
            )
    return findings


def _illegal_import_message(
    owner: JavascriptImplementationQualityFacts,
    imported: JavascriptImportFact,
) -> str:
    if imported.destination_kind == "node":
        return "node implementations cannot import another node"
    if owner.kind == "base_lib" and imported.destination_kind in {
        "node",
        "plugin",
        "runtime",
        "capability",
        "host_extension",
    }:
        return f"base_lib cannot import {imported.destination_kind}"
    if owner.kind == "host_extension" and imported.destination_kind != "host_extension":
        return f"host_extension cannot import {imported.destination_kind} source"
    if imported.destination_kind in {"base_lib", "host_extension"} and not imported.declared:
        return f"{imported.destination_kind} dependency is not declared"
    return ""


def _finding(
    owner: JavascriptImplementationQualityFacts,
    rule_id: str,
    message: str,
    imported: JavascriptImportFact | None = None,
) -> QualityFinding:
    location: dict[str, object] = {"path": owner.source_path}
    if imported is not None:
        location.update({"line": imported.line, "column": imported.column})
    return QualityFinding(
        rule_id=rule_id,
        severity="error",
        object_type=owner.kind,
        object_id=owner.implementation_id,
        source_location=location,
        message=message,
        suggested_fix_type="fix_javascript_contract",
        details={
            "target": owner.target,
            "completion": owner.completion,
            **(
                {
                    "specifier": imported.specifier,
                    "destination_kind": imported.destination_kind,
                    "destination_id": imported.destination_id,
                }
                if imported is not None
                else {}
            ),
        },
    )


__all__ = [
    "quality_findings_from_toolchain",
    "validate_javascript_quality",
]
