from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol

from vibeflow.targets.javascript.frontend.errors import ProjectBuildError


class WorkspaceRoot(Protocol):
    """Structural project-root view required by JavaScript tooling."""

    project_config: Mapping[str, object]


def javascript_options(root: WorkspaceRoot) -> dict[str, object]:
    raw = root.project_config.get("javascript", {})
    if not isinstance(raw, Mapping):
        raise ProjectBuildError(
            "VF_AOT_JAVASCRIPT_CONFIG",
            "project javascript config must be an object",
        )
    package_root = str(raw.get("package_root", ".") or ".").strip()
    external = raw.get("external_packages", ())
    if isinstance(external, str) or not isinstance(external, (list, tuple)):
        raise ProjectBuildError(
            "VF_AOT_JAVASCRIPT_CONFIG",
            "javascript.external_packages must be a list",
        )
    host_extensions = raw.get("host_extensions", ())
    if (
        isinstance(host_extensions, str)
        or not isinstance(host_extensions, (list, tuple))
    ):
        raise ProjectBuildError(
            "VF_AOT_JAVASCRIPT_CONFIG",
            "javascript.host_extensions must be a list",
        )
    return {
        "package_root": package_root,
        "external_packages": tuple(
            dict.fromkeys(str(item).strip() for item in external)
        ),
        "host_extensions": tuple(
            dict.fromkeys(
                str(item).strip() for item in host_extensions
            )
        ),
    }


def safe_project_path(
    project_root: Path,
    value: str | Path,
    *,
    subject: str,
    require_file: bool = False,
    require_directory: bool = False,
) -> Path:
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else project_root / raw
    resolved = candidate.resolve()
    if resolved != project_root and project_root not in resolved.parents:
        raise ProjectBuildError(
            "VF_AOT_PATH",
            f"{subject} escapes the project root: {resolved}",
        )
    if require_file and not resolved.is_file():
        raise ProjectBuildError(
            "VF_AOT_PATH",
            f"{subject} is not a file: {resolved}",
        )
    if require_directory and not resolved.is_dir():
        raise ProjectBuildError(
            "VF_AOT_PATH",
            f"{subject} is not a directory: {resolved}",
        )
    return resolved


__all__ = ["javascript_options", "safe_project_path"]
