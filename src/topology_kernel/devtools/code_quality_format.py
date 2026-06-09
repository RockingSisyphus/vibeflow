from __future__ import annotations

from typing import Mapping

from .code_quality_types import QualityReport


def format_quality_summary(report: QualityReport, *, max_findings: int = 30) -> str:
    payload = report.to_dict()
    summary = payload["summary"]
    lines = [
        str(report.status),
        (
            f"root={report.root} files={summary['files']} "
            f"errors={summary['errors']} warnings={summary['warnings']} "
            f"longest_dependency_chain={summary['longest_dependency_chain_length']}"
        ),
    ]
    scope_line = _scope_summary_line(payload.get("scope_summary", {}))
    if scope_line:
        lines.append(scope_line)
    for module in report.longest_dependency_chain:
        lines.append(f"  chain: {module}")
    for finding in report.findings[:max_findings]:
        location = finding.source_location.get("path", "")
        line = finding.source_location.get("line")
        suffix = f":{line}" if line else ""
        lines.append(f"{finding.severity.upper()} {finding.rule_id} {location}{suffix} {finding.message}")
    if len(report.findings) > max_findings:
        lines.append(f"... {len(report.findings) - max_findings} more findings omitted")
    return "\n".join(lines)


def _scope_summary_line(scope_summary: object) -> str:
    if not isinstance(scope_summary, Mapping):
        return ""
    parts = [_format_scope_part(scope, scope_summary.get(scope)) for scope in ("src", "tests", "devtools", "other")]
    parts = [part for part in parts if part]
    return "scopes: " + "; ".join(parts) if parts else ""


def _format_scope_part(scope: str, values: object) -> str:
    if not isinstance(values, Mapping):
        return ""
    return f"{scope}=files:{values.get('files', 0)} errors:{values.get('errors', 0)} warnings:{values.get('warnings', 0)}"
