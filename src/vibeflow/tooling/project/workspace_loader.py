"""Filesystem adapter for target-neutral workspace configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_raw_config_document,
)
from vibeflow.tooling.project.architecture_registration import (
    root_architecture_documents,
)
from vibeflow.tooling.project.project_config_options import (
    project_javascript_options,
)
from vibeflow.tooling.project.workspace_model import (
    PROJECT_CONFIG_NAME,
    PROJECT_TARGETS,
    ProjectTarget,
    WorkspaceConfig,
    WorkspaceRoot,
    WORKSPACE_CONFIG_NAME,
)


def load_workspace_config(path: str | Path) -> WorkspaceConfig:
    """Load workspace and project metadata without importing any Target."""

    workspace_path = Path(path).resolve()
    try:
        document = load_raw_config_document(workspace_path)
    except ConfigLoadError as exc:
        raise WorkspaceConfigError(
            exc.rule_id,
            exc.message,
            exc.source_location,
            exc.failure_layer,
        ) from exc
    data = document.data
    _validate_workspace_keys(data, workspace_path)
    if not isinstance(data.get("purpose", ""), str):
        raise WorkspaceConfigError("WORKSPACE.PURPOSE", "project purpose must be a string", {"path":str(workspace_path)})
    roots = _workspace_roots(data.get("roots"), workspace_path=workspace_path)
    return WorkspaceConfig(
        path=workspace_path,
        root=workspace_path.parent.resolve(),
        roots=tuple(roots),
        purpose=data.get("purpose", ""),
    )


def load_project_workspace(path: str | Path) -> WorkspaceConfig:
    """Load the registered project containing a root or workflow path."""
    candidate = Path(path).expanduser().resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for directory in (start, *start.parents):
        config = directory / WORKSPACE_CONFIG_NAME
        if config.is_file():
            workspace = load_workspace_config(config)
            if candidate not in {config, directory} and workspace.root_for_path(candidate) is None:
                raise WorkspaceConfigError("WORKSPACE.ROOT.UNREGISTERED",
                    f"path does not belong to a registered root: {candidate}", {"path": str(candidate)})
            return workspace
    raise WorkspaceConfigError("WORKSPACE.CONFIG.MISSING",
        f"create {WORKSPACE_CONFIG_NAME} with at least one root in a separate subdirectory; "
        "standalone roots are no longer supported", {"path": str(candidate)})


def find_project_config(path: str | Path) -> Path | None:
    """Return the nearest canonical project config without loading a Target."""

    candidate = Path(path).expanduser().resolve()
    start = candidate if candidate.is_dir() else candidate.parent
    for directory in (start, *start.parents):
        config_path = directory / PROJECT_CONFIG_NAME
        if config_path.is_file():
            return config_path
    return None


def load_project_target(path: str | Path) -> ProjectTarget:
    """Load and validate one project config, returning its declared Target."""

    config_path = Path(path).expanduser().resolve()
    project_config = _load_project_config(
        config_path,
        root_path=config_path.parent,
    )
    return _project_target(project_config, config_path)


def _workspace_roots(
    value: object,
    *,
    workspace_path: Path,
) -> list[WorkspaceRoot]:
    if not isinstance(value, list) or not value:
        raise WorkspaceConfigError(
            "WORKSPACE.ROOTS",
            "workspace roots must be a non-empty list",
            {"path": str(workspace_path)},
        )
    roots: list[WorkspaceRoot] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.SHAPE",
                f"roots[{index}] must be an object",
                {"path": str(workspace_path)},
            )
        unknown = set(item) - {"id", "path", "config", "purpose"}
        if unknown:
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.UNKNOWN_FIELD",
                f"roots[{index}] contains unknown fields: {sorted(unknown)}",
                {"path": str(workspace_path)},
            )
        if not isinstance(item.get("purpose", ""), str):
            raise WorkspaceConfigError("WORKSPACE.ROOT.PURPOSE", "root purpose must be a string", {"path":str(workspace_path)})
        if not isinstance(item.get("id"), str) or not isinstance(item.get("path"), str):
            raise WorkspaceConfigError("WORKSPACE.ROOT.REQUIRED", "root id and path must be strings", {"path":str(workspace_path)})
        root_id = item["id"].strip()
        raw_path = item["path"].strip()
        if not root_id or not raw_path:
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.REQUIRED",
                f"roots[{index}] requires id and path",
                {"path": str(workspace_path)},
            )
        if root_id.startswith("@"):
            raise WorkspaceConfigError("WORKSPACE.ROOT.ID", "root IDs cannot start with @ (reserved for project scope)", {"path":str(workspace_path)})
        if root_id in seen:
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.DUPLICATE",
                f"duplicate workspace root id: {root_id}",
                {"path": str(workspace_path)},
            )
        seen.add(root_id)
        roots.append(
            _workspace_root_from_item(
                root_id,
                item,
                workspace_path=workspace_path,
            )
        )
    for index, root in enumerate(roots):
        for other in roots[:index]:
            if root.path.is_relative_to(other.path) or other.path.is_relative_to(root.path):
                raise WorkspaceConfigError("WORKSPACE.ROOT.OVERLAP",
                    f"roots '{root.id}' and '{other.id}' must have separate directories",
                    {"path": str(workspace_path)})
    return roots


def _workspace_root_from_item(
    root_id: str,
    item: Mapping[str, Any],
    *,
    workspace_path: Path,
) -> WorkspaceRoot:
    root_path = _resolve_workspace_relative(
        str(item.get("path", "")).strip(),
        base=workspace_path.parent,
    )
    project_path = workspace_path.parent.resolve()
    if root_path == project_path or not root_path.is_relative_to(project_path):
        raise WorkspaceConfigError("WORKSPACE.ROOT.SEPARATE_DIRECTORY",
            "each root must be in its own subdirectory of the project; path '.' is unsupported",
            {"path": str(workspace_path), "root": root_id})
    if not root_path.is_dir():
        raise WorkspaceConfigError(
            "WORKSPACE.ROOT.PATH",
            f"workspace root path does not exist: {root_path}",
            {"path": str(workspace_path)},
        )
    config_name = (
        str(item.get("config", PROJECT_CONFIG_NAME)).strip()
        or PROJECT_CONFIG_NAME
    )
    config_path = _resolve_workspace_relative(config_name, base=root_path)
    if not config_path.is_relative_to(root_path):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.PATH",
            "root configuration must be inside its root directory", {"path": str(config_path)})
    if not config_path.is_file():
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.MISSING",
            f"project config does not exist: {config_path}",
            {"path": str(config_path)},
        )
    return _workspace_root_from_project_config(
        root_id,
        root_path=root_path,
        config_path=config_path,
        purpose=item.get("purpose", ""),
    )


def _workspace_root_from_project_config(
    root_id: str,
    *,
    root_path: Path,
    config_path: Path,
    purpose: str = "",
) -> WorkspaceRoot:
    if not isinstance(purpose, str):
        raise WorkspaceConfigError("WORKSPACE.ROOT.PURPOSE", "root purpose must be a string", {"path": str(config_path)})
    project_config = _load_project_config(config_path, root_path=root_path)
    return WorkspaceRoot(
        id=root_id,
        path=root_path,
        config_path=config_path,
        project_config=project_config,
        project_target=_project_target(project_config, config_path),
        purpose=purpose,
        runtime_options=_project_runtime_options(project_config, config_path),
        architecture_documents=root_architecture_documents(
            project_config,
            root_path=root_path,
            path=config_path,
        ),
    )


def _load_project_config(
    path: Path,
    *,
    root_path: Path,
) -> Mapping[str, Any]:
    try:
        document = load_raw_config_document(path)
    except ConfigLoadError as exc:
        raise WorkspaceConfigError(
            exc.rule_id,
            exc.message,
            exc.source_location,
            exc.failure_layer,
        ) from exc
    data = document.data
    removed = set(data) & {"registry", "descriptors", "base_lib", "plugins"}
    if removed:
        raise WorkspaceConfigError("PLUGIN.REGISTRATION.MIGRATION",
            f"project resource registration was removed: {sorted(removed)}; define fixed SDK plugins and select workflow.plugins",
            {"path": str(path), "field": sorted(removed)[0], "fields": sorted(removed)})
    unknown = set(data) - {
        "project_target",
        "runtime",
        "architecture",
        "javascript",
        "preview",
    }
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.UNKNOWN_FIELD",
            f"project config contains unknown fields: {sorted(unknown)}",
            {"path": str(path)},
        )
    target = _project_target(data, path)
    _validate_project_target_fields(data, target=target, path=path)
    _project_runtime_options(data, path)
    project_javascript_options(data, path)
    root_architecture_documents(data, root_path=root_path, path=path)
    from vibeflow.tooling.project.preview_options import validate_preview_options
    validate_preview_options(data.get("preview", {}), path=path)
    return data


def _project_target(
    data: Mapping[str, Any],
    path: Path,
) -> ProjectTarget:
    if "project_target" not in data:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_TARGET.MISSING",
            "project config requires project_target: 'python' or 'javascript'",
            {"path": str(path), "field": "project_target"},
        )
    value = data.get("project_target")
    if not isinstance(value, str) or value not in PROJECT_TARGETS:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_TARGET.INVALID",
            "project config project_target must be exactly 'python' or 'javascript'",
            {
                "path": str(path),
                "field": "project_target",
                "value": value,
            },
        )
    return value


def _validate_project_target_fields(
    data: Mapping[str, Any],
    *,
    target: ProjectTarget,
    path: Path,
) -> None:
    conflicts: list[str] = []
    if target == "python":
        if "javascript" in data:
            conflicts.append("javascript")
    else:
        conflicts.extend(
            field
            for field in ("runtime",)
            if field in data
        )
    if not conflicts:
        return
    raise WorkspaceConfigError(
        "WORKSPACE.PROJECT_TARGET.FIELD_CONFLICT",
        f"project_target {target!r} does not allow fields: {sorted(conflicts)}",
        {
            "path": str(path),
            "field": conflicts[0],
            "fields": sorted(conflicts),
            "project_target": target,
        },
    )


def _project_runtime_options(
    data: Mapping[str, Any],
    path: Path,
) -> Mapping[str, object]:
    raw_runtime = data.get("runtime")
    if raw_runtime in (None, {}):
        return {}
    if not isinstance(raw_runtime, Mapping):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.RUNTIME",
            "project config runtime must be an object",
            {"path": str(path)},
        )
    allowed = {
        "status_interval",
        "status_file",
    }
    unknown = set(raw_runtime) - allowed
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.RUNTIME",
            f"project config runtime contains unknown fields: {sorted(unknown)}",
            {"path": str(path)},
        )
    return {
        name: _project_runtime_value(name, value, path=path)
        for name, value in raw_runtime.items()
    }


def _project_runtime_value(name: str, value: object, *, path: Path) -> object:
    if name == "status_file":
        if value is None or isinstance(value, str) and value:
            return value
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.RUNTIME",
                                   "runtime.status_file must be null or a nonempty path string", {"path": str(path)})
    if name == "status_interval":
        import math
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            return value
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.RUNTIME",
                                   "runtime.status_interval must be positive finite seconds", {"path": str(path)})


def _validate_workspace_keys(data: Mapping[str, Any], path: Path) -> None:
    unknown = set(data) - {"roots", "purpose"}
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.UNKNOWN_FIELD",
            f"workspace config contains unknown fields: {sorted(unknown)}",
            {"path": str(path)},
        )
    if "roots" not in data:
        raise WorkspaceConfigError(
            "WORKSPACE.ROOTS",
            "workspace config requires roots",
            {"path": str(path)},
        )


def _resolve_workspace_relative(value: str, *, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


__all__ = [
    "find_project_config",
    "load_project_workspace",
    "load_project_target",
    "load_workspace_config",
]
