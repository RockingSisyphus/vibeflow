from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from vibeflow.config.resources import BaseLibRegistry, ConfigResources, PluginResourceRegistry
from vibeflow.devtools.code_quality_types import QualityStructureLimits
from vibeflow.health.types import HealthFinding
from vibeflow.config.path_utils import is_relative_to
from vibeflow.plugin import PluginRegistry
from vibeflow.policy import EffectivePolicy
from vibeflow.registry import NodeRegistry


WORKSPACE_CONFIG_NAME = "vibeflow_config.jsonc"
PROJECT_CONFIG_NAME = "vibeflow_project.jsonc"
WORKSPACE_FORBIDDEN_CONFIG_FIELDS = frozenset({"policy"})


@dataclass(frozen=True)
class WorkspaceResourceRegistries:
    base_libs: BaseLibRegistry = field(default_factory=BaseLibRegistry)
    plugins: PluginResourceRegistry = field(default_factory=PluginResourceRegistry)
    base_lib_paths: tuple[str, ...] = ()
    has_base_lib_registry: bool = False
    has_plugin_registry: bool = False


@dataclass
class WorkspaceConfigError(ValueError):
    rule_id: str
    message: str
    source_location: Mapping[str, object]
    failure_layer: str = "workspace"

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class WorkspaceRoot:
    id: str
    path: Path
    config_path: Path
    project_config: Mapping[str, Any]
    registry_ref: str = ""
    quality_enabled: bool = True
    quality_structure: QualityStructureLimits = field(default_factory=QualityStructureLimits)
    runtime_options: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceConfig:
    path: Path
    root: Path
    policy: object
    roots: tuple[WorkspaceRoot, ...]

    def root_by_id(self, root_id: str) -> WorkspaceRoot:
        for root in self.roots:
            if root.id == root_id:
                return root
        raise WorkspaceConfigError(
            "WORKSPACE.ROOT.UNKNOWN",
            f"unknown workspace root id: {root_id}",
            {"path": str(self.path)},
        )

    def resolve_root_path(self, root_id: str, value: str) -> Path:
        root = self.root_by_id(root_id)
        path = Path(value)
        if not path.is_absolute():
            path = root.path / path
        return path.resolve()

    def root_for_path(self, path: Path | str) -> WorkspaceRoot | None:
        resolved = Path(path).resolve()
        matches = [root for root in self.roots if is_relative_to(resolved, root.path)]
        if not matches:
            return None
        return sorted(matches, key=lambda root: len(str(root.path)), reverse=True)[0]


@dataclass(frozen=True)
class WorkspaceEnvironment:
    registry: NodeRegistry
    plugin_registry: PluginRegistry
    resources: ConfigResources
    available_resources: ConfigResources
    resource_registries: Mapping[str, WorkspaceResourceRegistries]
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...]
