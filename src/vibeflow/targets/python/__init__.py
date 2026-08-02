"""High-level stable API for the Python Target.

Names are loaded lazily so selecting a frontend type does not initialise the
registry, runtime, or quality evaluator as a side effect.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    # Project frontend.
    "BaseLibRegistry": ("vibeflow.targets.python.project", "BaseLibRegistry"),
    "CompilerPlugin": ("vibeflow.targets.python.project", "CompilerPlugin"),
    "Context": ("vibeflow.targets.python.project", "Context"),
    "EffectivePolicy": ("vibeflow.targets.python.project", "EffectivePolicy"),
    "GraphCompileError": ("vibeflow.targets.python.project", "GraphCompileError"),
    "GraphCompiler": ("vibeflow.targets.python.project", "GraphCompiler"),
    "NodeContract": ("vibeflow.targets.python.project", "NodeContract"),
    "NodeInfo": ("vibeflow.targets.python.project", "NodeInfo"),
    "NodeRegistry": ("vibeflow.targets.python.project", "NodeRegistry"),
    "NodeRegistryError": ("vibeflow.targets.python.project", "NodeRegistryError"),
    "PluginDescriptor": ("vibeflow.targets.python.project", "PluginDescriptor"),
    "PluginRegistry": ("vibeflow.targets.python.project", "PluginRegistry"),
    "PolicyPlugin": ("vibeflow.targets.python.project", "PolicyPlugin"),
    "PureNode": ("vibeflow.targets.python.project", "PureNode"),
    "PythonBindingPlan": ("vibeflow.targets.python.project", "PythonBindingPlan"),
    "RuntimePlugin": ("vibeflow.targets.python.project", "RuntimePlugin"),
    "load_plugins_from_config": (
        "vibeflow.targets.python.project",
        "load_plugins_from_config",
    ),
    # Quality.
    "NodeMetrics": ("vibeflow.targets.python.quality", "NodeMetrics"),
    "PurityPolicy": ("vibeflow.targets.python.quality", "PurityPolicy"),
    "PurityViolation": ("vibeflow.targets.python.quality", "PurityViolation"),
    "collect_node_metrics": (
        "vibeflow.targets.python.quality",
        "collect_node_metrics",
    ),
    "validate_graph_health": (
        "vibeflow.targets.python.quality",
        "validate_graph_health",
    ),
    "validate_node_class": (
        "vibeflow.targets.python.quality",
        "validate_node_class",
    ),
    # Runtime.
    "ExecutionPlan": ("vibeflow.targets.python.runtime", "ExecutionPlan"),
    "PipelineRuntime": ("vibeflow.targets.python.runtime", "PipelineRuntime"),
    "PipelineRuntimeError": (
        "vibeflow.targets.python.runtime",
        "PipelineRuntimeError",
    ),
    "RuntimeOptions": ("vibeflow.targets.python.runtime", "RuntimeOptions"),
    "RuntimeTrace": ("vibeflow.targets.python.runtime", "RuntimeTrace"),
    "build_execution_plan": (
        "vibeflow.targets.python.runtime",
        "build_execution_plan",
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
