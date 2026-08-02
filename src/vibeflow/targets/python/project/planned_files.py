"""Filesystem adapter for Python planned-stub source validation."""

from __future__ import annotations

from pathlib import Path

from vibeflow.core.findings import HealthFinding
from vibeflow.core.planned import (
    PLANNED_BEHAVIOR_PYTHON_STUB,
    PlannedBehavior,
)
from vibeflow.targets.python.project.planned import (
    planned_stub_finding,
    validate_python_stub_source,
)
from vibeflow.targets.python.runtime.support.planned import (
    resolve_stub_module_path,
)


def validate_python_stub_file(
    behavior: PlannedBehavior,
    *,
    project_root: str | Path | None,
    object_type: str,
    object_id: str,
) -> tuple[HealthFinding, ...]:
    if behavior.kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        return ()
    try:
        path = resolve_stub_module_path(behavior.stub_module, project_root)
    except ValueError as exc:
        return (
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_PATH",
                str(exc),
                object_type,
                object_id,
            ),
        )
    if not path.is_file():
        return (
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_MISSING",
                f"planned python_stub file does not exist: {path}",
                object_type,
                object_id,
            ),
        )
    try:
        source_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return (
            planned_stub_finding(
                "GRAPH.PLANNED.STUB_READ",
                f"planned python_stub file cannot be read: {exc}",
                object_type,
                object_id,
            ),
        )
    return validate_python_stub_source(
        source_text,
        path=str(path),
        object_type=object_type,
        object_id=object_id,
    )

__all__ = ["validate_python_stub_file"]
