"""Nodeset maintainability checks shared by JavaScript audit and build."""

from __future__ import annotations

from vibeflow.core.flow import GraphConfig
from vibeflow.core.quality.nodesets import nodeset_quality_findings
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError


DEFAULT_NODESET_MAX_DEPTH = 4


def check_nodeset_depth(
    graph: GraphConfig, *, max_depth: int = DEFAULT_NODESET_MAX_DEPTH
) -> None:
    findings = nodeset_quality_findings(graph, max_depth=max_depth)
    errors = tuple(finding for finding in findings if finding.severity == "error")
    if not errors:
        return
    finding = errors[0]
    raise ProjectBuildError(
        finding.rule_id,
        finding.message,
        diagnostics=(
            dict(finding.details),
            *(item.to_dict() for item in findings if item.severity == "warning"),
        ),
    )


def nodeset_width_warnings(graph: GraphConfig) -> tuple[dict[str, object], ...]:
    return tuple(
        finding.to_dict()
        for finding in nodeset_quality_findings(graph)
        if finding.severity == "warning"
    )
