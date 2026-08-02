"""Stable workflow-level Python quality API, loaded on demand."""

from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "HealthFinding": ("vibeflow.core.findings", "HealthFinding"),
    "HealthReport": ("vibeflow.core.findings", "HealthReport"),
    "PythonNodeQualityFacts": (
        "vibeflow.targets.python.quality.workflow.facts",
        "PythonNodeQualityFacts",
    ),
    "append_dependency_chain_findings": (
        "vibeflow.targets.python.quality.workflow.base_lib",
        "append_dependency_chain_findings",
    ),
    "base_lib_finding_to_health": (
        "vibeflow.targets.python.quality.workflow.base_lib",
        "base_lib_finding_to_health",
    ),
    "matching_unhealthy_base_module": (
        "vibeflow.targets.python.quality.workflow.base_lib",
        "matching_unhealthy_base_module",
    ),
    "nodeset_depth_error_report": (
        "vibeflow.targets.python.quality.workflow.nodesets",
        "nodeset_depth_error_report",
    ),
    "registry_namespace_findings": (
        "vibeflow.targets.python.quality.workflow.registry",
        "registry_namespace_findings",
    ),
    "validate_graph_health": (
        "vibeflow.targets.python.quality.workflow.validation",
        "validate_graph_health",
    ),
    "validate_node_config_health": (
        "vibeflow.targets.python.quality.workflow.node_config",
        "validate_node_config_health",
    ),
    "validate_nodeset_depth": (
        "vibeflow.targets.python.quality.workflow.nodesets",
        "validate_nodeset_depth",
    ),
    "validate_nodesets": (
        "vibeflow.targets.python.quality.workflow.nodesets",
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
