"""Filesystem adapter for target-neutral workspace configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.quality import QualityStructureLimits
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_raw_config_document,
)
from vibeflow.tooling.project.project_architecture import (
    project_architecture_documents,
)
from vibeflow.tooling.project.project_config_options import (
    project_descriptor_paths,
    project_javascript_options,
)
from vibeflow.tooling.project.workspace_model import (
    PROJECT_CONFIG_NAME,
    PROJECT_TARGETS,
    ProjectTarget,
    WorkspaceConfig,
    WorkspaceRoot,
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
    roots = _workspace_roots(data.get("roots"), workspace_path=workspace_path)
    return WorkspaceConfig(
        path=workspace_path,
        root=workspace_path.parent.resolve(),
        policy=data.get("policy", {}),
        roots=tuple(roots),
    )


def load_project_workspace(path: str | Path) -> WorkspaceConfig:
    """Load one project root as an in-memory workspace.

    This supports project-scoped read-only commands when no surrounding
    ``vibeflow_config.jsonc`` exists.  No synthetic workspace file is written;
    the returned model simply gives the normal loaders the same root metadata.
    """

    project_path = Path(path).expanduser().resolve()
    config_path = (
        project_path
        if project_path.name == PROJECT_CONFIG_NAME and project_path.is_file()
        else find_project_config(project_path)
    )
    if config_path is None:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.MISSING",
            f"cannot find {PROJECT_CONFIG_NAME} above {project_path}",
            {"path": str(project_path)},
        )
    root_path = config_path.parent.resolve()
    root = _workspace_root_from_project_config(
        "project",
        root_path=root_path,
        config_path=config_path,
    )
    return WorkspaceConfig(
        path=config_path,
        root=root_path,
        policy={},
        roots=(root,),
    )


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
        unknown = set(item) - {"id", "path", "config"}
        if unknown:
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.UNKNOWN_FIELD",
                f"roots[{index}] contains unknown fields: {sorted(unknown)}",
                {"path": str(workspace_path)},
            )
        root_id = str(item.get("id", "")).strip()
        raw_path = str(item.get("path", "")).strip()
        if not root_id or not raw_path:
            raise WorkspaceConfigError(
                "WORKSPACE.ROOT.REQUIRED",
                f"roots[{index}] requires id and path",
                {"path": str(workspace_path)},
            )
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
    )


def _workspace_root_from_project_config(
    root_id: str,
    *,
    root_path: Path,
    config_path: Path,
) -> WorkspaceRoot:
    project_config = _load_project_config(config_path, root_path=root_path)
    return WorkspaceRoot(
        id=root_id,
        path=root_path,
        config_path=config_path,
        project_config=project_config,
        project_target=_project_target(project_config, config_path),
        registry_ref=str(project_config.get("registry", "")).strip(),
        quality_enabled=bool(project_config.get("quality_enabled", True)),
        quality_structure=_project_quality_structure(
            project_config,
            config_path,
        ),
        runtime_options=_project_runtime_options(project_config, config_path),
        architecture_documents=project_architecture_documents(
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
    unknown = set(data) - {
        "project_target",
        "registry",
        "quality_enabled",
        "quality",
        "runtime",
        "architecture",
        "base_lib",
        "plugins",
        "descriptors",
        "javascript",
    }
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.UNKNOWN_FIELD",
            f"project config contains unknown fields: {sorted(unknown)}",
            {"path": str(path)},
        )
    target = _project_target(data, path)
    _validate_project_target_fields(data, target=target, path=path)
    if "registry" in data and not isinstance(data["registry"], str):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.REGISTRY",
            "project config registry must be a string",
            {"path": str(path)},
        )
    if "quality_enabled" in data and not isinstance(
        data["quality_enabled"],
        bool,
    ):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            "project config quality_enabled must be a boolean",
            {"path": str(path)},
        )
    _project_quality_structure(data, path)
    _project_runtime_options(data, path)
    project_descriptor_paths(data, path)
    project_javascript_options(data, path)
    project_architecture_documents(data, root_path=root_path, path=path)
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
        descriptors = data.get("descriptors")
        if isinstance(descriptors, Mapping) and "host_extensions" in descriptors:
            conflicts.append("descriptors.host_extensions")
    else:
        conflicts.extend(
            field
            for field in ("registry", "runtime", "base_lib", "plugins")
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
        "async_max_workers",
        "async_flush_timeout",
        "nodeset_max_depth",
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
    if name in {"async_max_workers", "nodeset_max_depth"}:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.RUNTIME",
            f"runtime.{name} must be a positive integer",
            {"path": str(path)},
        )
    if value is None or (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    ):
        return value
    raise WorkspaceConfigError(
        "WORKSPACE.PROJECT_CONFIG.RUNTIME",
        "runtime.async_flush_timeout must be null or a non-negative number",
        {"path": str(path)},
    )


def _project_quality_structure(
    data: Mapping[str, Any],
    path: Path,
) -> QualityStructureLimits:
    raw_quality = data.get("quality")
    if raw_quality in (None, {}):
        return QualityStructureLimits()
    if not isinstance(raw_quality, Mapping):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            "project config quality must be an object",
            {"path": str(path)},
        )
    unknown_quality = set(raw_quality) - {"structure"}
    if unknown_quality:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            "project config quality contains unknown fields: "
            f"{sorted(unknown_quality)}",
            {"path": str(path)},
        )
    raw_structure = raw_quality.get("structure")
    if raw_structure in (None, {}):
        return QualityStructureLimits()
    if not isinstance(raw_structure, Mapping):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            "project config quality.structure must be an object",
            {"path": str(path)},
        )
    allowed = set(QualityStructureLimits().to_dict())
    unknown = set(raw_structure) - allowed
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            "project config quality.structure contains unknown fields: "
            f"{sorted(unknown)}",
            {"path": str(path)},
        )
    values = _quality_structure_values(raw_structure, path)
    limits = QualityStructureLimits(**values)
    _validate_quality_structure_pairs(limits, path)
    return limits


def _quality_structure_values(
    raw: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, value in raw.items():
        if field in {"enabled", "enforce_role_imports"}:
            if not isinstance(value, bool):
                raise WorkspaceConfigError(
                    "WORKSPACE.PROJECT_CONFIG.QUALITY",
                    f"quality.structure.{field} must be a boolean",
                    {"path": str(path)},
                )
            values[field] = value
        elif field == "allowed_root_code_files":
            values[field] = _string_tuple(
                value,
                f"quality.structure.{field}",
                path,
            )
        else:
            values[field] = _positive_int(
                value,
                f"quality.structure.{field}",
                path,
            )
    return values


def _validate_quality_structure_pairs(
    limits: QualityStructureLimits,
    path: Path,
) -> None:
    for warn_field, max_field in (
        ("warn_root_code_files", "max_root_code_files"),
        ("warn_code_dirs", "max_code_dirs"),
        ("warn_code_files_per_dir", "max_code_files_per_dir"),
        ("warn_code_dir_depth", "max_code_dir_depth"),
        ("warn_child_code_dirs_per_dir", "max_child_code_dirs_per_dir"),
        ("warn_root_level_code_files", "max_root_level_code_files"),
    ):
        if getattr(limits, warn_field) > getattr(limits, max_field):
            raise WorkspaceConfigError(
                "WORKSPACE.PROJECT_CONFIG.QUALITY",
                f"quality.structure.{warn_field} must be <= {max_field}",
                {"path": str(path)},
            )


def _positive_int(value: object, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            f"{field} must be a positive integer",
            {"path": str(path)},
        )
    return value


def _string_tuple(value: object, field: str, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.QUALITY",
            f"{field} must be a list of non-empty strings",
            {"path": str(path)},
        )
    return tuple(dict.fromkeys(item.strip() for item in value))


def _validate_workspace_keys(data: Mapping[str, Any], path: Path) -> None:
    unknown = set(data) - {"policy", "roots"}
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
