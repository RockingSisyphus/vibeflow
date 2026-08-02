"""Canonical project-file loading, descriptors, resources, and diagnostics."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "WorkspaceConfig": ("vibeflow.tooling.project.types", "WorkspaceConfig"),
    "WorkspaceConfigError": (
        "vibeflow.tooling.project.architecture_types",
        "WorkspaceConfigError",
    ),
    "collect_python_workflow_quality_facts": (
        "vibeflow.tooling.project.python_quality",
        "collect_python_workflow_quality_facts",
    ),
    "load_workspace_config": (
        "vibeflow.tooling.project.core",
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
