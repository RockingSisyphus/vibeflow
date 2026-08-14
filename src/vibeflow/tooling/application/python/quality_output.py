"""Text presentation for source-quality reports."""

from __future__ import annotations

import json
from typing import Mapping

from vibeflow.core.quality import QualityReport


def format_quality_summary(
    report: QualityReport,
    *,
    max_findings: int = 30,
) -> str:
    payload = report.to_dict()
    summary = payload["summary"]
    from vibeflow.core.result_scope import add_result_scope, format_result_scope

    scoped_payload = add_result_scope(
        payload,
        "vibeflow_quality",
        checked_ids=None,
    )

    lines = [
        format_result_scope(scoped_payload),
        (
            f"root={report.root} files={summary['files']} "
            f"errors={summary['errors']} warnings={summary['warnings']} "
            f"score={summary['score']} "
            f"longest_dependency_chain={summary['longest_dependency_chain_length']}"
        ),
    ]
    scope_line = _scope_summary_line(payload.get("scope_summary", {}))
    if scope_line:
        lines.append(scope_line)
    for module in report.longest_dependency_chain:
        lines.append(f"  chain: {module}")
    lines.extend(_top_offender_lines(payload.get("top_offenders", {})))
    for finding in report.findings[:max_findings]:
        location = finding.source_location.get("path", "")
        line = finding.source_location.get("line")
        suffix = f":{line}" if line else ""
        target = f"{finding.object_type}:{finding.object_id}"
        location_text = f" [{location}{suffix}]" if location else ""
        lines.append(
            f"{finding.severity.upper()} {finding.rule_id} "
            f"{target}{location_text} {finding.message}"
        )
        if finding.details:
            details = json.dumps(
                dict(finding.details),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            lines.append(f"  details: {details}")
    if len(report.findings) > max_findings:
        lines.append(
            f"... {len(report.findings) - max_findings} more findings omitted"
        )
    return "\n".join(lines)


def _top_offender_lines(top_offenders: object) -> list[str]:
    if not isinstance(top_offenders, Mapping):
        return []
    lines: list[str] = []
    files = top_offenders.get("files")
    for file in files[:5] if isinstance(files, list) else []:
        if isinstance(file, Mapping):
            lines.append(
                f"  top-file: {file.get('path')} score={file.get('score')}"
            )
    functions = top_offenders.get("functions")
    for function in functions[:5] if isinstance(functions, list) else []:
        if isinstance(function, Mapping):
            lines.append(
                "  top-function: "
                f"{function.get('object_id')} score={function.get('score')}"
            )
    return lines


def _scope_summary_line(scope_summary: object) -> str:
    if not isinstance(scope_summary, Mapping):
        return ""
    parts = [
        _format_scope_part(scope, scope_summary.get(scope))
        for scope in ("src", "tests", "devtools", "other")
    ]
    parts = [part for part in parts if part]
    return "scopes: " + "; ".join(parts) if parts else ""


def _format_scope_part(scope: str, values: object) -> str:
    if not isinstance(values, Mapping):
        return ""
    return (
        f"{scope}=files:{values.get('files', 0)} "
        f"errors:{values.get('errors', 0)} "
        f"warnings:{values.get('warnings', 0)}"
    )


__all__ = ["format_quality_summary"]
