from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .config_loader import ConfigLoadError, load_config_document
from .config_resources import ConfigResources, load_config_resources
from .config_schema import collect_config_schema_findings
from .health_types import HealthFinding, HealthReport
from .plugin import load_plugins_from_config
from .policy import default_effective_policy, resolve_effective_policy
from .summaries import summarize_mapping

from .graph_config import GraphConfig
from .planned_behavior import project_root_for_config
from .registry import NodeRegistry
from .runtime_options import runtime_options as normalize_runtime_options


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
    _refuse_on_schema_findings(document.data, (*resource_findings, *policy_result.findings), effective_policy, run_dir, actual_run_id)
    graph, compiled = _compile_or_refuse(document.data, plugin_registry, effective_policy, run_dir, actual_run_id, config_path=path)
    health = _validate_run_health(graph, registry, plugin_registry, policy_result, effective_policy, document.nodeset_imports, resources)
    _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=registry, resources=resources, runtime_options=runtime_options)
    if health.status not in {"FAIL", "ERROR"}:
        compiled = _compile_with_registry_or_refuse(graph, registry, effective_policy, run_dir, actual_run_id)
    _write_preflight_artifacts(run_dir, graph, compiled, health, registry=registry, resources=resources)
    _refuse_on_health_failure(health, run_dir, actual_run_id)
    context = _execute_runtime(graph, registry, plugin_registry, initial, run_dir, runtime_options, resources)
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
    status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib"} for finding in findings) else "FAIL"
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
    *,
    config_path: Path,
):
    from .compiler import GraphCompiler
    from .graph_config import GraphConfigError, parse_graph_config

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
    from .compiler import GraphCompiler, GraphCompileError

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
) -> HealthReport:
    from .health import validate_graph_health

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
    return replace(health, effective_policy=effective_policy, info=info)


def _write_preflight_artifacts(run_dir: Path, graph: GraphConfig, compiled, health: HealthReport, *, registry: NodeRegistry | None = None, resources: ConfigResources | None = None) -> None:
    from .ascii_flowchart import export_ascii_flowchart
    from .mermaid import compiled_graph_payload, export_mermaid
    from .mermaid_render import EXPANDED_MERMAID_MAX_EDGES, EXPANDED_MERMAID_MAX_TEXT_SIZE, MermaidRenderError, render_mermaid_svg
    from .mermaid_review_svg import render_review_columns_svg

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
    from .compiler import GraphCompiler
    from .runtime_helpers import planned_items

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
    from .runtime import PipelineRuntime

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
    for name in ("runtime_trace.jsonl",):
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
