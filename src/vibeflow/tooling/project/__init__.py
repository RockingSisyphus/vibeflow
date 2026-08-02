"""Canonical project-file loading, descriptors, resources, and diagnostics."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "WorkspaceConfig": (
        "vibeflow.tooling.project.workspace_model",
        "WorkspaceConfig",
    ),
    "WorkspaceRoot": (
        "vibeflow.tooling.project.workspace_model",
        "WorkspaceRoot",
    ),
    "ProjectTarget": (
        "vibeflow.tooling.project.workspace_model",
        "ProjectTarget",
    ),
    "PROJECT_TARGETS": (
        "vibeflow.tooling.project.workspace_model",
        "PROJECT_TARGETS",
    ),
    "WorkspaceConfigError": (
        "vibeflow.tooling.project.architecture_types",
        "WorkspaceConfigError",
    ),
    "load_workspace_config": (
        "vibeflow.tooling.project.workspace_loader",
        "load_workspace_config",
    ),
    "load_project_workspace": (
        "vibeflow.tooling.project.workspace_loader",
        "load_project_workspace",
    ),
    "find_project_config": (
        "vibeflow.tooling.project.workspace_loader",
        "find_project_config",
    ),
    "load_project_target": (
        "vibeflow.tooling.project.workspace_loader",
        "load_project_target",
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
