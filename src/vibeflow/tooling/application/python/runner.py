from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.core.flow import GraphConfig
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.registry import NodeRegistry, NodeRegistryError
from vibeflow.targets.python.runtime.options import (
    RuntimeOptions,
    runtime_options as normalize_runtime_options,
)
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from vibeflow.tooling.application.python.run_directory import (
    RunDirectoryExistsError,
    prepare_run_dir as _prepare_run_dir,
    validate_run_id,
)
from vibeflow.tooling.project.graph_config import project_root_for_config
from vibeflow.tooling.application.python.project.effective_policy import (
    default_effective_policy,
    resolve_effective_policy,
)
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_config_document,
)
from vibeflow.tooling.project.config_schema import (
    collect_config_schema_findings,
)
from vibeflow.tooling.application.python.project.resource_selection import (
    PythonResources,
    select_python_resources,
)
from vibeflow.tooling.application.python.run_observation import observed_checked_run
from vibeflow.tooling.application.python.execution import (
    CheckedRunError,
    CheckedRunResult,
    _checked_run_error_payload,
    _checked_runtime_binding,
    _ensure_trace_files,
    _execute_runtime,
    _is_data_envelope_payload,
    _iter_result_summary_items,
    _new_run_id,
    _summarize_result_item,
    _summarize_run_result,
    _summarize_shallow_value,
    _write_execution_report,
    _write_json,
    _write_refused_artifacts,
)


@observed_checked_run
def run_checked(
    config_path: str | Path,
    *,
    registry: NodeRegistry,
    initial: Mapping[str, Any] | None = None,
    policy_path: str | Path | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
    runtime_options: object | None = None,
    capabilities: Mapping[str, object] | None = None,
    delegate_cli: bool = False,
    _prepared_run_dir: Path | None = None,
    preview_root: str | Path | None = None,
    entry: str | None = None,
    signal=None,
) -> CheckedRunResult:
    path = Path(config_path)
    from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace
    if find_project_config(path) is not None:
        from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
        document = load_config_document(path)
        policy = resolve_effective_policy(document.data, config_path=path,
            explicit_policy_path=Path(policy_path) if policy_path else None)
        workspace = load_project_workspace(path)
        return run_workspace_checked(path, workspace=workspace,
            initial=initial, run_root=run_root, run_id=run_id,
            runtime_options=runtime_options, capabilities=capabilities,
            delegate_cli=delegate_cli, _policy_result=policy, _prepared_run_dir=_prepared_run_dir, preview_root=preview_root, entry=entry, signal=signal)
    actual_run_id = _new_run_id() if run_id is None else validate_run_id(run_id)
    effective_runtime_options = normalize_runtime_options(runtime_options)
    run_dir = _prepared_run_dir if _prepared_run_dir is not None else _prepare_run_dir(run_root, actual_run_id)
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))

    document = _load_document_or_refuse(path, run_dir, actual_run_id)
    plugin_registry = PluginRegistry()
    if document.data.get("plugins"):
        health = HealthReport(status="ERROR", errors=(HealthFinding(
            rule_id="PLUGIN.CONFIG.ROOT", severity="error", object_type="config", object_id=str(path),
            source_location={"path": str(path)}, failure_layer="plugin",
            message="custom plugins require an owning vibeflow_project.jsonc"),))
        _write_refused_artifacts(run_dir, health, include_effective_policy=True)
        raise CheckedRunError("run refused: plugin configuration has no project", CheckedRunResult(actual_run_id, run_dir, health))
    resources, resource_findings = select_python_resources(
        document.data,
        base_path=path.parent,
        registry=registry,
    )
    policy_result = resolve_effective_policy(
        document.data,
        config_path=path,
        explicit_policy_path=Path(policy_path) if policy_path else None,
    )
    from vibeflow.targets.python.project.check_session import python_check_scope
    with python_check_scope(registry):
        registry.configure_rule_defaults(purity_policy=policy_result.effective_policy.to_purity_policy())
        effective_policy = policy_result.effective_policy.to_dict()
        _write_json(run_dir / "effective_policy.json", effective_policy)
        preflight_warnings = _refuse_on_schema_findings(document.data, (*resource_findings, *policy_result.findings), effective_policy, run_dir, actual_run_id)
        graph, compiled = _compile_or_refuse(
            document.data,
            plugin_registry,
            effective_policy,
            run_dir,
            actual_run_id,
            config_path=path,
            registry=registry,
        )
        health = _validate_run_health(
            graph,
            registry,
            plugin_registry,
            policy_result,
            document.nodeset_imports,
            resources,
            runtime_options=effective_runtime_options,
            preflight_warnings=preflight_warnings,
            delegate_cli=delegate_cli,
            entry=entry,
        )
        if health.status in {"FAIL", "ERROR"}:
            _write_refused_artifacts(run_dir, health)
            _refuse_on_health_failure(health, run_dir, actual_run_id)
        from vibeflow.tooling.application.python.presentation.prepared import final_python_compilation, prepare_python_presentation
        compilation = final_python_compilation(graph, registry)
        graph, compiled = compilation.workflow.graph, compilation.compiled_graph
        presentation = prepare_python_presentation(graph, registry=registry, resources=resources, compilation=compilation)
        _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=registry, resources=resources,
                              runtime_options=effective_runtime_options, compiled=compiled, prepared=presentation)
        _write_preflight_artifacts(run_dir, graph, compiled, health, registry=registry, resources=resources, prepared=presentation)
        _refuse_on_health_failure(health, run_dir, actual_run_id)
        context = _execute_runtime(
            graph, registry, plugin_registry, initial, run_dir, effective_runtime_options, resources,
            capabilities=capabilities,
            delegate_cli=delegate_cli,
            health=health,
            entry=entry,
            signal=signal,
        )
        _write_json(run_dir / "output_summary.json", _summarize_run_result(context))
        from .execution import checked_result
        return checked_result(actual_run_id, run_dir, health, context, graph, entry)


def _load_document_or_refuse(path: Path, run_dir: Path, run_id: str):
    try:
        return load_config_document(path)
    except ConfigLoadError as exc:
        health = _load_error_report(exc)
        _write_refused_artifacts(run_dir, health, include_effective_policy=True)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError("run refused: config load failed", result) from exc


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
    registry: NodeRegistry,
):
    from vibeflow.core.flow import GraphConfigError
    from vibeflow.targets.python.project.compiler import GraphCompiler
    from vibeflow.tooling.project.graph_config import parse_graph_config

    try:
        project_root = project_root_for_config(config_path)
        graph = parse_graph_config(
            config_data,
            project_root=project_root,
            root_path=project_root,
            source_path=config_path,
        )
        compilation = GraphCompiler().compile_with_findings(
            graph,
            registry=registry,
            plugin_registry=plugin_registry,
        )
        graph = compilation.workflow.graph
        compiled = compilation.compiled_graph
    except (GraphConfigError, Exception) as exc:
        health = _compile_health_report(exc, effective_policy)
        _write_refused_artifacts(run_dir, health)
        result = CheckedRunResult(run_id, run_dir, health)
        raise CheckedRunError(f"run refused: health status {health.status}", result) from exc
    return graph, compiled


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
    nodeset_imports: tuple[Mapping[str, Any], ...],
    resources: PythonResources,
    runtime_options: RuntimeOptions,
    preflight_warnings: tuple[HealthFinding, ...] = (),
    delegate_cli: bool = False,
    entry: str | None = None,
) -> HealthReport:
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context

    purity_policy = policy_result.effective_policy.to_purity_policy()
    health = validate_graph_health(
        graph,
        registry=registry,
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=purity_policy,
        nodeset_max_depth=runtime_options.nodeset_max_depth,
        source_context=collect_workflow_source_context(registry, graph),
        rule_phase="run",
    )
    info = dict(health.info)
    info["nodeset_imports"] = [dict(item) for item in nodeset_imports]
    info["resources"] = resources.to_dict()
    info["production_ready"] = (
        bool(info.get("production_ready", True))
        and not resources.has_planned
    )
    warnings = (*preflight_warnings, *health.warnings)
    status = "CONCERNS" if health.status == "PASS" and warnings else health.status
    report = replace(
        health,
        status=status,
        warnings=warnings,
        effective_policy=policy_result.effective_policy.to_dict(),
        info=info,
    )
    if delegate_cli:
        from vibeflow.tooling.application.python.delegate_contract import (
            validate_delegate_cli_graph_contract,
        )

        from vibeflow.core.workflows.entries import project_entry
        from vibeflow.tooling.application.python.presentation.prepared import final_python_compilation
        compilation = final_python_compilation(graph, registry)
        selected, _ = project_entry(compilation.workflow.graph, compilation.compiled_graph, entry)
        report = validate_delegate_cli_graph_contract(selected, report)
    return report


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
) -> None:
    from vibeflow.targets.python.runtime.helpers import planned_items

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
    if prepared is None:
        from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
        prepared = prepare_python_presentation(graph, compiled=compiled, registry=registry, resources=resources)
    _write_preflight_artifacts(run_dir, graph, prepared.compiled, failed, registry=registry,
                              resources=resources, prepared=prepared)
    _ensure_trace_files(run_dir)
    result = CheckedRunResult(run_id, run_dir, failed)
    raise CheckedRunError("run refused: planned nodes are not executable", result)


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


__all__ = [
    "CheckedRunError",
    "CheckedRunResult",
    "RunDirectoryExistsError",
    "run_checked",
]
