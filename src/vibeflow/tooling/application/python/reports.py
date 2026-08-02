"""Stable health-report construction and text formatting."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.core.flow import GraphConfigError
from vibeflow.targets.python.project.policy import EffectivePolicy
from vibeflow.tooling.project.config_loader import ConfigLoadError
from vibeflow.tooling.application.python.project.types import WorkspaceConfig


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


def config_load_error_report(
    exc: ConfigLoadError,
    *,
    object_type: str,
    object_id: str,
) -> HealthReport:
    from vibeflow.targets.python.project.policy import default_effective_policy

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
    if detail.startswith("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID"):
        return fail_report(
            "CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID",
            str(exc),
            "config",
            str(path),
            "schema",
            effective_policy=effective_policy,
        )
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


def dedupe_findings(
    findings: tuple[HealthFinding, ...],
) -> tuple[HealthFinding, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[HealthFinding] = []
    for finding in findings:
        key = (
            finding.rule_id,
            finding.object_type,
            finding.object_id,
            finding.message,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return tuple(unique)


def format_finding_text(finding: HealthFinding) -> str:
    location = location_text(finding.source_location)
    suffix = f" [{location}]" if location else ""
    text = (
        f"{finding.severity}: {finding.rule_id}: "
        f"{finding.message}{suffix}"
    )
    if finding.details:
        details = json.dumps(
            dict(finding.details),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        text = f"{text}\n  details: {details}"
    return text


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


def annotate_health_report(
    report: HealthReport,
    graph: object,
    *,
    workspace: WorkspaceConfig,
) -> HealthReport:
    """Attach workspace source ownership to graph health findings."""

    return replace(
        report,
        errors=tuple(
            _annotate_graph_finding(finding, graph, workspace=workspace)
            for finding in report.errors
        ),
        warnings=tuple(
            _annotate_graph_finding(finding, graph, workspace=workspace)
            for finding in report.warnings
        ),
        skipped=tuple(
            _annotate_graph_finding(finding, graph, workspace=workspace)
            for finding in report.skipped
        ),
    )


def _workspace_error_report(
    rule_id: str,
    message: str,
    path: Path,
    effective_policy: EffectivePolicy,
) -> HealthReport:
    return HealthReport(
        status="ERROR",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type="workspace",
                object_id=str(path),
                source_location={"path": str(path)},
                failure_layer="workspace",
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=effective_policy.to_dict(),
    )


def _workspace_info(workspace: WorkspaceConfig) -> dict[str, object]:
    return {
        "path": str(workspace.path),
        "roots": [
            {
                "id": root.id,
                "path": str(root.path),
                "config": str(root.config_path),
                "quality_enabled": root.quality_enabled,
            }
            for root in workspace.roots
        ],
    }


def _annotate_graph_finding(
    finding: HealthFinding,
    graph: object,
    *,
    workspace: WorkspaceConfig,
) -> HealthFinding:
    if finding.root_id:
        return finding
    source = _source_for_finding(finding, graph, workspace=workspace)
    if source is None:
        return finding
    return replace(
        finding,
        root_id=source["root_id"],
        root_path=source["root_path"],
        source_path=source["source_path"],
    )


def _source_for_finding(
    finding: HealthFinding,
    graph: object,
    *,
    workspace: WorkspaceConfig,
) -> dict[str, str] | None:
    location_path = str(finding.source_location.get("path", "")).strip()
    if location_path:
        root = workspace.root_for_path(location_path)
        if root is not None:
            return {
                "root_id": root.id,
                "root_path": str(root.path),
                "source_path": location_path,
            }
    if finding.object_type == "nodeset":
        nodeset = graph.nodesets.get(finding.object_id)
        return (
            _source_payload(
                nodeset.root_id,
                nodeset.root_path,
                nodeset.source_path,
            )
            if nodeset is not None
            else None
        )
    if finding.object_type == "node":
        return _node_source_for_finding(finding, graph)
    graph_source = str(getattr(graph, "source_path", ""))
    root = workspace.root_for_path(graph_source)
    if root is not None:
        return {
            "root_id": root.id,
            "root_path": str(root.path),
            "source_path": graph_source,
        }
    return None


def _node_source_for_finding(
    finding: HealthFinding,
    graph: object,
) -> dict[str, str] | None:
    owner_graph = _graph_for_owner(
        graph,
        str(finding.details.get("owner", "")),
    )
    if owner_graph is not None:
        return _source_payload(
            owner_graph.root_id,
            owner_graph.root_path,
            owner_graph.source_path,
        )
    if any(node.id == finding.object_id for node in graph.nodes):
        return _source_payload(
            graph.root_id,
            graph.root_path,
            graph.source_path,
        )
    for nodeset in graph.nodesets.values():
        if any(node.id == finding.object_id for node in nodeset.graph.nodes):
            return _source_payload(
                nodeset.graph.root_id,
                nodeset.graph.root_path,
                nodeset.graph.source_path,
            )
    return None


def _graph_for_owner(graph: object, owner: str) -> object | None:
    if not owner or owner == "pipeline":
        return graph
    if owner.startswith("nodeset:"):
        nodeset = graph.nodesets.get(owner[len("nodeset:") :])
        return nodeset.graph if nodeset is not None else None
    return None


def _source_payload(
    root_id: str,
    root_path: str,
    source_path: str,
) -> dict[str, str] | None:
    if not root_id and not root_path and not source_path:
        return None
    return {
        "root_id": root_id,
        "root_path": root_path,
        "source_path": source_path,
    }


__all__ = [
    "annotate_health_report",
    "config_load_error_report",
    "dedupe_findings",
    "error_report",
    "fail_report",
    "format_finding_text",
    "graph_config_error_report",
    "location_text",
]
