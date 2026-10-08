"""High-level stable API for the Python Target.

Names are loaded lazily so selecting a frontend type does not initialise the
registry, runtime, or quality evaluator as a side effect.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    # Project frontend.
    "CompilerPlugin": ("vibeflow.targets.python.project", "CompilerPlugin"),
    "EffectivePolicy": ("vibeflow.targets.python.project", "EffectivePolicy"),
    "GraphCompileError": ("vibeflow.targets.python.project", "GraphCompileError"),
    "GraphCompiler": ("vibeflow.targets.python.project", "GraphCompiler"),
    "NodeRegistry": ("vibeflow.targets.python.project", "NodeRegistry"),
    "NodeRegistryError": ("vibeflow.targets.python.project", "NodeRegistryError"),
    "PluginDescriptor": ("vibeflow.targets.python.project", "PluginDescriptor"),
    "PluginRegistry": ("vibeflow.targets.python.project", "PluginRegistry"),
    "PureNode": ("vibeflow.targets.python.project", "PureNode"),
    "PythonBindingPlan": ("vibeflow.targets.python.project", "PythonBindingPlan"),
    "RuntimePlugin": ("vibeflow.targets.python.project", "RuntimePlugin"),
    # Quality.
    "NodeMetrics": ("vibeflow.targets.python.quality", "NodeMetrics"),
    "PurityPolicy": ("vibeflow.targets.python.quality", "PurityPolicy"),
    "PurityViolation": ("vibeflow.targets.python.quality", "PurityViolation"),
    "validate_graph_health": (
        "vibeflow.targets.python.quality",
        "validate_graph_health",
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
