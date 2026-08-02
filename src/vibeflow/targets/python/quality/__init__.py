"""Stable aggregate API for Python source and workflow quality."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "PythonSource": ("vibeflow.targets.python.quality.source", "PythonSource"),
    "PythonSourceQuality": (
        "vibeflow.targets.python.quality.source",
        "PythonSourceQuality",
    ),
    "analyze_python_source": (
        "vibeflow.targets.python.quality.source",
        "analyze_python_source",
    ),
    "ModulePurityVisitor": (
        "vibeflow.targets.python.quality.source_analysis",
        "ModulePurityVisitor",
    ),
    "NodeMetrics": (
        "vibeflow.targets.python.quality.source_analysis",
        "NodeMetrics",
    ),
    "NodePurityVisitor": (
        "vibeflow.targets.python.quality.source_analysis",
        "NodePurityVisitor",
    ),
    "PurityPolicy": (
        "vibeflow.targets.python.quality.source_analysis",
        "PurityPolicy",
    ),
    "PurityViolation": (
        "vibeflow.targets.python.quality.source_analysis",
        "PurityViolation",
    ),
    "collect_node_metrics": (
        "vibeflow.targets.python.quality.source_analysis",
        "collect_node_metrics",
    ),
    "validate_node_class": (
        "vibeflow.targets.python.quality.source_analysis",
        "validate_node_class",
    ),
    "HealthFinding": (
        "vibeflow.targets.python.quality.workflow",
        "HealthFinding",
    ),
    "HealthReport": (
        "vibeflow.targets.python.quality.workflow",
        "HealthReport",
    ),
    "PythonNodeQualityFacts": (
        "vibeflow.targets.python.quality.workflow",
        "PythonNodeQualityFacts",
    ),
    "validate_graph_health": (
        "vibeflow.targets.python.quality.workflow",
        "validate_graph_health",
    ),
    "validate_node_config_health": (
        "vibeflow.targets.python.quality.workflow",
        "validate_node_config_health",
    ),
    "validate_nodeset_depth": (
        "vibeflow.targets.python.quality.workflow",
        "validate_nodeset_depth",
    ),
    "validate_nodesets": (
        "vibeflow.targets.python.quality.workflow",
        "validate_nodesets",
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
