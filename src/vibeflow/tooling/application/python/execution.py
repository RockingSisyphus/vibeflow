"""Checked execution results and delivery shared by source, AOT and launchers.

This module never loads or checks workflow configuration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TYPE_CHECKING
from uuid import uuid4

from vibeflow.core.findings import HealthReport
from vibeflow.targets.python.project.registry import NodeRegistryError

if TYPE_CHECKING:
    from vibeflow.core.flow import GraphConfig
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.tooling.application.python.project.resource_selection import PythonResources

@dataclass(frozen=True)
class CheckedRunResult:
    run_id: str
    run_dir: Path
    health: HealthReport
    context: object | None = None
    has_declared_outputs: bool = False
    public_outputs: Mapping[str, object] = field(default_factory=dict)


def checked_result(run_id, run_dir, health, context, graph, entry=None):
    from vibeflow.core.workflows.entries import choose_entry
    from vibeflow.targets.python.runtime.values import _public_result_value
    selected = choose_entry(graph.entries, graph.default_entry, entry)
    contract = graph.entries[selected].outputs if selected is not None else None
    outputs = graph.outputs if contract is None else contract
    public = {spec.public_name: _public_result_value(context.get(spec.public_name))
        for spec in outputs if context.exists(spec.public_name)}
    return CheckedRunResult(run_id, run_dir, health, context, bool(outputs), public)


@dataclass
class CheckedRunError(RuntimeError):
    message: str
    result: CheckedRunResult

    def __str__(self) -> str:
        return self.message


def _checked_run_error_payload(error):
    from vibeflow.tooling.application.result_scope import add_result_scope
    result = error.result
    return add_result_scope({"status": result.health.status, "run_id": result.run_id,
        "run_dir": str(result.run_dir), "error": str(error), "health": result.health.to_dict()},
        "vibeflow_workflow_execution", checked_ids=())


def _write_execution_report(result):
    """Describe the completed runtime without reopening its source config."""
    from vibeflow.tooling.application.result_scope import add_result_scope
    checked = ["workflow_started", "structural_runtime"]
    if result.context is not None and result.context.get("runtime.qualified_exec_order"):
        checked.append("execution_order")
    if result.has_declared_outputs:
        checked.append("declared_outputs")
    payload = add_result_scope({"status": result.health.status, "run_id": result.run_id,
        "run_dir": str(result.run_dir)}, "vibeflow_workflow_execution", checked_ids=checked)
    _write_json(result.run_dir / "workflow_execution_report.json", payload)
    return payload


def _checked_runtime_binding(factory, *, health, run_dir):
    try:
        return factory()
    except NodeRegistryError as cause:
        findings = getattr(cause, "findings", ())
        if not findings:
            raise
        failed = replace(health or HealthReport(status="ERROR"), status="ERROR",
            errors=(*(health.errors if health is not None else ()), *findings))
        _write_refused_artifacts(run_dir, failed)
        raise CheckedRunError("run refused: implementation binding failed",
            CheckedRunResult(run_dir.name, run_dir, failed)) from cause


def _execute_runtime(
    graph: GraphConfig,
    registry: NodeRegistry,
    plugin_registry,
    initial: Mapping[str, Any] | None,
    run_dir: Path,
    runtime_options: object | None,
    resources: PythonResources,
    *,
    capabilities: Mapping[str, object] | None = None,
    delegate_cli: bool = False,
    health: HealthReport | None = None,
    entry: str | None = None,
    signal=None,
):
    from vibeflow.targets.python.runtime.engine import PipelineRuntime

    from vibeflow.targets.python.sdk.loading import source_paths

    with source_paths(getattr(registry, "source_roots", ())):
        runtime = _checked_runtime_binding(lambda: PipelineRuntime(
            graph, registry=registry, plugin_registry=plugin_registry, run_dir=run_dir,
            global_config=resources.global_config, runtime_options=runtime_options,
            capabilities=capabilities, delegate_cli=delegate_cli, entry=entry), health=health, run_dir=run_dir)
        unsubscribe = signal.subscribe(runtime.request_stop) if signal is not None else lambda: None
        try:
            context = runtime.run(initial)
        finally:
            unsubscribe()
            _ensure_trace_files(run_dir)
        return context


def _write_refused_artifacts(run_dir: Path, health: HealthReport, *, include_effective_policy: bool = False) -> None:
    if include_effective_policy:
        _write_json(run_dir / "effective_policy.json", health.effective_policy)
    _write_json(run_dir / "health_report.json", health.to_dict())
    _ensure_trace_files(run_dir)


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:8]}"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _summarize_run_result(result: object) -> dict[str, object]:
    if not hasattr(result, "to_dict"):
        return {}
    data = result.to_dict()
    if not isinstance(data, Mapping):
        return {}
    return {key: _summarize_result_item(value) for key, value in _iter_result_summary_items(data, prefix="")}


def _iter_result_summary_items(value: object, *, prefix: str):
    if _is_data_envelope_payload(value):
        if prefix:
            yield prefix, value
        return
    if not isinstance(value, Mapping):
        if prefix:
            yield prefix, value
        return
    for key, item in value.items():
        child = f"{prefix}.{key}" if prefix else str(key)
        yield from _iter_result_summary_items(item, prefix=child)


def _summarize_result_item(value: object) -> dict[str, object]:
    if _is_data_envelope_payload(value):
        return {
            "type": "DataEnvelope",
            "key": str(value.get("key", "")),
            "data_type": str(value.get("type", "")),
            "source_node": str(value.get("source_node", "")),
            "value": _summarize_shallow_value(value.get("value")),
        }
    return _summarize_shallow_value(value)


def _summarize_shallow_value(value: object) -> dict[str, object]:
    summary: dict[str, object] = {"type": type(value).__name__}
    if isinstance(value, Mapping):
        summary["size"] = len(value)
        return summary
    if isinstance(value, (list, tuple, set)):
        summary["size"] = len(value)
        return summary
    if isinstance(value, (str, bytes)):
        summary["size"] = len(value)
        return summary
    if value is None or isinstance(value, (int, float, bool)):
        summary["scalar"] = True
        return summary
    if isinstance(value, Path):
        summary["path"] = True
        return summary
    summary["repr_type"] = type(value).__qualname__
    return summary


def _is_data_envelope_payload(value: object) -> bool:
    return isinstance(value, Mapping) and {"key", "type", "value", "source_node"} <= set(value)


def _ensure_trace_files(run_dir: Path) -> None:
    for name in ("runtime_trace.jsonl",):
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
