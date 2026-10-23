"""Python application boundary for execution and project orchestration."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "build_python_aot": ("vibeflow.tooling.application.python.build", "build_python_aot"),
    "PythonBuildResult": ("vibeflow.tooling.application.python.build", "PythonBuildResult"),
    "PythonBuildRequest": ("vibeflow.tooling.application.python.build", "PythonBuildRequest"),
    "PythonBundle": ("vibeflow.tooling.application.python.bundle", "PythonBundle"),
    "load_bundle": ("vibeflow.tooling.application.python.bundle", "load_bundle"),
    "CheckedRunError": (
        "vibeflow.tooling.application.python.execution",
        "CheckedRunError",
    ),
    "CheckedRunResult": (
        "vibeflow.tooling.application.python.execution",
        "CheckedRunResult",
    ),
    "run_checked_async": ("vibeflow.tooling.application.python.runner", "run_checked_async"),
    "run_workspace_checked_async": ("vibeflow.tooling.application.python.async_workspace", "run_workspace_checked_async"),
    "run_checked": (
        "vibeflow.tooling.application.python.runner",
        "run_checked",
    ),
    "run_workspace_checked": (
        "vibeflow.tooling.application.python.workspace_service",
        "run_workspace_checked",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
