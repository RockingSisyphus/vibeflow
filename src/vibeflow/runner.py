from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from vibeflow.config.loader import ConfigLoadError, load_config_document
from vibeflow.config.resources import ConfigResources, load_config_resources
from vibeflow.config.schema import collect_config_schema_findings
from vibeflow.health.types import HealthFinding, HealthReport
from vibeflow.plugin import load_plugins_from_config
from vibeflow.policy import default_effective_policy, resolve_effective_policy
from vibeflow.runtime.summaries import summarize_mapping

from vibeflow.graph_config import GraphConfig
from vibeflow.graph_config.planned_behavior import project_root_for_config
from vibeflow.registry import NodeRegistry
from vibeflow.runtime.options import runtime_options as normalize_runtime_options


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
    boundary_registry: object | None = None,
    initial: Mapping[str, Any] | None = None,
    policy_path: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
    runtime_options: object | None = None,
) -> CheckedRunResult:
    path = Path(config_path)
    actual_run_id = run_id or _new_run_id()
    if boundary_registry is not None:
        raise ValueError("boundary_registry is removed; use flowchart nodes")
    run_dir = _prepare_run_dir(run_root, actual_run_id)
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))

    document = _load_document_or_refuse(path, run_dir, actual_run_id)
    plugin_registry = _load_plugins_or_refuse(document.data, path, run_dir, actual_run_id)
    resources, resource_findings = load_config_resources(document.data, base_path=path.parent, plugin_registry=plugin_registry)
    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
        plugin_registry=plugin_registry,
    )
    effective_policy = policy_result.effective_policy.to_dict()
    _write_json(run_dir / "effective_policy.json", effective_policy)
    preflight_warnings = _refuse_on_schema_findings(document.data, (*resource_findings, *policy_result.findings), effective_policy, run_dir, actual_run_id)
    graph, compiled = _compile_or_refuse(document.data, plugin_registry, effective_policy, run_dir, actual_run_id, config_path=path)
    health = _validate_run_health(graph, registry, plugin_registry, policy_result, effective_policy, document.nodeset_imports, resources, preflight_warnings=preflight_warnings)
    _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=registry, resources=resources, runtime_options=runtime_options)
    if health.status not in {"FAIL", "ERROR"}:
        compiled = _compile_with_registry_or_refuse(graph, registry, effective_policy, run_dir, actual_run_id)
    try:
        _write_preflight_artifacts(run_dir, graph, compiled, health, registry=registry, resources=resources)
    except Exception:
        if health.status in {"FAIL", "ERROR"}:
            _write_refused_artifacts(run_dir, health)
            _refuse_on_health_failure(health, run_dir, actual_run_id)
        raise
    _refuse_on_health_failure(health, run_dir, actual_run_id)
    context = _execute_runtime(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources)
    _write_json(run_dir / "output_summary.json", _summarize_run_result(context))
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
) -> tuple[HealthFinding, ...]:
    schema_findings = (*collect_config_schema_findings(config_data), *policy_findings)
    errors = tuple(finding for finding in schema_findings if finding.severity == "error")
    warnings = tuple(finding for finding in schema_findings if finding.severity == "warning")
    if errors:
        health = _schema_health_report(schema_findings, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result)
    return warnings


def _schema_health_report(findings: tuple[HealthFinding, ...], effective_policy: dict[str, Any]) -> HealthReport:
    errors = tuple(finding for finding in findings if finding.severity == "error")
    warnings = tuple(finding for finding in findings if finding.severity == "warning")
    if errors:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib"} for finding in errors) else "FAIL"
    else:
        status = "CONCERNS" if warnings else "PASS"
    return HealthReport(
        status=status,
        errors=errors,
        warnings=warnings,
        effective_policy=effective_policy,
    )


def _compile_or_refuse(
    config_data: Mapping[str, Any],
    plugin_registry,
    effective_policy: dict[str, Any],
    run_dir: Path,
    run_id: str,
    *,
    config_path: Path,
):
    from vibeflow.compiler import GraphCompiler
    from vibeflow.graph_config import GraphConfigError, parse_graph_config

    try:
        graph = parse_graph_config(config_data, project_root=project_root_for_config(config_path))
        compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
    except (GraphConfigError, Exception) as exc:
        health = _compile_health_report(exc, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result) from exc
    return graph, compiled


def _compile_with_registry_or_refuse(
    graph: GraphConfig,
    registry: NodeRegistry,
    effective_policy: dict[str, Any],
    run_dir: Path,
    run_id: str,
):
    from vibeflow.compiler import GraphCompiler, GraphCompileError

    try:
        return GraphCompiler().compile(graph, registry=registry)
    except GraphCompileError as exc:
        health = _compile_health_report(exc, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result) from exc


def _compile_health_report(exc: Exception, effective_policy: dict[str, Any]) -> HealthReport:
    rule_id = getattr(exc, "rule_id", "GRAPH.COMPILE")
    return HealthReport(
        status="FAIL",
        errors=(
            HealthFinding(
                rule_id=str(rule_id),
                severity="error",
                object_type="pipeline",
                object_id="pipeline",
                failure_layer="topology",
                message=str(exc),
                suggested_fix_type="fix_config",
                details=dict(getattr(exc, "details", None) or {}),
            ),
        ),
        effective_policy=effective_policy,
    )


def _validate_run_health(
    graph: GraphConfig,
    registry: NodeRegistry,
    plugin_registry,
    policy_result,
    effective_policy: dict[str, Any],
    nodeset_imports: tuple[Mapping[str, Any], ...],
    resources: ConfigResources,
    preflight_warnings: tuple[HealthFinding, ...] = (),
) -> HealthReport:
    from vibeflow.health import validate_graph_health

    health = validate_graph_health(
        graph,
        registry=registry,
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=policy_result.effective_policy.to_purity_policy(),
        effective_policy=policy_result.effective_policy,
    )
    info = dict(health.info)
    info["nodeset_imports"] = [dict(item) for item in nodeset_imports]
    info["resources"] = resources.to_dict()
    warnings = (*preflight_warnings, *health.warnings)
    status = "CONCERNS" if health.status == "PASS" and warnings else health.status
    return replace(health, status=status, warnings=warnings, effective_policy=effective_policy, info=info)


def _write_preflight_artifacts(run_dir: Path, graph: GraphConfig, compiled, health: HealthReport, *, registry: NodeRegistry | None = None, resources: ConfigResources | None = None) -> None:
    from vibeflow.rendering.ascii_flowchart import export_ascii_flowchart
    from vibeflow.rendering.mermaid import compiled_graph_payload, export_mermaid
    from vibeflow.rendering.mermaid.render import EXPANDED_MERMAID_MAX_EDGES, EXPANDED_MERMAID_MAX_TEXT_SIZE, MermaidRenderError, render_mermaid_svg
    from vibeflow.rendering.mermaid.review_svg import render_review_columns_svg

    _write_json(run_dir / "health_report.json", health.to_dict())
    _write_json(run_dir / "compiled_graph.json", compiled_graph_payload(graph, compiled, resources=resources))
    (run_dir / "graph.txt").write_text(export_ascii_flowchart(graph, compiled=compiled, registry=registry, health_report=health), encoding="utf-8")
    mermaid_text = export_mermaid(graph, compiled=compiled, registry=registry, health_report=health, resources=resources)
    (run_dir / "graph.mmd").write_text(mermaid_text, encoding="utf-8")
    try:
        render_mermaid_svg(mermaid_text, run_dir / "graph.svg")
    except MermaidRenderError as exc:
        (run_dir / "graph.svg.error.txt").write_text(str(exc), encoding="utf-8")
    try:
        render_review_columns_svg(
            graph,
            compiled,
            run_dir / "graph.expanded.svg",
            registry=registry,
            resources=resources,
            expand_nodesets=True,
            max_text_size=EXPANDED_MERMAID_MAX_TEXT_SIZE,
            max_edges=EXPANDED_MERMAID_MAX_EDGES,
        )
    except MermaidRenderError as exc:
        (run_dir / "graph.expanded.svg.error.txt").write_text(str(exc), encoding="utf-8")


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
    resources: ConfigResources,
    runtime_options: object | None,
) -> None:
    from vibeflow.compiler import GraphCompiler
    from vibeflow.runtime.helpers import planned_items

    options = normalize_runtime_options(runtime_options)
    planned = planned_items(graph)
    if not planned:
        return
    if options.allow_planned_stub and all(item.get("behavior") == "python_stub" for item in planned):
        return
    planned_ids = [str(item.get("id", "")) for item in planned]
    non_stub = [str(item.get("id", "")) for item in planned if item.get("behavior") != "python_stub"]
    reason = "planned nodes/nodesets cannot run"
    if options.allow_planned_stub:
        reason = "only planned python_stub nodes/nodesets can run with allow_planned_stub"
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
    _write_preflight_artifacts(run_dir, graph, GraphCompiler().compile(graph, registry=registry), failed, registry=registry, resources=resources)
    _ensure_trace_files(run_dir)
    result = CheckedRunResult(run_id, run_dir, failed)
    raise CheckedRunError("run refused: planned nodes are not executable", result)


def _execute_runtime(
    graph: GraphConfig,
    registry: NodeRegistry,
    plugin_registry,
    initial: Mapping[str, Any] | None,
    run_dir: Path,
    runtime_options: object | None,
    resources: ConfigResources,
):
    from vibeflow.runtime import PipelineRuntime

    runtime = PipelineRuntime(
        graph,
        registry=registry,
        plugin_registry=plugin_registry,
        run_dir=run_dir,
        global_config=resources.global_config,
        runtime_options=runtime_options,
    )
    try:
        context = runtime.run(initial)
    finally:
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
