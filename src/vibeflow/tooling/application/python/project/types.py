from __future__ import annotations

from dataclasses import dataclass

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.policy import EffectivePolicy
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.tooling.application.python.project.resource_selection import PythonResources
@dataclass(frozen=True)
class WorkspaceEnvironment:
    registry: NodeRegistry
    plugin_registry: PluginRegistry
    resources: PythonResources
    available_resources: PythonResources
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...]


__all__ = ["WorkspaceEnvironment"]
