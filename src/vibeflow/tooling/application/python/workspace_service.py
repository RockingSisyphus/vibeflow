from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.application.python.reports import (
    _workspace_error_report,
    _workspace_info,
    annotate_health_report,
    config_load_error_report,
    dedupe_findings,
    fail_report,
)
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.core.flow import GraphConfigError
from vibeflow.tooling.application.python.project.prepared_graph import PreparedWorkspaceGraph
from vibeflow.targets.python.project.compiler import GraphCompileError, GraphCompiler
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
from vibeflow.targets.python.project.policy import default_effective_policy
from vibeflow.targets.python.runtime.options import RuntimeOptions
from vibeflow.targets.python.sdk.loading import source_paths
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from vibeflow.tooling.application.python.run_directory import validate_run_id
from vibeflow.tooling.application.python.execution import (CheckedRunError, CheckedRunResult)
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_workspace_config_document,
)
from vibeflow.tooling.project.config_schema import (
    ConfigSchemaError, collect_config_schema_findings,
)
from vibeflow.tooling.project.resources import ResourcePreparationError
from vibeflow.tooling.application.python.project.resource_selection import PythonResources, select_python_resources

from vibeflow.tooling.application.python.presentation.architecture_validation import (
    _validate_registered_architecture_document,
)
from vibeflow.tooling.application.python.project.core import (
    annotate_findings,
    build_workspace_environment,
    build_workspace_node_registry,
    load_workspace_config,
    load_workspace_resources,
    workspace_finding,
)
from vibeflow.tooling.application.python.project.project_options import (
    _workspace_runtime_options,
)
from vibeflow.tooling.application.python.project.types import WorkspaceEnvironment
from vibeflow.tooling.project.architecture_types import ArchitectureDocumentSpec, WorkspaceConfigError
from vibeflow.tooling.project.workspace_model import (
    PROJECT_CONFIG_NAME,
    WORKSPACE_CONFIG_NAME,
    WORKSPACE_FORBIDDEN_CONFIG_FIELDS,
    WorkspaceConfig,
    WorkspaceRoot,
)
from vibeflow.targets.python.project.check_session import python_check_scope as _python_check_scope
from vibeflow.tooling.application.python.presentation.prepared import (
    final_python_compilation as _final_compilation,
)


def validate_workspace_config_path(path: Path, *, workspace: WorkspaceConfig, environment=None) -> HealthReport:
    env = environment if environment is not None else _environment_or_report(workspace, path)
    if isinstance(env, HealthReport):
        return env
    with _python_check_scope(env.registry):
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


from vibeflow.tooling.application.python.run_observation import observed_checked_run


@observed_checked_run
def run_workspace_checked(
    config_path: str | Path,
    *,
    workspace: WorkspaceConfig,
    initial: Mapping[str, Any] | None = None,
    run_root: str | Path | None = None,
    run_id: str | None = None,
    runtime_options: object | None = None,
    delegate_cli: bool = False,
    capabilities: Mapping[str, object] | None = None,
    _prepared_run_dir: Path | None = None,
    preview_root: str | Path | None = None,
    entry: str | None = None,
    signal=None,
) -> CheckedRunResult:
    from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
    from vibeflow.tooling.application.python.execution import (_execute_runtime, _new_run_id, _summarize_run_result, _write_json, _write_refused_artifacts)
    from vibeflow.tooling.application.python.preflight import (_refuse_on_health_failure, _refuse_on_planned_run, _write_preflight_artifacts)

    actual_run_id = _new_run_id() if run_id is None else validate_run_id(run_id)
    if _prepared_run_dir is None:
        run_dir = _prepare_run_dir(run_root, actual_run_id)
    else:
        run_dir = Path(_prepared_run_dir)
        expected_run_dir = (Path(run_root) if run_root is not None else Path("runs")) / actual_run_id
        if run_dir != expected_run_dir or not run_dir.is_dir():
            raise ValueError("_prepared_run_dir must be the already claimed directory for this checked run")
    _write_json(run_dir / "input_summary.json", summarize_mapping(dict(initial or {})))
    env = _environment_or_report(workspace, Path(config_path))
    if isinstance(env, HealthReport):
        _write_refused_artifacts(run_dir, env, include_effective_policy=True)
        raise CheckedRunError("run refused: workspace load failed", CheckedRunResult(actual_run_id, run_dir, env))
    with _python_check_scope(env.registry):
        prepared = _prepare_workspace_graph(Path(config_path), workspace=workspace, env=env)
        if isinstance(prepared, HealthReport):
            _write_refused_artifacts(run_dir, prepared, include_effective_policy=True)
            raise CheckedRunError(f"run refused: health status {prepared.status}", CheckedRunResult(actual_run_id, run_dir, prepared))
        effective_runtime_options = _workspace_runtime_options(config_path, workspace=workspace, overrides=runtime_options)
        graph, resources = prepared.graph, prepared.resources
        plugin_registry, effective_policy = prepared.plugin_registry, prepared.effective_policy
        _write_json(run_dir / "effective_policy.json", effective_policy.to_dict())
        from vibeflow.core.workflows.entries import choose_entry
        selected_entry = choose_entry(graph.entries, graph.default_entry, entry)
        validation_kwargs = {"delegate_cli": True} if delegate_cli else {}
        if selected_entry is not None:
            validation_kwargs["entry"] = selected_entry
        health = _validate_prepared_workspace_graph(
            prepared,
            env=env,
            workspace=workspace,
            runtime_options=effective_runtime_options,
            rule_phase="run",
            **validation_kwargs,
        )
        if health.status in {"FAIL", "ERROR"}:
            _write_refused_artifacts(run_dir, health)
            _refuse_on_health_failure(health, run_dir, actual_run_id)
        compilation = _final_compilation(graph, env.registry)
        graph, compiled = compilation.workflow.graph, compilation.compiled_graph
        from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
        presentation = prepare_python_presentation(graph, registry=env.registry, resources=resources, compilation=compilation)
        _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=env.registry, resources=resources,
                              runtime_options=effective_runtime_options, compiled=compiled, prepared=presentation, entry=entry)
        _write_preflight_artifacts(run_dir, graph, compiled, health, registry=env.registry, resources=resources, prepared=presentation)
        _refuse_on_health_failure(health, run_dir, actual_run_id)
        execute_kwargs = {"delegate_cli": True} if delegate_cli else {}
        if capabilities is not None:
            execute_kwargs["capabilities"] = capabilities
        from vibeflow.tooling.application.python.project.lifecycle import lifecycle_registry, checked_runtime_plugins
        from vibeflow.targets.python.project.plugins import plugin_lifetime
        runtime_registry = checked_runtime_plugins(
            lambda: lifecycle_registry(env.registry, workflow_id=str(config_path), config_path=config_path,
                                       plugin_types=("runtime",)),
            config_path=config_path, effective_policy=effective_policy, run_dir=run_dir)
        health = replace(health, info={**health.info, "plugins": {"plugins": [
            *plugin_registry.to_dict()["plugins"], *runtime_registry.to_dict()["plugins"]]}})
        _write_json(run_dir / "health_report.json", health.to_dict())
        with source_paths(env.registry.source_roots), plugin_lifetime(runtime_registry):
            context = _execute_runtime(
            graph,
            env.registry,
            runtime_registry,
            initial,
            run_dir,
            effective_runtime_options,
            resources,
            health=health,
            entry=entry,
            signal=signal,
            **execute_kwargs,
            )
        _write_json(run_dir / "output_summary.json", _summarize_run_result(context))
        from .execution import checked_result
        return checked_result(actual_run_id, run_dir, health, context, graph, entry)


def load_workspace_graph_for_export(
    path: Path,
    *,
    workspace: WorkspaceConfig,
    validate_health: bool = False,
    _include_presentation: bool = False,
    preparation=None, governance=None,
) -> tuple[object, object, object, PythonResources, HealthReport | None]:
    result = _load_workspace_graph_for_presentation(path, workspace=workspace, validate_health=validate_health, preparation=preparation, governance=governance)
    return result if _include_presentation else result[:5]


def _load_workspace_graph_for_presentation(path, *, workspace, validate_health, preparation=None, governance=None):
    env = _environment_or_report(workspace, path, preparation=preparation, governance=governance)
    if isinstance(env, HealthReport):
        return None, None, None, PythonResources(), env, env, None
    with _python_check_scope(env.registry):
        prepared = _prepare_workspace_graph(path, workspace=workspace, env=env)
        if isinstance(prepared, HealthReport):
            return None, None, None, PythonResources(), prepared, prepared, None
        graph, compiled, resources = prepared.graph, prepared.compiled, prepared.resources
        health = _validate_prepared_workspace_graph(prepared, env=env, workspace=workspace,
            runtime_options=_workspace_runtime_options(path, workspace=workspace), check_architecture_document=False)
        if validate_health and health.status in {"FAIL", "ERROR"}:
            return None, None, None, PythonResources(), health, health, None
        presentation = None
        if health.status not in {"FAIL", "ERROR"}:
            from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation

            compilation = _final_compilation(graph, env.registry)
            presentation = prepare_python_presentation(graph, registry=env.registry,
                resources=resources, compilation=compilation)
            graph, compiled = presentation.graph, presentation.compiled
        return graph, compiled, env.registry, resources, None, health, presentation


def _validate_prepared_workspace_graph(
    prepared,
    *,
    env: WorkspaceEnvironment,
    workspace: WorkspaceConfig,
    runtime_options: RuntimeOptions,
    check_architecture_document: bool = True,
    delegate_cli: bool = False,
    entry: str | None = None,
    rule_phase: str = "static",
) -> HealthReport:
    document, graph, compiled = prepared.document, prepared.graph, prepared.compiled
    resources, plugin_registry = prepared.resources, prepared.plugin_registry
    effective_policy, warnings = prepared.effective_policy, prepared.warnings
    purity_policy = effective_policy.to_purity_policy()
    health = validate_graph_health(
        graph,
        registry=env.registry,
        plugin_registry=plugin_registry,
        global_config=resources.global_config,
        purity_policy=purity_policy,
        source_context=collect_workflow_source_context(env.registry, graph),
        rule_phase=rule_phase,
        compilation=prepared.compilation,
        **({"entry": entry} if entry is not None and rule_phase == "run" else {}),
    )
    if health.status not in {"FAIL", "ERROR"}:
        compilation = _final_compilation(graph, env.registry)
        graph, compiled = compilation.workflow.graph, compilation.compiled_graph
        prepared.graph, prepared.compilation = graph, compilation
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
    env.registry.review_findings = (*report.errors, *report.warnings)
    if delegate_cli:
        from vibeflow.tooling.application.python.delegate_contract import (
            validate_delegate_cli_graph_contract,
        )

        from vibeflow.core.workflows.entries import project_entry
        selected, _ = project_entry(graph, compiled, entry)
        report = validate_delegate_cli_graph_contract(selected, report)
    prepared.health = report
    if report.status in {"FAIL", "ERROR"} or not check_architecture_document:
        return report
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
    presentation = prepare_python_presentation(graph, registry=env.registry, resources=resources,
        compilation=compilation)
    prepared.health = _validate_registered_architecture_document(
        report,
        document_path=document.path,
        graph=graph,
        compiled=compiled,
        registry=env.registry,
        resources=resources,
        workspace=workspace,
        prepared=presentation,
    )
    return prepared.health


def _prepare_workspace_graph(path: Path, *, workspace: WorkspaceConfig, env: WorkspaceEnvironment):
    config_path = path.resolve()
    root = workspace.root_for_path(config_path)
    if root is None:
        return _workspace_error_report("WORKSPACE.CONFIG.OUTSIDE_ROOT", f"config is not under any workspace root: {config_path}", config_path, env.effective_policy)
    if root.project_target != "python":
        return _workspace_error_report(
            "CLI.PROJECT_TARGET.MISMATCH",
            (
                "Python Application requires project_target='python'; "
                f"root {root.id!r} declares {root.project_target!r}"
            ),
            config_path,
            env.effective_policy,
        )
    try:
        document = env.registry.prepared_resources.document
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(config_path))
    forbidden = _forbidden_config_findings(document.data, root=root, source_path=config_path) if workspace.path.name == WORKSPACE_CONFIG_NAME else ()
    preflight_findings = [*forbidden, *annotate_findings(env.findings, root=root, source_path=config_path)]
    source_policy = env.effective_policy
    env.registry.configure_rule_defaults(purity_policy=source_policy.to_purity_policy())
    from vibeflow.tooling.application.python.project.lifecycle import lifecycle_registry
    from vibeflow.targets.python.project.resource_rules import review_python_resource
    descriptor_catalogs = env.registry.rule_catalogs[0]
    # Libraries are reviewed when reached by the Node source closure. Lifecycle
    # factories are the resources about to bind at this stage.
    for resource in descriptor_catalogs.plugins:
        owner = env.registry.resource_roots.get(("plugins" if resource.to_dict()["kind"] == "plugin" else "base_libs", resource.id))
        if owner is not None:
            for phase in ("import", "static"):
                preflight_findings.extend(review_python_resource(resource, base_path=owner.path, registry=env.registry, phase=phase))
    from vibeflow.core.descriptors.source_bundle import declaration_descriptor
    for record in descriptor_catalogs.plugin_records:
        if record.get("loaded") and record.get("declaration"):
            resource = declaration_descriptor(record["declaration"])
            from vibeflow.tooling.project.resources.ownership import ResourceScope
            owner = (ResourceScope("project", workspace.root, "python", {}) if record.get("scope") == "project"
                     else workspace.root_by_id(record["root"]))
            for phase in ("import", "static"):
                preflight_findings.extend(review_python_resource(resource, base_path=owner.path, registry=env.registry, phase=phase))
    if any(item.severity == "error" for item in preflight_findings):
        return HealthReport(status="FAIL", errors=tuple(item for item in preflight_findings if item.severity == "error"),
                            warnings=tuple(item for item in preflight_findings if item.severity != "error"),
                            effective_policy=env.effective_policy.to_dict())
    try:
        plugin_registry = lifecycle_registry(env.registry, workflow_id=str(config_path), config_path=config_path,
                                             plugin_types=("compiler",))
    except Exception as exc:
        return _workspace_error_report("PLUGIN.FACTORY.LOAD", str(exc), config_path, env.effective_policy)
    from vibeflow.targets.python.project.plugins import plugin_lifetime
    with source_paths(env.registry.source_roots), plugin_lifetime(plugin_registry, plugin_type="compiler"):
        resources, resource_findings = select_python_resources(document.data, registry=env.registry, base_path=root.path)
        resources = replace(
            resources,
            base_libs=_with_effective_resource_source(resources.base_libs, root=root, source_path=config_path),
            plugins=_with_effective_resource_source(resources.plugins, root=root, source_path=config_path),

        )
        preflight_findings.extend(annotate_findings(resource_findings, root=root, source_path=config_path))
        effective_policy = env.effective_policy
        env.registry.configure_rule_defaults(purity_policy=effective_policy.to_purity_policy())
        schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *preflight_findings))
        errors = tuple(finding for finding in schema_findings if finding.severity == "error")
        warnings = tuple(finding for finding in schema_findings if finding.severity == "warning")
        if errors:
            status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib", "workspace"} for finding in errors) else "FAIL"
            return HealthReport(status=status, errors=errors, warnings=warnings, effective_policy=effective_policy.to_dict())
        try:
            graph = env.registry.prepared_resources.graph
            compilation = GraphCompiler().compile_with_findings(
                graph,
                registry=env.registry,
                plugin_registry=plugin_registry,
            )
            graph = compilation.workflow.graph
            compiled = compilation.compiled_graph
        except GraphConfigError as exc:
            return fail_report("CONFIG.SCHEMA.PARSE", str(exc), "config", str(config_path), "schema", effective_policy=effective_policy.to_dict())
        except GraphCompileError as exc:
            return fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology",
                effective_policy=effective_policy.to_dict(), details=exc.details)
        return PreparedWorkspaceGraph(document, graph, compilation, resources, plugin_registry, effective_policy, warnings)


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


def _environment_or_report(workspace: WorkspaceConfig, config_path=None, *, preparation=None, governance=None) -> WorkspaceEnvironment | HealthReport:
    root = workspace.root_for_path(Path(config_path).resolve()) if config_path else None
    if root is not None and root.project_target != "python":
        return _workspace_error_report(
            "CLI.PROJECT_TARGET.MISMATCH",
            f"Python Application requires project_target='python'; root {root.id!r} declares {root.project_target!r}",
            Path(config_path), default_effective_policy(),
        )
    try:
        return build_workspace_environment(workspace, config_path=config_path, preparation=preparation, governance=governance)
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(config_path))
    except ConfigSchemaError as exc:
        return HealthReport(status="FAIL", errors=annotate_findings(exc.findings, root=root, source_path=Path(config_path)) if root else exc.findings)
    except GraphConfigError as exc:
        from vibeflow.tooling.application.python.reports import graph_config_error_report
        return graph_config_error_report(exc, path=Path(config_path), effective_policy=default_effective_policy().to_dict())
    except WorkspaceConfigError as exc:
        path = Path(str(exc.source_location.get("path", workspace.path)))
        return _workspace_error_report(exc.rule_id, exc.message, path, default_effective_policy())
    except ResourcePreparationError as exc:
        return HealthReport(status="ERROR", errors=(HealthFinding(rule_id=exc.code, severity="error",
            object_type="descriptor", object_id=str(exc.details.get("resource_id", "")), message=exc.message,
            source_location={"path":exc.path, **exc.details.get("location", {})}, failure_layer="descriptor",
            details={"field":exc.field, "source":exc.path, **exc.details}),))
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
    "validate_workspace_config_path",
]
