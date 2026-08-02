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
    "vibeflow.targets.python.project.base_lib",
    "analyze_base_lib_source",
    "base_lib_imports_from_source",
    "build_base_lib_scan_report",
    "node_base_lib_imports",
    "scan_base_lib",
    "summarize_base_lib_dependency_chain",
)
_export(
    "vibeflow.targets.python.project.base_lib_types",
    "BaseLibDependencySummary",
    "BaseLibFinding",
    "BaseLibModuleReport",
    "BaseLibScanReport",
)
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
_export("vibeflow.targets.python.project.context", "Context", "ContextKeyError")
_export(
    "vibeflow.targets.python.project.descriptors",
    "LegacyDescriptorError",
    "PythonBaseLibAdapterResult",
    "PythonNodeAdapterResult",
    "adapt_base_lib_registry",
    "adapt_node_registry",
    "base_lib_catalog_from_registry",
    "base_lib_descriptor_from_registry",
    "catalog_from_node_registry",
    "node_descriptor_from_registry",
)
_export(
    "vibeflow.targets.python.project.node",
    "EFFECT_SCOPE_NONE",
    "EFFECT_SCOPE_PYTHON_IO",
    "EFFECT_SCOPE_TERMINAL",
    "EFFECT_SCOPE_TRUSTED",
    "NodeContract",
    "NodeInfo",
    "PureNode",
    "effective_effect_scope",
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
    "vibeflow.targets.python.project.plugin_loader",
    "load_plugins_from_config",
)
_export(
    "vibeflow.targets.python.project.plugins",
    "CompilerPlugin",
    "PluginDescriptor",
    "PluginRegistry",
    "PolicyPlugin",
    "RuntimePlugin",
    "plugin_error",
)
_export(
    "vibeflow.targets.python.project.policy",
    "DEFAULT_POLICY_DATA",
    "EffectivePolicy",
    "PolicyResolveResult",
    "apply_policy_plugins",
    "apply_policy_to_findings",
    "default_effective_policy",
    "merge_policy",
    "validate_plugin_relaxations",
)
_export(
    "vibeflow.targets.python.project.registry",
    "GLOBAL_NODE_REGISTRY",
    "NodeRegistrationInfo",
    "NodeRegistry",
    "NodeRegistryError",
)
_export("vibeflow.targets.python.project.registry_base", "RegistryBase")
_export(
    "vibeflow.targets.python.project.resources",
    "BaseLibInfo",
    "BaseLibRegistry",
    "BaseLibResource",
    "PluginInfo",
    "PluginResource",
    "PluginResourceRegistry",
    "normalize_base_lib_info",
    "normalize_plugin_config",
    "normalize_plugin_info",
    "plugin_status",
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
