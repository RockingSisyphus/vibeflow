"""Stable application-service API for CLI and workspace orchestration."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "CheckedRunError": ("vibeflow.tooling.application.python.runner", "CheckedRunError"),
    "CheckedRunResult": ("vibeflow.tooling.application.python.runner", "CheckedRunResult"),
    "run_checked": ("vibeflow.tooling.application.python.runner", "run_checked"),
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
