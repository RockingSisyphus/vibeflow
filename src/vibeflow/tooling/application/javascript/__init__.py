"""JavaScript/TypeScript application boundary."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "ProjectBuildError": (
        "vibeflow.tooling.application.javascript.build",
        "ProjectBuildError",
    ),
    "ProjectBuildRequest": (
        "vibeflow.tooling.application.javascript.build",
        "ProjectBuildRequest",
    ),
    "ProjectBuildResult": (
        "vibeflow.tooling.application.javascript.build",
        "ProjectBuildResult",
    ),
    "build_project_aot": (
        "vibeflow.tooling.application.javascript.build",
        "build_project_aot",
    ),
    "prepare_project_build": (
        "vibeflow.tooling.application.javascript.build",
        "prepare_project_build",
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
