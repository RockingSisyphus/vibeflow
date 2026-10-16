"""Resolve Python workflow runtime options."""

from __future__ import annotations

from pathlib import Path

from vibeflow.targets.python.runtime.options import (
    RuntimeOptions,
    merge_runtime_options,
)
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
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
    return merge_runtime_options(root.runtime_options, overrides)



__all__ = ["_workspace_runtime_options"]
