from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.policy import EffectivePolicy
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.tooling.application.python.project.resource_selection import PythonResources
from vibeflow.tooling.project.architecture_types import (
    ArchitectureDocumentSpec,
    WorkspaceConfigError,
)
from vibeflow.tooling.project.workspace_model import (
    PROJECT_CONFIG_NAME,
    WORKSPACE_CONFIG_NAME,
    WORKSPACE_FORBIDDEN_CONFIG_FIELDS,
    WorkspaceConfig,
    WorkspaceRoot,
)


@dataclass(frozen=True)
class WorkspaceEnvironment:
    registry: NodeRegistry
    plugin_registry: PluginRegistry
    resources: PythonResources
    available_resources: PythonResources
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...]


__all__ = [
    "ArchitectureDocumentSpec",
    "PROJECT_CONFIG_NAME",
    "WORKSPACE_CONFIG_NAME",
    "WORKSPACE_FORBIDDEN_CONFIG_FIELDS",
    "WorkspaceConfig",
    "WorkspaceConfigError",
    "WorkspaceEnvironment",
    "WorkspaceRoot",
]
