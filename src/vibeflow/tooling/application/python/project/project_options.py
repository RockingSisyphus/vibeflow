"""Python runtime options plus neutral project-option compatibility exports."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from vibeflow.targets.python.runtime.options import (
    RuntimeOptions,
    runtime_options as normalize_runtime_options,
)
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.project_config_options import (
    project_descriptor_paths,
    project_javascript_options,
)
from vibeflow.tooling.project.workspace_model import WorkspaceConfig


def _workspace_runtime_options(
    config_path: str | Path,
    *,
    workspace: WorkspaceConfig,
    overrides: object | None = None,
) -> RuntimeOptions:
    """Resolve one workflow's effective Python runtime options."""

    root = workspace.root_for_path(config_path)
    if root is None:
        resolved = Path(config_path).resolve()
        raise WorkspaceConfigError(
            "WORKSPACE.CONFIG.OUTSIDE_ROOT",
            f"config is not under any workspace root: {resolved}",
            {"path": str(resolved)},
        )
    if isinstance(overrides, RuntimeOptions):
        return overrides
    values = dict(root.runtime_options)
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            return normalize_runtime_options(overrides)
        values.update(dict(overrides))
    return normalize_runtime_options(values)


__all__ = [
    "project_descriptor_paths",
    "project_javascript_options",
]
