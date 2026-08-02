"""Python planned-stub adapter for Core planned health events."""

from __future__ import annotations

from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.workflow_rules.planned import (
    PlannedImplementationCheck,
    behavior_details,
    planned_health_events,
)
from vibeflow.targets.python.project.planned_files import validate_python_stub_file


def append_planned_findings(graph, state) -> None:
    for event in planned_health_events(graph):
        if isinstance(event, HealthFinding):
            target = state.warnings if event.severity == "warning" else state.errors
            target.append(event)
            continue
        _append_python_stub_findings(event, state)


def _append_python_stub_findings(
    request: PlannedImplementationCheck,
    state,
) -> None:
    state.warnings.append(
        HealthFinding(
            rule_id="GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY",
            severity="warning",
            object_type=request.object_type,
            object_id=request.object_id,
            failure_layer="topology",
            message=(
                f"{request.object_type} '{request.object_id}' uses planned "
                "python_stub for development tests only"
            ),
            suggested_fix_type="replace_stub_with_implementation",
            details=behavior_details(request.behavior),
        )
    )
    for finding in validate_python_stub_file(
        request.behavior,
        project_root=request.project_root,
        object_type=request.object_type,
        object_id=request.object_id,
    ):
        state.errors.append(finding)

__all__ = ["append_planned_findings"]
