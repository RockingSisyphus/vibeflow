from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

from .config_loader import ConfigLoadError, load_config_document
from .config_schema import collect_config_schema_findings
from .health_types import HealthFinding, HealthReport
from .plugin import load_plugins_from_config
from .policy import default_effective_policy, resolve_effective_policy
from .summaries import summarize_mapping

if TYPE_CHECKING:
    from .boundary import BoundaryRegistry
    from .graph_config import GraphConfig
    from .registry import NodeRegistry


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
    run_dir = _prepare_run_dir(run_root, actual_run_id)
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))

    document = _load_document_or_refuse(path, run_dir, actual_run_id)
    plugin_registry = _load_plugins_or_refuse(document.data, path, run_dir, actual_run_id)
    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
        plugin_registry=plugin_registry,
    )
    effective_policy = policy_result.effective_policy.to_dict()
    _write_json(run_dir / "effective_policy.json", effective_policy)
    _refuse_on_schema_findings(document.data, policy_result.findings, effective_policy, run_dir, actual_run_id)
    graph, compiled = _compile_or_refuse(document.data, plugin_registry, effective_policy, run_dir, actual_run_id)
    health = _validate_run_health(graph, registry, boundary_registry, plugin_registry, policy_result, effective_policy)
    _write_preflight_artifacts(run_dir, graph, compiled, health)
    _refuse_on_health_failure(health, run_dir, actual_run_id)
    context = _execute_runtime(graph, registry, boundary_registry, plugin_registry, initial, run_dir)
    _write_json(run_dir / "output_summary.json", summarize_mapping(dict(context.iter_flat_items())))
    return CheckedRunResult(actual_run_id, run_dir, health, context)


def _prepare_run_dir(run_root: str | Path | None, run_id: str) -> Path:
    run_dir = (Path(run_root) if run_root is not None else Path("runs")) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _load_document_or_refuse(path: Path, run_dir: Path, run_id: str):
    try:
        return load_config_document(path)
    except ConfigLoadError as exc:
        health = _load_error_report(exc)
        _write_refused_artifacts(run_dir, health, include_effective_policy=True)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError("run refused: config load failed", result) from exc


def _load_plugins_or_refuse(config_data: Mapping[str, Any], path: Path, run_dir: Path, run_id: str):
    plugin_registry, plugin_findings = load_plugins_from_config(config_data, base_path=path.parent)
    if plugin_findings:
        health = HealthReport(
            status="ERROR",
            errors=tuple(plugin_findings),
            effective_policy=default_effective_policy().to_dict(),
        )
        _write_refused_artifacts(run_dir, health, include_effective_policy=True)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError("run refused: plugin load failed", result)
    return plugin_registry


def _refuse_on_schema_findings(
    config_data: Mapping[str, Any],
    policy_findings: tuple[HealthFinding, ...],
    effective_policy: dict[str, Any],
    run_dir: Path,
    run_id: str,
) -> None:
    schema_findings = (*collect_config_schema_findings(config_data), *policy_findings)
    if schema_findings:
        health = _schema_health_report(schema_findings, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)


def _schema_health_report(findings: tuple[HealthFinding, ...], effective_policy: dict[str, Any]) -> HealthReport:
    status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin"} for finding in findings) else "FAIL"
    return HealthReport(
        status=status,
        errors=tuple(finding for finding in findings if finding.severity == "error"),
        warnings=tuple(finding for finding in findings if finding.severity == "warning"),
        effective_policy=effective_policy,
    )


def _compile_or_refuse(
    config_data: Mapping[str, Any],
    plugin_registry,
    effective_policy: dict[str, Any],
    run_dir: Path,
    run_id: str,
):
    from .compiler import GraphCompiler
    from .graph_config import GraphConfigError, parse_graph_config

    try:
        graph = parse_graph_config(config_data)
        compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
    except (GraphConfigError, Exception) as exc:
        health = _compile_health_report(exc, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result) from exc
    return graph, compiled


def _compile_health_report(exc: Exception, effective_policy: dict[str, Any]) -> HealthReport:
    return HealthReport(
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


def _validate_run_health(
    graph: GraphConfig,
    registry: NodeRegistry,
    boundary_registry: BoundaryRegistry | None,
    plugin_registry,
    policy_result,
    effective_policy: dict[str, Any],
) -> HealthReport:
    from .health import validate_graph_health

    health = validate_graph_health(
        graph,
        registry=registry,
        boundary_registry=boundary_registry,
        plugin_registry=plugin_registry,
        purity_policy=policy_result.effective_policy.to_purity_policy(),
    )
    return replace(health, effective_policy=effective_policy)


def _write_preflight_artifacts(run_dir: Path, graph: GraphConfig, compiled, health: HealthReport) -> None:
    from .mermaid import compiled_graph_payload, export_mermaid

    _write_json(run_dir / "health_report.json", health.to_dict())
    _write_json(run_dir / "compiled_graph.json", compiled_graph_payload(graph, compiled))
    (run_dir / "graph.mmd").write_text(export_mermaid(graph, compiled=compiled, health_report=health), encoding="utf-8")


def _refuse_on_health_failure(health: HealthReport, run_dir: Path, run_id: str) -> None:
    if health.status in {"FAIL", "ERROR"}:
        _ensure_trace_files(run_dir)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)


def _execute_runtime(
    graph: GraphConfig,
    registry: NodeRegistry,
    boundary_registry: BoundaryRegistry | None,
    plugin_registry,
    initial: Mapping[str, Any] | None,
    run_dir: Path,
):
    from .runtime import PipelineRuntime

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
    return context


def _write_refused_artifacts(run_dir: Path, health: HealthReport, *, include_effective_policy: bool = False) -> None:
    if include_effective_policy:
        _write_json(run_dir / "effective_policy.json", health.effective_policy)
    _write_json(run_dir / "health_report.json", health.to_dict())
    _ensure_trace_files(run_dir)


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


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_trace_files(run_dir: Path) -> None:
    for name in ("runtime_trace.jsonl", "boundary_trace.jsonl"):
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
