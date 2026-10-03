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
    _validate_stub_ast,
)
from vibeflow.targets.python.project.source_closure import collect_python_source_facts
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
    findings = list(validate_python_stub_source(
        source_text,
        path=str(path),
        object_type=object_type,
        object_id=object_id,
    ))
    root = Path(project_root or path.parent).resolve()
    import ast
    from dataclasses import replace
    for source in collect_python_source_facts(path, project_root=root):
        if source.path == str(path):
            continue
        if source.load_error or source.parse_error:
            findings.append(replace(planned_stub_finding("GRAPH.PLANNED.STUB_SYNTAX",
                source.load_error or source.parse_error, object_type, object_id),
                source_location={"path": source.path, "line": source.parse_line or 1, "column": source.parse_column or 1}))
            continue
        findings.extend(_validate_stub_ast(ast.parse(source.source, filename=source.path),
            path=source.path, object_type=object_type, object_id=object_id))
    return tuple(findings)

__all__ = ["validate_python_stub_file"]
