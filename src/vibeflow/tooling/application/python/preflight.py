"""Shared source-run checks and preflight artifacts, separate from execution."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.core.flow import GraphConfig
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime.options import runtime_options as normalize_runtime_options
from vibeflow.tooling.application.python.project.resource_bindings import PythonResources
from vibeflow.tooling.application.python.execution import (
    CheckedRunError, CheckedRunResult, _ensure_trace_files, _write_json,
)

def _write_preflight_artifacts(run_dir: Path, graph: GraphConfig, compiled, health: HealthReport, *, registry: NodeRegistry | None = None, resources: PythonResources | None = None, prepared=None) -> None:
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
    from vibeflow.tooling.application.python.presentation.compiled_document import compiled_graph_payload
    from vibeflow.tooling.application.python.preview_run import start_run_preview
    from vibeflow.tooling.presentation.preview.diagnostics import incidental_preview

    prepared = prepared or prepare_python_presentation(graph, compiled=compiled, registry=registry, resources=resources)
    _write_json(run_dir / "health_report.json", health.to_dict())
    _write_json(run_dir / "compiled_graph.json", compiled_graph_payload(prepared.graph, prepared.compiled, resources=resources))
    incidental_preview(start_run_preview, prepared=prepared, run_dir=run_dir, health=health, error_path=run_dir / "preview.error.txt")

def _refuse_on_health_failure(health: HealthReport, run_dir: Path, run_id: str) -> None:
    if health.status in {"FAIL", "ERROR"}:
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)

def _refuse_on_planned_run(
    graph: GraphConfig,
    health: HealthReport,
    run_dir: Path,
    run_id: str,
    *,
    registry: NodeRegistry,
    resources: PythonResources,
    runtime_options: object | None,
    compiled=None,
    prepared=None,
    entry: str | None = None,
) -> None:
    from vibeflow.targets.python.runtime.helpers import planned_items

    options = normalize_runtime_options(runtime_options)
    from vibeflow.core.workflows.entries import execution_graph, project_entry
    selected = project_entry(graph, compiled, entry)[0] if graph.entries else graph
    planned = planned_items(execution_graph(selected))
    if not planned:
        return
    if options.allow_planned_stub and all(item.get("behavior") == "python_stub" for item in planned):
        return
    planned_ids = [str(item.get("id", "")) for item in planned]
    non_stub = [str(item.get("id", "")) for item in planned if item.get("behavior") != "python_stub"]
    reason = "planned nodes/nodeset_types cannot run"
    if options.allow_planned_stub:
        reason = "only planned python_stub nodes/nodeset_types can run with allow_planned_stub"
    error = HealthFinding(
        rule_id="GRAPH.PLANNED.NODE_IN_RUN",
        severity="error",
        object_type="pipeline",
        object_id="pipeline",
        failure_layer="topology",
        message=f"{reason}: " + ", ".join(non_stub or planned_ids),
        suggested_fix_type="implement_node",
        details={"planned": [dict(item) for item in planned], "allow_planned_stub": options.allow_planned_stub},
    )
    failed = replace(health, status="FAIL", errors=(*health.errors, error))
    if prepared is None:
        from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
        prepared = prepare_python_presentation(graph, compiled=compiled, registry=registry, resources=resources)
    _write_preflight_artifacts(run_dir, graph, prepared.compiled, failed, registry=registry,
                              resources=resources, prepared=prepared)
    _ensure_trace_files(run_dir)
    result = CheckedRunResult(run_id, run_dir, failed)
    raise CheckedRunError("run refused: planned nodes are not executable", result)
