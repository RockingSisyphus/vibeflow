from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .boundary import BoundaryRegistry
from .compiler import GraphCompiler
from .config_loader import ConfigLoadError, load_config_document
from .config_schema import collect_config_schema_findings
from .graph_config import GraphConfig, GraphConfigError, parse_graph_config
from .health import HealthFinding, HealthReport, validate_graph_health
from .mermaid import compiled_graph_payload, export_mermaid
from .plugin import load_plugins_from_config
from .policy import default_effective_policy, resolve_effective_policy
from .registry import NodeRegistry
from .runtime import PipelineRuntime


@dataclass(frozen=True)
class CheckedRunResult:
    run_id: str
    run_dir: Path
    health: HealthReport
    context: object | None = None


@dataclass
class CheckedRunError(RuntimeError):
    message: str
    result: CheckedRunResult

    def __str__(self) -> str:
        return self.message


def run_checked(
    config_path: str | Path,
    *,
    registry: NodeRegistry,
    boundary_registry: BoundaryRegistry | None = None,
    initial: Mapping[str, Any] | None = None,
    policy_path: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
) -> CheckedRunResult:
    path = Path(config_path)
    actual_run_id = run_id or _new_run_id()
    run_dir = (Path(run_root) if run_root is not None else Path("runs")) / actual_run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "input_summary.json", _summarize_mapping(dict(initial or {})))

    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        health = _load_error_report(exc)
        _write_json(run_dir / "effective_policy.json", health.effective_policy)
        _write_json(run_dir / "health_report.json", health.to_dict())
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(actual_run_id, run_dir, health)
        raise CheckedRunError("run refused: config load failed", result) from exc

    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    if plugin_findings:
        health = HealthReport(
            status="ERROR",
            errors=tuple(plugin_findings),
            effective_policy=default_effective_policy().to_dict(),
        )
        _write_json(run_dir / "effective_policy.json", health.effective_policy)
        _write_json(run_dir / "health_report.json", health.to_dict())
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(actual_run_id, run_dir, health)
        raise CheckedRunError("run refused: plugin load failed", result)

    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
        plugin_registry=plugin_registry,
    )
    effective_policy = policy_result.effective_policy.to_dict()
    _write_json(run_dir / "effective_policy.json", effective_policy)

    schema_findings = (*collect_config_schema_findings(document.data), *policy_result.findings)
    if schema_findings:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin"} for finding in schema_findings) else "FAIL"
        health = HealthReport(
            status=status,
            errors=tuple(finding for finding in schema_findings if finding.severity == "error"),
            warnings=tuple(finding for finding in schema_findings if finding.severity == "warning"),
            effective_policy=effective_policy,
        )
        _write_json(run_dir / "health_report.json", health.to_dict())
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(actual_run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)

    try:
        graph = parse_graph_config(document.data)
        compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
    except (GraphConfigError, Exception) as exc:
        health = HealthReport(
            status="FAIL",
            errors=(
                HealthFinding(
                    rule_id="GRAPH.COMPILE",
                    severity="error",
                    object_type="pipeline",
                    object_id="pipeline",
                    failure_layer="topology",
                    message=str(exc),
                    suggested_fix_type="fix_config",
                ),
            ),
            effective_policy=effective_policy,
        )
        _write_json(run_dir / "health_report.json", health.to_dict())
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(actual_run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result) from exc

    health = validate_graph_health(
        graph,
        registry=registry,
        boundary_registry=boundary_registry,
        plugin_registry=plugin_registry,
        purity_policy=policy_result.effective_policy.to_purity_policy(),
    )
    health = replace(health, effective_policy=effective_policy)
    _write_json(run_dir / "health_report.json", health.to_dict())
    _write_json(run_dir / "compiled_graph.json", compiled_graph_payload(graph, compiled))
    (run_dir / "graph.mmd").write_text(export_mermaid(graph, compiled=compiled, health_report=health), encoding="utf-8")
    if health.status in {"FAIL", "ERROR"}:
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(actual_run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)

    runtime = PipelineRuntime(
        graph,
        registry=registry,
        boundary_registry=boundary_registry,
        plugin_registry=plugin_registry,
        run_dir=run_dir,
    )
    try:
        context = runtime.run(initial)
    finally:
        _write_runtime_trace(run_dir / "runtime_trace.jsonl", runtime.trace.to_dict())
        _ensure_trace_files(run_dir)
    _write_json(run_dir / "output_summary.json", _summarize_mapping(dict(context.iter_flat_items())))
    return CheckedRunResult(actual_run_id, run_dir, health, context)


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:8]}"


def _load_error_report(exc: ConfigLoadError) -> HealthReport:
    return HealthReport(
        status="ERROR",
        errors=(
            HealthFinding(
                rule_id=exc.rule_id,
                severity="error",
                object_type="config",
                object_id=str(exc.source_location.get("path", "config")),
                source_location=exc.source_location,
                failure_layer=exc.failure_layer,
                message=exc.message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=default_effective_policy().to_dict(),
    )


def _write_runtime_trace(path: Path, trace: Mapping[str, object]) -> None:
    events = trace.get("events", [])
    with path.open("w", encoding="utf-8") as handle:
        if isinstance(events, list):
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        summary = {key: value for key, value in trace.items() if key != "events"}
        summary["kind"] = "runtime_summary"
        handle.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")


def _summarize_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _summarize_value(value) for key, value in values.items()}


def _summarize_value(value: object) -> dict[str, object]:
    summary: dict[str, object] = {"type": type(value).__name__}
    if isinstance(value, Mapping):
        summary["keys"] = sorted(str(key) for key in value.keys())
        summary["size"] = len(value)
    elif isinstance(value, (list, tuple, set)):
        summary["size"] = len(value)
    elif isinstance(value, (str, bytes)):
        summary["size"] = len(value)
    elif value is None or isinstance(value, (int, float, bool)):
        summary["scalar"] = True
    else:
        summary["repr_type"] = type(value).__qualname__
    return summary


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_trace_files(run_dir: Path) -> None:
    for name in ("runtime_trace.jsonl", "boundary_trace.jsonl"):
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
