"""Stable aggregate API for Python source and workflow quality."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "PythonSourceContext": ("vibeflow.targets.python.quality.source_context", "PythonSourceContext"),
    "PythonSourceFile": ("vibeflow.targets.python.quality.source_context", "PythonSourceFile"),
    "PythonSourceNode": ("vibeflow.targets.python.quality.source_context", "PythonSourceNode"),
    "PythonSourceCall": ("vibeflow.targets.python.quality.source_context", "PythonSourceCall"),
    "PythonSourceReference": ("vibeflow.targets.python.quality.source_context", "PythonSourceReference"),
    "PythonSourceImport": ("vibeflow.targets.python.quality.source_context", "PythonSourceImport"),
    "PythonSourceOwnership": ("vibeflow.targets.python.quality.source_context", "PythonSourceOwnership"),
    "PythonSymbol": ("vibeflow.targets.python.quality.source_context", "PythonSymbol"),
    "PythonSource": ("vibeflow.targets.python.quality.source", "PythonSource"),
    "PythonSourceQuality": (
        "vibeflow.targets.python.quality.source",
        "PythonSourceQuality",
    ),
    "source_context_quality_facts": ("vibeflow.targets.python.quality.project_context", "source_context_quality_facts"),
    "analyze_python_source_tree": ("vibeflow.targets.python.quality.source", "analyze_python_source_tree"),
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
    "HealthFinding": (
        "vibeflow.targets.python.quality.workflow",
        "HealthFinding",
    ),
    "HealthReport": (
        "vibeflow.targets.python.quality.workflow",
        "HealthReport",
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
