"""Python-specific workspace and project adapters."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "WorkspaceConfig": (
        "vibeflow.tooling.project.workspace_model",
        "WorkspaceConfig",
    ),
    "WorkspaceConfigError": (
        "vibeflow.tooling.project.architecture_types",
        "WorkspaceConfigError",
    ),
    "WorkspaceEnvironment": (
        "vibeflow.tooling.application.python.project.types",
        "WorkspaceEnvironment",
    ),
    "load_workspace_config": (
        "vibeflow.tooling.application.python.project.core",
        "load_workspace_config",
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
