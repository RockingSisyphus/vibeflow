from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.application.reports import (
    _workspace_error_report,
    _workspace_info,
    annotate_health_report,
    config_load_error_report,
    dedupe_findings,
    fail_report,
)
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.core.flow import GraphConfigError
from vibeflow.targets.python.project.compiler import GraphCompileError, GraphCompiler
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
from vibeflow.targets.python.project.plugin_loader import load_plugins_from_config
from vibeflow.targets.python.project.policy import default_effective_policy
from vibeflow.targets.python.runtime.options import RuntimeOptions
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from vibeflow.tooling.application.run_directory import validate_run_id
from vibeflow.tooling.application.runner import CheckedRunError, CheckedRunResult
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.tooling.project.python_quality import (
    collect_python_workflow_quality_facts,
)
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_workspace_config_document,
)
from vibeflow.tooling.project.config_schema import (
    collect_config_schema_findings,
)
from vibeflow.tooling.project.descriptor_loader import (
    DescriptorLoadError,
    load_project_descriptor_catalogs,
)
from vibeflow.tooling.project.resources import (
    ConfigResources,
    HostExtensionResource,
    config_base_lib_policy,
    load_config_resources,
    resolve_host_extension_resources,
)
from vibeflow.tooling.presentation.architecture_validation import (
    _validate_registered_architecture_document,
)
from vibeflow.tooling.project.core import (
    annotate_findings,
    build_workspace_environment,
    build_workspace_node_registry,
    load_workspace_config,
    load_workspace_resources,
    workspace_finding,
)
from vibeflow.tooling.project.policy import resolve_workspace_effective_policy
from vibeflow.tooling.project.project_options import (
    _workspace_runtime_options,
    project_javascript_options,
)
from vibeflow.tooling.project.quality import scan_workspace_code_quality
from vibeflow.tooling.project.types import (
    ArchitectureDocumentSpec,
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
    effective_runtime_options = _workspace_runtime_options(path, workspace=workspace)
    return _validate_prepared_workspace_graph(
        prepared,
        env=env,
        workspace=workspace,
        runtime_options=effective_runtime_options,
    )


def run_workspace_checked(
    config_path: str | Path,
    *,
    workspace: WorkspaceConfig,
    initial: Mapping[str, Any] | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
    runtime_options: object | None = None,
    delegate_cli: bool = False,
    _prepared_run_dir: Path | None = None,
) -> CheckedRunResult:
    from vibeflow.tooling.application.runner import (
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

    actual_run_id = _new_run_id() if run_id is None else validate_run_id(run_id)
    if _prepared_run_dir is None:
        run_dir = _prepare_run_dir(run_root, actual_run_id)
    else:
        run_dir = Path(_prepared_run_dir)
        expected_run_dir = (Path(run_root) if run_root is not None else Path("runs")) / actual_run_id
        if run_dir != expected_run_dir or not run_dir.is_dir():
            raise ValueError("_prepared_run_dir must be the already claimed directory for this checked run")
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))
    env = _environment_or_report(workspace)
    if isinstance(env, HealthReport):
        _write_refused_artifacts(run_dir, env, include_effective_policy=True)
        raise CheckedRunError("run refused: workspace load failed", CheckedRunResult(actual_run_id, run_dir, env))
    prepared = _prepare_workspace_graph(Path(config_path), workspace=workspace, env=env)
    if isinstance(prepared, HealthReport):
        _write_refused_artifacts(run_dir, prepared, include_effective_policy=True)
        raise CheckedRunError(f"run refused: health status {prepared.status}", CheckedRunResult(actual_run_id, run_dir, prepared))
    effective_runtime_options = _workspace_runtime_options(config_path, workspace=workspace, overrides=runtime_options)
    document, graph, compiled, resources, plugin_registry, effective_policy, warnings = prepared
    _write_json(run_dir / "effective_policy.json", effective_policy.to_dict())
    validation_kwargs = {"delegate_cli": True} if delegate_cli else {}
    health = _validate_prepared_workspace_graph(
        prepared,
        env=env,
        workspace=workspace,
        runtime_options=effective_runtime_options,
        **validation_kwargs,
    )
    _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=env.registry, resources=resources, runtime_options=effective_runtime_options)
    if health.status not in {"FAIL", "ERROR"}:
        compiled = _compile_with_registry_or_refuse(graph, env.registry, effective_policy.to_dict(), run_dir, actual_run_id)
    _write_preflight_artifacts(run_dir, graph, compiled, health, registry=env.registry, resources=resources)
    _refuse_on_health_failure(health, run_dir, actual_run_id)
    execute_kwargs = {"delegate_cli": True} if delegate_cli else {}
    context = _execute_runtime(
        graph,
        env.registry,
        plugin_registry,
        initial,
        run_dir,
        effective_runtime_options,
        resources,
        **execute_kwargs,
    )
    _write_json(run_dir / "output_summary.json", _summarize_run_result(context))
    return CheckedRunResult(actual_run_id, run_dir, health, context)


def load_workspace_graph_for_export(
    path: Path,
    *,
    workspace: WorkspaceConfig,
    validate_health: bool = False,
) -> tuple[object, object, object, ConfigResources, HealthReport | None]:
    env = _environment_or_report(workspace)
    if isinstance(env, HealthReport):
        return None, None, None, ConfigResources(), env
    prepared = _prepare_workspace_graph(path, workspace=workspace, env=env)
    if isinstance(prepared, HealthReport):
        return None, None, None, ConfigResources(), prepared
    _, graph, compiled, resources, _, _, _ = prepared
    if validate_health:
        health = _validate_prepared_workspace_graph(
            prepared,
            env=env,
            workspace=workspace,
            runtime_options=_workspace_runtime_options(path, workspace=workspace),
            check_architecture_document=False,
        )
        if health.status in {"FAIL", "ERROR"}:
            return None, None, None, ConfigResources(), health
    return graph, compiled, env.registry, resources, None


def _validate_prepared_workspace_graph(
    prepared,
    *,
    env: WorkspaceEnvironment,
    workspace: WorkspaceConfig,
    runtime_options: RuntimeOptions,
    check_architecture_document: bool = True,
    delegate_cli: bool = False,
) -> HealthReport:
    document, graph, compiled, resources, plugin_registry, effective_policy, warnings = prepared
    purity_policy = effective_policy.to_purity_policy()
    health = validate_graph_health(
        graph,
        registry=env.registry,
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=purity_policy,
        effective_policy=effective_policy,
        nodeset_max_depth=runtime_options.nodeset_max_depth,
        node_quality_facts=collect_python_workflow_quality_facts(
            graph,
            registry=env.registry,
            policy=purity_policy,
        ),
    )
    info = dict(health.info)
    info["nodeset_imports"] = [dict(item) for item in document.nodeset_imports]
    info["resources"] = resources.to_dict()
    info["effective_resources"] = resources.to_dict()
    info["available_resources"] = env.available_resources.to_dict()
    info["production_ready"] = (
        bool(info.get("production_ready", True))
        and not resources.has_planned
    )
    info["workspace"] = _workspace_info(workspace)
    info["explicit_edges"] = [edge.pair for edge in compiled.explicit_edges]
    info["data_edges"] = [edge.pair for edge in compiled.data_edges]
    info["effective_edges"] = [edge.pair for edge in compiled.effective_edges]
    report = replace(
        health,
        status="CONCERNS" if health.status == "PASS" and warnings else health.status,
        warnings=(*warnings, *health.warnings),
        info=info,
        effective_policy=effective_policy.to_dict(),
    )
    report = annotate_health_report(report, graph, workspace=workspace)
    if delegate_cli:
        from vibeflow.tooling.application.delegate_contract import (
            validate_delegate_cli_graph_contract,
        )

        report = validate_delegate_cli_graph_contract(graph, report)
    if report.status in {"FAIL", "ERROR"} or not check_architecture_document:
        return report
    return _validate_registered_architecture_document(
        report,
        document_path=document.path,
        graph=graph,
        compiled=compiled,
        registry=env.registry,
        resources=resources,
        workspace=workspace,
    )


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
    root_registries = env.resource_registries.get(root.id)
    plugin_registry, plugin_findings = load_plugins_from_config(
        document.data,
        base_path=root.path,
        root_id=root.id,
        root_path=str(root.path),
        source_path=str(config_path),
        plugin_resource_registry=root_registries.plugins if root_registries and root_registries.has_plugin_registry else None,
    )
    preflight_findings.extend(annotate_findings(plugin_findings, root=root, source_path=config_path))
    resources, resource_findings = load_config_resources(
        document.data,
        base_path=root.path,
        plugin_registry=plugin_registry,
        base_lib_registry=root_registries.base_libs if root_registries and root_registries.has_base_lib_registry else None,
        plugin_resource_registry=root_registries.plugins if root_registries and root_registries.has_plugin_registry else None,
        base_lib_paths=root_registries.base_lib_paths if root_registries else (str(root.path),),
    )
    if "host_extensions" not in document.data:
        javascript = project_javascript_options(
            root.project_config,
            root.config_path,
        )
        legacy_extension_ids = tuple(
            javascript.get("host_extensions", ())
        )
        if legacy_extension_ids:
            resources = replace(
                resources,
                host_extensions=tuple(
                    HostExtensionResource(
                        id=str(extension_id),
                        root_id=root.id,
                        root_path=str(root.path),
                        source_path=str(root.config_path),
                    )
                    for extension_id in legacy_extension_ids
                ),
            )
            preflight_findings.append(
                workspace_finding(
                    "CONFIG.SMELL.LEGACY_HOST_EXTENSION_SELECTION",
                    (
                        "javascript.host_extensions is deprecated; select "
                        "host extensions in the workflow-level "
                        "host_extensions list"
                    ),
                    root=root,
                    source_path=root.config_path,
                    object_id="javascript.host_extensions",
                    failure_layer="host_extension",
                    severity="warning",
                )
            )
    if resources.host_extensions:
        try:
            descriptor_catalogs = load_project_descriptor_catalogs(
                root.path,
                project_config=root.config_path,
            )
        except DescriptorLoadError as exc:
            preflight_findings.append(
                workspace_finding(
                    exc.code,
                    exc.message,
                    root=root,
                    source_path=Path(exc.path or root.config_path),
                    object_id="descriptors",
                    failure_layer="descriptor",
                )
            )
        else:
            resolved_extensions, extension_findings = (
                resolve_host_extension_resources(
                    resources.host_extensions,
                    catalog=descriptor_catalogs.host_extensions,
                )
            )
            resources = replace(
                resources,
                host_extensions=resolved_extensions,
            )
            resource_findings = (*resource_findings, *extension_findings)
    resources = replace(
        resources,
        base_libs=_with_effective_resource_source(resources.base_libs, root=root, source_path=config_path),
        plugins=_with_effective_resource_source(resources.plugins, root=root, source_path=config_path),
        host_extensions=_with_effective_resource_source(
            resources.host_extensions,
            root=root,
            source_path=config_path,
        ),
    )
    preflight_findings.extend(annotate_findings(resource_findings, root=root, source_path=config_path))
    policy_result = resolve_workspace_effective_policy(
        workspace.policy,
        workspace_path=workspace.path,
        base_lib_policies=(config_base_lib_policy(resources.to_dict(), base_path=root.path),),
        plugin_registry=plugin_registry,
    )
    preflight_findings.extend(annotate_findings(policy_result.findings, root=root, source_path=config_path))
    effective_policy = policy_result.effective_policy
    schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *preflight_findings))
    errors = tuple(finding for finding in schema_findings if finding.severity == "error")
    warnings = tuple(finding for finding in schema_findings if finding.severity == "warning")
    if errors:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib", "workspace"} for finding in errors) else "FAIL"
        return HealthReport(status=status, errors=errors, warnings=warnings, effective_policy=effective_policy.to_dict())
    try:
        graph = parse_graph_config(document.data, project_root=root.path, root_id=root.id, root_path=root.path, source_path=config_path)
        compiled = GraphCompiler().compile(graph, registry=env.registry, plugin_registry=plugin_registry)
    except GraphConfigError as exc:
        return fail_report("CONFIG.SCHEMA.PARSE", str(exc), "config", str(config_path), "schema", effective_policy=effective_policy.to_dict())
    except GraphCompileError as exc:
        return fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology", effective_policy=effective_policy.to_dict())
    return document, graph, compiled, resources, plugin_registry, effective_policy, warnings


def _with_effective_resource_source(resources, *, root: WorkspaceRoot, source_path: Path) -> tuple[object, ...]:
    return tuple(
        replace(
            resource,
            root_id=getattr(resource, "root_id", "") or root.id,
            root_path=getattr(resource, "root_path", "") or str(root.path),
            source_path=getattr(resource, "source_path", "") or str(source_path),
        )
        for resource in resources
    )


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
        findings.append(
            workspace_finding(
                "WORKSPACE.CONFIG.FIELD_FORBIDDEN",
                f"workspace mode does not allow config field '{field}'; move it to {WORKSPACE_CONFIG_NAME}",
                root=root,
                source_path=source_path,
                object_id=field,
                failure_layer="schema",
            )
        )
    return tuple(findings)


__all__ = [
    "ArchitectureDocumentSpec",
    "PROJECT_CONFIG_NAME",
    "WORKSPACE_CONFIG_NAME",
    "WORKSPACE_FORBIDDEN_CONFIG_FIELDS",
    "WorkspaceConfig",
    "WorkspaceConfigError",
    "WorkspaceEnvironment",
    "WorkspaceRoot",
    "annotate_health_report",
    "build_workspace_environment",
    "build_workspace_node_registry",
    "load_workspace_config",
    "load_workspace_graph_for_export",
    "load_workspace_resources",
    "run_workspace_checked",
    "scan_workspace_code_quality",
    "validate_workspace_config_path",
]
