"""Target-neutral validation of descriptor and JavaScript project options."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.project.architecture_types import WorkspaceConfigError


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
    if "host_extensions" in raw:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "Host Extension is retired; express initialization and cleanup as explicit workflow Nodes",
            {"path": str(path), "field": "javascript.host_extensions"},
        )
    allowed = {
        "package_root",
        "external_packages",
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
            "javascript.package_root must be a non-empty root-relative path",
            {"path": str(path)},
        )
    external = raw.get("external_packages", [])
    if (
        not isinstance(external, list)
        or not all(isinstance(item, str) and item.strip() for item in external)
    ):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT",
            "javascript.external_packages must be a list of non-empty package names",
            {"path": str(path)},
        )
    return {
        "package_root": package_root.strip(),
        "external_packages": tuple(
            dict.fromkeys(item.strip() for item in external)
        ),
    }


__all__ = ["project_javascript_options"]
