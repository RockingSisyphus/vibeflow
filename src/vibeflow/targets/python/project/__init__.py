"""Stable Python project frontend API.

The exports are lazy so importing a leaf analyzer does not initialise the
registry, plugin loader, runtime, or the remaining frontend modules.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {}


def _export(module: str, *names: str) -> None:
    _EXPORTS.update({name: (module, name) for name in names})


_export(
    "vibeflow.targets.python.project.bindings",
    "PythonBindingError",
    "PythonBindingPlan",
    "PythonCallBinding",
)
_export(
    "vibeflow.targets.python.project.compiler",
    "CompiledGraph",
    "GraphCompileError",
    "GraphCompiler",
    "explicit_flow_cycles",
)
_export(
    "vibeflow.targets.python.nodetypes.protocols",
    "EFFECT_SCOPE_GLOBAL_STATE",
    "EFFECT_SCOPE_NONE",
    "EFFECT_SCOPE_PYTHON_IO",
    "EFFECT_SCOPE_TERMINAL",
    "EFFECT_SCOPE_TRUSTED",
    "PureNode",
)
_export(
    "vibeflow.targets.python.project.planned",
    "planned_stub_finding",
    "signature_is_run_stub",
    "validate_python_stub_source",
)
_export(
    "vibeflow.targets.python.project.planned_files",
    "validate_python_stub_file",
)
_export(
    "vibeflow.targets.python.project.plugins",
    "CompilerPlugin",
    "PluginDescriptor",
    "PluginRegistry",
    "RuntimePlugin",
    "plugin_error",
)
_export(
    "vibeflow.targets.python.project.policy",
    "DEFAULT_POLICY_DATA",
    "EffectivePolicy",
    "PolicyResolveResult",
    "default_effective_policy",
    "merge_policy",
)
_export(
    "vibeflow.targets.python.project.registry",
    "NodeRegistrationInfo",
    "NodeRegistry",
    "NodeRegistryError",
)

del _export

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
