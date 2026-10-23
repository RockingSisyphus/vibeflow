"""Native asynchronous checked source entry, sharing project preparation."""
from __future__ import annotations
from .workspace_service import Any, CheckedRunError, CheckedRunResult, HealthReport, Mapping, Path, WorkspaceConfig, _environment_or_report, _final_compilation, _prepare_workspace_graph, _python_check_scope, _validate_prepared_workspace_graph, _workspace_runtime_options, observed_checked_run, replace, source_paths, summarize_mapping, validate_run_id

@observed_checked_run
async def run_workspace_checked_async(config_path: str | Path, *, workspace: WorkspaceConfig, initial: Mapping[str, Any] | None=None, run_root: str | Path | None=None, run_id: str | None=None, runtime_options: object | None=None, delegate_cli: bool=False, capabilities: Mapping[str, object] | None=None, workflow_instance_id: str | None=None, _prepared_run_dir: Path | None=None, preview_root: str | Path | None=None, entry: str | None=None, signal=None) -> CheckedRunResult:
    from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
    from vibeflow.tooling.application.python.execution import _execute_runtime_async, _new_run_id, _summarize_run_result, _write_json, _write_refused_artifacts
    from vibeflow.tooling.application.python.preflight import _refuse_on_health_failure, _refuse_on_planned_run, _write_preflight_artifacts
    actual_run_id = _new_run_id() if run_id is None else validate_run_id(run_id)
    if _prepared_run_dir is None:
        run_dir = _prepare_run_dir(run_root, actual_run_id)
    else:
        run_dir = Path(_prepared_run_dir)
        expected_run_dir = (Path(run_root) if run_root is not None else Path('runs')) / actual_run_id
        if run_dir != expected_run_dir or not run_dir.is_dir():
            raise ValueError('_prepared_run_dir must be the already claimed directory for this checked run')
    _write_json(run_dir / 'input_summary.json', summarize_mapping(dict(initial or {})))
    env = _environment_or_report(workspace, Path(config_path))
    if isinstance(env, HealthReport):
        _write_refused_artifacts(run_dir, env, include_effective_policy=True)
        raise CheckedRunError('run refused: workspace load failed', CheckedRunResult(actual_run_id, run_dir, env))
    with _python_check_scope(env.registry):
        prepared = _prepare_workspace_graph(Path(config_path), workspace=workspace, env=env)
        if isinstance(prepared, HealthReport):
            _write_refused_artifacts(run_dir, prepared, include_effective_policy=True)
            raise CheckedRunError(f'run refused: health status {prepared.status}', CheckedRunResult(actual_run_id, run_dir, prepared))
        effective_runtime_options = _workspace_runtime_options(config_path, workspace=workspace, overrides=runtime_options)
        graph, resources = (prepared.graph, prepared.resources)
        plugin_registry, effective_policy = (prepared.plugin_registry, prepared.effective_policy)
        _write_json(run_dir / 'effective_policy.json', effective_policy.to_dict())
        from vibeflow.core.workflows.entries import choose_entry
        selected_entry = choose_entry(graph.entries, graph.default_entry, entry)
        validation_kwargs = {'delegate_cli': True} if delegate_cli else {}
        if selected_entry is not None:
            validation_kwargs['entry'] = selected_entry
        health = _validate_prepared_workspace_graph(prepared, env=env, workspace=workspace, runtime_options=effective_runtime_options, rule_phase='run', **validation_kwargs)
        if health.status in {'FAIL', 'ERROR'}:
            _write_refused_artifacts(run_dir, health)
            _refuse_on_health_failure(health, run_dir, actual_run_id)
        compilation = _final_compilation(graph, env.registry)
        graph, compiled = (compilation.workflow.graph, compilation.compiled_graph)
        from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
        presentation = prepare_python_presentation(graph, registry=env.registry, resources=resources, compilation=compilation)
        _refuse_on_planned_run(graph, health, run_dir, actual_run_id, registry=env.registry, resources=resources, runtime_options=effective_runtime_options, compiled=compiled, prepared=presentation, entry=entry)
        _write_preflight_artifacts(run_dir, graph, compiled, health, registry=env.registry, resources=resources, prepared=presentation)
        _refuse_on_health_failure(health, run_dir, actual_run_id)
        execute_kwargs = {'delegate_cli': True} if delegate_cli else {}
        if capabilities is not None:
            execute_kwargs['capabilities'] = capabilities
        if workflow_instance_id is not None:
            execute_kwargs['workflow_instance_id'] = workflow_instance_id
        from vibeflow.tooling.application.python.project.lifecycle import lifecycle_registry, checked_runtime_plugins
        from vibeflow.targets.python.project.plugins import plugin_lifetime_async, create_plugins_async
        runtime_registry = await create_plugins_async(lambda owned: checked_runtime_plugins(lambda: lifecycle_registry(env.registry, workflow_id=str(config_path), config_path=config_path, plugin_types=('runtime',), _owned=owned), config_path=config_path, effective_policy=effective_policy, run_dir=run_dir))
        health = replace(health, info={**health.info, 'plugins': {'plugins': [*plugin_registry.to_dict()['plugins'], *runtime_registry.to_dict()['plugins']]}})
        _write_json(run_dir / 'health_report.json', health.to_dict())
        with source_paths(env.registry.source_roots):
            async with plugin_lifetime_async(runtime_registry):
                context = await _execute_runtime_async(graph, env.registry, runtime_registry, initial, run_dir, effective_runtime_options, resources, health=health, entry=entry, signal=signal, **execute_kwargs)
        _write_json(run_dir / 'output_summary.json', _summarize_run_result(context))
        from .execution import checked_result
        return checked_result(actual_run_id, run_dir, health, context, graph, entry)
