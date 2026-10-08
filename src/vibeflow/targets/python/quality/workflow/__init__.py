"""Stable workflow-level Python quality API, loaded on demand."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "HealthFinding": ("vibeflow.core.findings", "HealthFinding"),
    "HealthReport": ("vibeflow.core.findings", "HealthReport"),
    "validate_graph_health": (
        "vibeflow.targets.python.quality.workflow.validation",
        "validate_graph_health",
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
