"""Observe checked runs from declaration loading through final artifacts."""

from functools import wraps
import json
import os
from pathlib import Path
import sys

from vibeflow.targets.python.runtime.observation import current_observation, observe_run
from vibeflow.targets.python.runtime.options import runtime_options
from vibeflow.tooling.project.diagnostic_sink import core_diagnostic_sink


def _resolve_observation_options(config_path, overrides, workspace=None):
    with core_diagnostic_sink(lambda _message: None):
        return _effective_observation_options(config_path, overrides, workspace)


def _effective_observation_options(config_path, overrides, workspace):
    from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace
    from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
    from vibeflow.tooling.application.python.project.project_options import _workspace_runtime_options
    try:
        if workspace is None:
            project = find_project_config(config_path)
            if project is not None:
                workspace = load_project_workspace(project)
        if workspace is not None:
            return _workspace_runtime_options(config_path, workspace=workspace, overrides=overrides)
    except WorkspaceConfigError:
        pass  # The checked loader reports this error after starting observation.
    return runtime_options(overrides)


def observed_checked_run(function):
    import inspect
    from contextlib import contextmanager

    @contextmanager
    def scope(args, kwargs):
        from vibeflow.tooling.application.python.preview_run import source_run_preview, bind_run_observer
        config = args[0] if args else kwargs['config_path']
        with source_run_preview(config, workspace=kwargs.get('workspace'), preview_root=kwargs.get('preview_root'), entry=kwargs.get('entry')):
            if current_observation() is not None:
                yield
                return
            from .run_directory import prepare_run_dir
            from .execution import _new_run_id
            run_id = _new_run_id() if kwargs.get('run_id') is None else kwargs['run_id']
            run_dir = kwargs.get('_prepared_run_dir') or prepare_run_dir(kwargs.get('run_root'), run_id)
            kwargs.update(run_id=run_id, _prepared_run_dir=run_dir)
            options = _resolve_observation_options(config, kwargs.get('runtime_options'), kwargs.get('workspace'))
            with observe_run(run_dir, options) as observer:
                bind_run_observer(observer)
                with core_diagnostic_sink(observer.write_kernel):
                    yield

    @wraps(function)
    def observed(*args, **kwargs):
        with scope(args, kwargs):
            return function(*args, **kwargs)

    @wraps(function)
    async def observed_async(*args, **kwargs):
        with scope(args, kwargs):
            return await function(*args, **kwargs)
    return observed_async if inspect.iscoroutinefunction(function) else observed


def print_run_report(payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    observer = current_observation()
    if observer is None:
        print(text)
        return
    observer.write_kernel(text)
    if payload.get("status") in {"ERROR", "FAIL"}:
        observer.transition("failed", payload.get("error") or "workflow check failed")
    if observer.terminal_stdout is not None:
        data = (text + "\n").encode("utf-8")
        offset = 0
        while offset < len(data):
            offset += os.write(observer.terminal_stdout, data[offset:])
    else:
        print(text, file=getattr(sys.stdout, "original", sys.stdout))


def observed_cli_run(function):
    @wraps(function)
    def observed(args):
        from vibeflow.tooling.application.python.cli import _runtime_options_from_args
        from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
        from vibeflow.tooling.application.python.execution import (_new_run_id)
        from vibeflow.targets.python.runtime.console_capture import capture_process_console
        from vibeflow.tooling.application.python.run_directory import RunDirectoryExistsError
        run_id = _new_run_id() if args.run_id is None else args.run_id
        run_root = (Path(args.run_root) if args.run_root else Path("runs")).resolve()
        try:
            run_dir = _prepare_run_dir(run_root, run_id)
        except (ValueError, OSError) as exc:
            if getattr(args, "command", None) == "delegate-cli":
                message = "run directory already exists" if isinstance(exc, RunDirectoryExistsError) else str(exc)
                print(f"vibeflow delegate-cli: {message}", file=sys.stderr)
            else:
                print_run_report({"status": "ERROR", "error": str(exc)})
            return 1
        args.run_id, args.run_root = run_id, str(run_root)
        args._prepared_run_dir = run_dir
        options = _resolve_observation_options(Path(args.config), _runtime_options_from_args(args))
        from vibeflow.tooling.application.python.preview_run import source_run_preview, bind_run_observer
        with source_run_preview(args.config, preview_root=getattr(args, "preview_root", None), entry=getattr(args, "entry", None)):
            with observe_run(run_dir, options) as observer:
                bind_run_observer(observer)
                with core_diagnostic_sink(observer.write_kernel), capture_process_console(observer):
                    code = function(args)
                    if code != 0 and observer.result["status"] != "failed":
                        observer.transition("failed", f"program exited with code {code}")
                    return code
    return observed
