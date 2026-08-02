"""Validation of per-project descriptor and JavaScript options."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.targets.python.runtime.options import (
    RuntimeOptions,
    runtime_options as normalize_runtime_options,
)
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.types import WorkspaceConfig


def _workspace_runtime_options(
    config_path: str | Path,
    *,
    workspace: WorkspaceConfig,
    overrides: object | None = None,
) -> RuntimeOptions:
    """Resolve one workflow's effective Python runtime options."""

    root = workspace.root_for_path(config_path)
    if root is None:
        raise WorkspaceConfigError(
            "WORKSPACE.CONFIG.OUTSIDE_ROOT",
            f"config is not under any workspace root: {Path(config_path).resolve()}",
            {"path": str(Path(config_path).resolve())},
        )
    if isinstance(overrides, RuntimeOptions):
        return overrides
    values = dict(root.runtime_options)
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            return normalize_runtime_options(overrides)
        values.update(dict(overrides))
    return normalize_runtime_options(values)


def project_descriptor_paths(
    data: Mapping[str, Any],
    path: Path,
) -> Mapping[str, tuple[str, ...]]:
    raw = data.get("descriptors")
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.DESCRIPTORS",
            "project config descriptors must be an object",
            {"path": str(path)},
        )
    allowed = {
        "nodes",
        "base_lib",
        "data_schemas",
        "capabilities",
        "host_extensions",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.DESCRIPTORS",
            "project config descriptors contains unknown fields: "
            f"{sorted(unknown)}",
            {"path": str(path)},
        )
    result: dict[str, tuple[str, ...]] = {}
    for name, value in raw.items():
        if (
            not isinstance(value, list)
            or not all(
                isinstance(item, str) and item.strip()
                for item in value
            )
        ):
            raise WorkspaceConfigError(
                "WORKSPACE.PROJECT_CONFIG.DESCRIPTORS",
                f"descriptors.{name} must be a list of non-empty "
                "root-relative paths",
                {"path": str(path)},
            )
        result[str(name)] = tuple(
            dict.fromkeys(item.strip() for item in value)
        )
    return result


def project_javascript_options(
    data: Mapping[str, Any],
    path: Path,
) -> Mapping[str, object]:
    raw = data.get("javascript")
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "project config javascript must be an object",
            {"path": str(path)},
        )
    allowed = {
        "package_root",
        "external_packages",
        "host_extensions",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "project config javascript contains unknown fields: "
            f"{sorted(unknown)}",
            {"path": str(path)},
        )
    package_root = raw.get("package_root", ".")
    if not isinstance(package_root, str) or not package_root.strip():
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "javascript.package_root must be a non-empty "
            "root-relative path",
            {"path": str(path)},
        )
    external = raw.get("external_packages", [])
    if (
        not isinstance(external, list)
        or not all(
            isinstance(item, str) and item.strip()
            for item in external
        )
    ):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "javascript.external_packages must be a list of non-empty "
            "package names",
            {"path": str(path)},
        )
    host_extensions = raw.get("host_extensions", [])
    if (
        not isinstance(host_extensions, list)
        or not all(
            isinstance(item, str) and item.strip()
            for item in host_extensions
        )
    ):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "javascript.host_extensions must be a list of non-empty "
            "host_extension ids",
            {"path": str(path)},
        )
    return {
        "package_root": package_root.strip(),
        "external_packages": tuple(
            dict.fromkeys(item.strip() for item in external)
        ),
        "host_extensions": tuple(
            dict.fromkeys(item.strip() for item in host_extensions)
        ),
    }


__all__ = ["project_descriptor_paths", "project_javascript_options"]
