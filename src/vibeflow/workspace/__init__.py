from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.cli.reports import config_load_error_report, dedupe_findings, fail_report
from vibeflow.compiler import GraphCompiler, GraphCompileError
from vibeflow.config.loader import ConfigLoadError, load_workspace_config_document
from vibeflow.config.resources import ConfigResources, load_config_resources
from vibeflow.config.schema import collect_config_schema_findings
from vibeflow.graph_config import GraphConfigError, parse_graph_config
from vibeflow.health.types import HealthFinding, HealthReport
from vibeflow.policy import EffectivePolicy, default_effective_policy
from vibeflow.runner import CheckedRunError, CheckedRunResult
from vibeflow.runtime.summaries import summarize_mapping
from vibeflow.workspace.core import (
    annotate_findings,
    build_workspace_environment,
    build_workspace_node_registry,
    load_workspace_config,
    load_workspace_resources,
    workspace_finding,
)
from vibeflow.workspace.quality import scan_workspace_code_quality
from vibeflow.workspace.types import (
    PROJECT_CONFIG_NAME,
    WORKSPACE_CONFIG_NAME,
    WORKSPACE_FORBIDDEN_CONFIG_FIELDS,
    WorkspaceConfig,
    WorkspaceConfigError,
    WorkspaceEnvironment,
    WorkspaceRoot,
)


def validate_workspace_config_path(path: Path, *, workspace: WorkspaceConfig) -> HealthReport:
    env = _environment_or_report(workspace)
    if isinstance(env, HealthReport):
        return env
    prepared = _prepare_workspace_graph(path, workspace=workspace, env=env)
    if isinstance(prepared, HealthReport):
        return prepared
    document, graph, compiled, resources, warnings = prepared
    return _validate_prepared_workspace_graph(document, graph, compiled, resources, warnings, env=env, workspace=workspace)


def run_workspace_checked(
    config_path: str | Path,
    *,
    workspace: WorkspaceConfig,
    initial: Mapping[str, Any] | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
    runtime_options: object | None = None,
) -> CheckedRunResult:
    from vibeflow.runner import (
        _compile_with_registry_or_refuse,
        _execute_runtime,
        _new_run_id,
        _prepare_run_dir,
        _refuse_on_health_failure,
        _refuse_on_planned_run,
        _summarize_run_result,
        _write_json,
        _write_preflight_artifacts,
        _write_refused_artifacts,
    )

    actual_run_id = run_id or _new_run_id()
    run_dir = _prepare_run_dir(run_root, actual_run_id)
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))
    env = _environment_or_report(workspace)
    if isinstance(env, HealthReport):
        _write_refused_artifacts(run_dir, env, include_effective_policy=True)
        raise CheckedRunError("run refused: workspace load failed", CheckedRunResult(actual_run_id, run_dir, env))
    prepared = _prepare_workspace_graph(Path(config_path), workspace=workspace, env=env)
    if isinstance(prepared, HealthReport):
        _write_refused_artifacts(run_dir, prepared, include_effective_policy=True)
        raise CheckedRunError(f"run refused: health status {prepared.status}", CheckedRunResult(actual_run_id, run_dir, prepared))
    document, graph, compiled, resources, warnings = prepared
    _write_json(run_dir / "effective_policy.json", env.effective_policy.to_dict())
    health = _validate_prepared_workspace_graph(document, graph, compiled, resources, warnings, env=env, workspace=workspace)
    _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=env.registry, resources=resources, runtime_options=runtime_options)
    if health.status not in {"FAIL", "ERROR"}:
        compiled = _compile_with_registry_or_refuse(graph, env.registry, env.effective_policy.to_dict(), run_dir, actual_run_id)
    _write_preflight_artifacts(run_dir, graph, compiled, health, registry=env.registry, resources=resources)
    _refuse_on_health_failure(health, run_dir, actual_run_id)
    context = _execute_runtime(graph, env.registry, env.plugin_registry, initial, run_dir, runtime_options, resources)
    _write_json(run_dir / "output_summary.json", _summarize_run_result(context))
    return CheckedRunResult(actual_run_id, run_dir, health, context)


def load_workspace_graph_for_export(
    path: Path,
    *,
    workspace: WorkspaceConfig,
) -> tuple[object, object, object, ConfigResources, HealthReport | None]:
    env = _environment_or_report(workspace)
    if isinstance(env, HealthReport):
        return None, None, None, ConfigResources(), env
    prepared = _prepare_workspace_graph(path, workspace=workspace, env=env)
    if isinstance(prepared, HealthReport):
        return None, None, None, ConfigResources(), prepared
    _, graph, compiled, resources, _ = prepared
    return graph, compiled, env.registry, resources, None


def annotate_health_report(report: HealthReport, graph, *, workspace: WorkspaceConfig) -> HealthReport:
    return replace(
        report,
        errors=tuple(_annotate_graph_finding(finding, graph, workspace=workspace) for finding in report.errors),
        warnings=tuple(_annotate_graph_finding(finding, graph, workspace=workspace) for finding in report.warnings),
        skipped=tuple(_annotate_graph_finding(finding, graph, workspace=workspace) for finding in report.skipped),
    )


def _validate_prepared_workspace_graph(
    document,
    graph,
    compiled,
    resources: ConfigResources,
    warnings: tuple[HealthFinding, ...],
    *,
    env: WorkspaceEnvironment,
    workspace: WorkspaceConfig,
) -> HealthReport:
    from vibeflow.health import validate_graph_health

    health = validate_graph_health(
        graph,
        registry=env.registry,
        plugin_registry=env.plugin_registry,
        global_config=resources.global_config,
        purity_policy=env.effective_policy.to_purity_policy(),
        effective_policy=env.effective_policy,
    )
    info = dict(health.info)
    info["nodeset_imports"] = [dict(item) for item in document.nodeset_imports]
    info["resources"] = resources.to_dict()
    info["workspace"] = _workspace_info(workspace)
    info["explicit_edges"] = [edge.pair for edge in compiled.explicit_edges]
    info["data_edges"] = [edge.pair for edge in compiled.data_edges]
    info["effective_edges"] = [edge.pair for edge in compiled.effective_edges]
    report = replace(
        health,
        status="CONCERNS" if health.status == "PASS" and warnings else health.status,
        warnings=(*warnings, *health.warnings),
        info=info,
        effective_policy=env.effective_policy.to_dict(),
    )
    return annotate_health_report(report, graph, workspace=workspace)


def _prepare_workspace_graph(path: Path, *, workspace: WorkspaceConfig, env: WorkspaceEnvironment):
    config_path = path.resolve()
    root = workspace.root_for_path(config_path)
    if root is None:
        return _workspace_error_report("WORKSPACE.CONFIG.OUTSIDE_ROOT", f"config is not under any workspace root: {config_path}", config_path, env.effective_policy)
    try:
        document = load_workspace_config_document(config_path, workspace=workspace)
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(config_path))
    preflight_findings = [*_forbidden_config_findings(document.data, root=root, source_path=config_path), *annotate_findings(env.findings, root=root, source_path=config_path)]
    config_resources, global_findings = load_config_resources(
        {"global_config": document.data.get("global_config", {})},
        base_path=config_path.parent,
        plugin_registry=env.plugin_registry,
    )
    preflight_findings.extend(annotate_findings(global_findings, root=root, source_path=config_path))
    resources = replace(env.resources, global_config=config_resources.global_config)
    schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *preflight_findings))
    errors = tuple(finding for finding in schema_findings if finding.severity == "error")
    warnings = tuple(finding for finding in schema_findings if finding.severity == "warning")
    if errors:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib", "workspace"} for finding in errors) else "FAIL"
        return HealthReport(status=status, errors=errors, warnings=warnings, effective_policy=env.effective_policy.to_dict())
    try:
        graph = parse_graph_config(document.data, project_root=root.path, root_id=root.id, root_path=root.path, source_path=config_path)
        compiled = GraphCompiler().compile(graph, registry=env.registry, plugin_registry=env.plugin_registry)
    except GraphConfigError as exc:
        return fail_report("CONFIG.SCHEMA.PARSE", str(exc), "config", str(config_path), "schema", effective_policy=env.effective_policy.to_dict())
    except GraphCompileError as exc:
        return fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology", effective_policy=env.effective_policy.to_dict())
    return document, graph, compiled, resources, warnings


def _environment_or_report(workspace: WorkspaceConfig) -> WorkspaceEnvironment | HealthReport:
    try:
        return build_workspace_environment(workspace)
    except WorkspaceConfigError as exc:
        path = Path(str(exc.source_location.get("path", workspace.path)))
        return _workspace_error_report(exc.rule_id, exc.message, path, default_effective_policy())
    except Exception as exc:
        return _workspace_error_report("WORKSPACE.LOAD", str(exc), workspace.path, default_effective_policy())


def _forbidden_config_findings(config: Mapping[str, Any], *, root: WorkspaceRoot, source_path: Path) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    for field in sorted(WORKSPACE_FORBIDDEN_CONFIG_FIELDS & set(config)):
        target = WORKSPACE_CONFIG_NAME if field == "policy" else PROJECT_CONFIG_NAME
        findings.append(
            workspace_finding(
                "WORKSPACE.CONFIG.FIELD_FORBIDDEN",
                f"workspace mode does not allow config field '{field}'; move it to {target}",
                root=root,
                source_path=source_path,
                object_id=field,
                failure_layer="schema",
            )
        )
    return tuple(findings)


def _workspace_error_report(rule_id: str, message: str, path: Path, effective_policy: EffectivePolicy) -> HealthReport:
    return HealthReport(
        status="ERROR",
        errors=(
            HealthFinding(
                rule_id=rule_id,
                severity="error",
                object_type="workspace",
                object_id=str(path),
                source_location={"path": str(path)},
                failure_layer="workspace",
                message=message,
                suggested_fix_type="fix_config",
            ),
        ),
        effective_policy=effective_policy.to_dict(),
    )


def _workspace_info(workspace: WorkspaceConfig) -> dict[str, object]:
    return {
        "path": str(workspace.path),
        "roots": [
            {"id": root.id, "path": str(root.path), "config": str(root.config_path), "quality_enabled": root.quality_enabled}
            for root in workspace.roots
        ],
    }


def _annotate_graph_finding(finding: HealthFinding, graph, *, workspace: WorkspaceConfig) -> HealthFinding:
    if finding.root_id:
        return finding
    source = _source_for_finding(finding, graph, workspace=workspace)
    if source is None:
        return finding
    return replace(finding, root_id=source["root_id"], root_path=source["root_path"], source_path=source["source_path"])


def _source_for_finding(finding: HealthFinding, graph, *, workspace: WorkspaceConfig) -> dict[str, str] | None:
    location_path = str(finding.source_location.get("path", "")).strip()
    if location_path:
        root = workspace.root_for_path(location_path)
        if root is not None:
            return {"root_id": root.id, "root_path": str(root.path), "source_path": location_path}
    if finding.object_type == "nodeset":
        nodeset = graph.nodesets.get(finding.object_id)
        return _source_payload(nodeset.root_id, nodeset.root_path, nodeset.source_path) if nodeset is not None else None
    if finding.object_type == "node":
        return _node_source_for_finding(finding, graph)
    root = workspace.root_for_path(getattr(graph, "source_path", ""))
    if root is not None:
        return {"root_id": root.id, "root_path": str(root.path), "source_path": str(getattr(graph, "source_path", ""))}
    return None


def _node_source_for_finding(finding: HealthFinding, graph) -> dict[str, str] | None:
    owner_graph = _graph_for_owner(graph, str(finding.details.get("owner", "")))
    if owner_graph is not None:
        return _source_payload(owner_graph.root_id, owner_graph.root_path, owner_graph.source_path)
    if any(node.id == finding.object_id for node in graph.nodes):
        return _source_payload(graph.root_id, graph.root_path, graph.source_path)
    for nodeset in graph.nodesets.values():
        if any(node.id == finding.object_id for node in nodeset.graph.nodes):
            return _source_payload(nodeset.graph.root_id, nodeset.graph.root_path, nodeset.graph.source_path)
    return None


def _graph_for_owner(graph, owner: str):
    if not owner or owner == "pipeline":
        return graph
    if owner.startswith("nodeset:"):
        nodeset = graph.nodesets.get(owner[len("nodeset:") :])
        return nodeset.graph if nodeset is not None else None
    return None


def _source_payload(root_id: str, root_path: str, source_path: str) -> dict[str, str] | None:
    if not root_id and not root_path and not source_path:
        return None
    return {"root_id": root_id, "root_path": root_path, "source_path": source_path}
