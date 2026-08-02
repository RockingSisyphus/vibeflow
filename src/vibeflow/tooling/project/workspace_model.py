"""Target-neutral workspace configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from vibeflow.core.quality import QualityStructureLimits
from vibeflow.tooling.project.architecture_types import (
    ArchitectureDocumentSpec,
    WorkspaceConfigError,
)
from vibeflow.tooling.project.paths import is_relative_to


WORKSPACE_CONFIG_NAME = "vibeflow_config.jsonc"
PROJECT_CONFIG_NAME = "vibeflow_project.jsonc"
WORKSPACE_FORBIDDEN_CONFIG_FIELDS = frozenset({"policy"})
PROJECT_TARGETS = frozenset({"python", "javascript"})
ProjectTarget = Literal["python", "javascript"]


@dataclass(frozen=True)
class WorkspaceRoot:
    id: str
    path: Path
    config_path: Path
    project_config: Mapping[str, Any]
    project_target: ProjectTarget
    registry_ref: str = ""
    quality_enabled: bool = True
    quality_structure: QualityStructureLimits = field(
        default_factory=QualityStructureLimits
    )
    runtime_options: Mapping[str, object] = field(default_factory=dict)
    architecture_documents: tuple[ArchitectureDocumentSpec, ...] = ()


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
        matches = [
            root for root in self.roots if is_relative_to(resolved, root.path)
        ]
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda root: len(str(root.path)),
            reverse=True,
        )[0]


__all__ = [
    "PROJECT_CONFIG_NAME",
    "PROJECT_TARGETS",
    "ProjectTarget",
    "WORKSPACE_CONFIG_NAME",
    "WORKSPACE_FORBIDDEN_CONFIG_FIELDS",
    "WorkspaceConfig",
    "WorkspaceRoot",
]
