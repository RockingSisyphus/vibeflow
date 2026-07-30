from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from vibeflow.config.loader import ConfigLoadError, load_raw_config_document
from vibeflow.descriptors._manifest_parser import (
    parse_descriptor_manifest as _parse_descriptor_manifest,
)
from vibeflow.descriptors.catalogs import (
    BaseLibCatalog,
    CapabilityCatalog,
    DescriptorCatalogError,
    DescriptorCatalogs,
    HostExtensionCatalog,
    NodeCatalog,
    SchemaRegistry,
)
from vibeflow.descriptors.models import (
    BaseLibDescriptor,
    CapabilityDescriptor,
    DataSchemaDescriptor,
    DescriptorModelError,
    HostExtensionDescriptor,
    NodeDescriptor,
)
from vibeflow.node_config import NodeConfigError


_CONFIG_KEYS = (
    "nodes",
    "base_lib",
    "data_schemas",
    "capabilities",
    "host_extensions",
)
_MANIFEST_KINDS = {
    "nodes": "node",
    "base_lib": "base_lib",
    "data_schemas": "data_schema",
    "capabilities": "capability",
    "host_extensions": "host_extension",
}


@dataclass(frozen=True)
class DescriptorLoadError(ValueError):
    code: str
    message: str
    path: str = ""
    field: str = ""

    def __str__(self) -> str:
        location = self.path
        if self.field:
            location = f"{location}:{self.field}" if location else self.field
        return f"{self.code}: {self.message}" + (
            f" ({location})" if location else ""
        )


def load_project_descriptor_catalogs(
    project_root: Path,
    *,
    project_config: Path | None = None,
) -> DescriptorCatalogs:
    """Load catalogs from the ``descriptors`` section of project config."""

    root = _project_root(project_root)
    config_path = _safe_project_file(
        root,
        project_config or Path("vibeflow_project.jsonc"),
        label="project config",
        require_exists=True,
    )
    try:
        document = load_raw_config_document(config_path)
    except ConfigLoadError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.PROJECT_CONFIG",
            message=str(exc),
            path=str(config_path),
        ) from exc
    raw = document.data.get("descriptors", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise DescriptorLoadError(
            code="DESCRIPTOR.CONFIG.SHAPE",
            message="project descriptors must be an object",
            path=str(config_path),
            field="descriptors",
        )
    return load_descriptor_catalogs(root, raw)


def load_descriptor_catalogs(
    project_root: Path,
    descriptor_paths: Mapping[str, object],
) -> DescriptorCatalogs:
    """Recursively load one JSONC descriptor per file.

    Scan order is stable: descriptor category order is fixed, configured
    directories retain their declared order, and files are sorted by their
    project-relative POSIX path.
    """

    root = _project_root(project_root)
    if not isinstance(descriptor_paths, Mapping):
        raise DescriptorLoadError(
            code="DESCRIPTOR.CONFIG.SHAPE",
            message="descriptor paths must be an object",
            path=str(root),
        )
    unknown = sorted(
        str(key) for key in descriptor_paths if str(key) not in _CONFIG_KEYS
    )
    if unknown:
        raise DescriptorLoadError(
            code="DESCRIPTOR.CONFIG.UNKNOWN_FIELD",
            message=f"unknown descriptor path groups: {unknown}",
            path=str(root),
        )

    nodes = NodeCatalog()
    base_libs = BaseLibCatalog()
    schemas = SchemaRegistry()
    capabilities = CapabilityCatalog()
    host_extensions = HostExtensionCatalog()
    catalogs = {
        "nodes": nodes,
        "base_lib": base_libs,
        "data_schemas": schemas,
        "capabilities": capabilities,
        "host_extensions": host_extensions,
    }
    parsed_files: set[Path] = set()
    source_files: list[Path] = []

    for config_key in _CONFIG_KEYS:
        entries = _directory_entries(
            descriptor_paths.get(config_key, ()),
            root=root,
            field=f"descriptors.{config_key}",
        )
        for entry in entries:
            directory = _safe_descriptor_directory(root, entry)
            for manifest_path in _manifest_files(root, directory):
                if manifest_path in parsed_files:
                    raise DescriptorLoadError(
                        code="DESCRIPTOR.FILE.DUPLICATE_SCAN",
                        message=(
                            "descriptor file is included by more than one "
                            f"configured directory: {manifest_path}"
                        ),
                        path=str(manifest_path),
                    )
                parsed_files.add(manifest_path)
                descriptor = _load_manifest(
                    manifest_path,
                    expected_kind=_MANIFEST_KINDS[config_key],
                    project_root=root,
                )
                try:
                    catalogs[config_key].register(
                        descriptor,
                        source=manifest_path,
                    )
                except DescriptorCatalogError as exc:
                    raise DescriptorLoadError(
                        code=exc.code,
                        message=exc.message,
                        path=exc.source,
                        field=(
                            f"previous_source={exc.previous_source}"
                            if exc.previous_source
                            else ""
                        ),
                    ) from exc
                source_files.append(manifest_path)

    return DescriptorCatalogs(
        nodes=nodes,
        base_libs=base_libs,
        schemas=schemas,
        capabilities=capabilities,
        host_extensions=host_extensions,
        source_files=tuple(source_files),
    )


def parse_descriptor_manifest(
    data: Mapping[str, Any],
    *,
    expected_kind: str | None = None,
) -> (
    NodeDescriptor
    | BaseLibDescriptor
    | DataSchemaDescriptor
    | CapabilityDescriptor
    | HostExtensionDescriptor
):
    """Parse one already-decoded manifest object."""

    return _parse_descriptor_manifest(data, expected_kind=expected_kind)


def _load_manifest(
    path: Path,
    *,
    expected_kind: str,
    project_root: Path,
) -> (
    NodeDescriptor
    | BaseLibDescriptor
    | DataSchemaDescriptor
    | CapabilityDescriptor
    | HostExtensionDescriptor
):
    try:
        document = load_raw_config_document(path)
        descriptor = parse_descriptor_manifest(
            document.data,
            expected_kind=expected_kind,
        )
        _validate_source_locators(descriptor, root=project_root, path=path)
        return descriptor
    except ConfigLoadError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.JSONC",
            message=str(exc),
            path=str(path),
        ) from exc
    except (DescriptorModelError, NodeConfigError) as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.INVALID",
            message=str(exc),
            path=str(path),
        ) from exc


def _directory_entries(
    value: object,
    *,
    root: Path,
    field: str,
) -> tuple[Path, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise DescriptorLoadError(
            code="DESCRIPTOR.CONFIG.PATHS",
            message=f"{field} must be a list of project-relative directories",
            path=str(root),
            field=field,
        )
    entries: list[Path] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise DescriptorLoadError(
                code="DESCRIPTOR.CONFIG.PATH",
                message=f"{field}[{index}] must be a non-empty string",
                path=str(root),
                field=f"{field}[{index}]",
            )
        entries.append(Path(item))
    return tuple(entries)


def _project_root(project_root: Path) -> Path:
    raw = Path(project_root)
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.PROJECT_ROOT",
            message=str(exc),
            path=str(raw),
        ) from exc
    if not root.is_dir():
        raise DescriptorLoadError(
            code="DESCRIPTOR.PROJECT_ROOT",
            message="project root must be a directory",
            path=str(root),
        )
    return root


def _safe_descriptor_directory(root: Path, relative: Path) -> Path:
    if _looks_absolute(relative):
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.ABSOLUTE",
            message="descriptor directory must be project-relative",
            path=str(relative),
        )
    candidate = root / relative
    _reject_symlink_components(root, candidate)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.MISSING",
            message=str(exc),
            path=str(candidate),
        ) from exc
    _assert_within_root(root, resolved, path=candidate)
    if not resolved.is_dir():
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.NOT_DIRECTORY",
            message="configured descriptor path must be a directory",
            path=str(candidate),
        )
    return resolved


def _safe_project_file(
    root: Path,
    value: Path,
    *,
    label: str,
    require_exists: bool,
) -> Path:
    raw = Path(value)
    if _looks_absolute(raw):
        candidate = raw
    else:
        candidate = root / raw
    _reject_symlink_components(root, candidate)
    try:
        resolved = candidate.resolve(strict=require_exists)
    except OSError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.MISSING",
            message=str(exc),
            path=str(candidate),
        ) from exc
    _assert_within_root(root, resolved, path=candidate)
    if require_exists and not resolved.is_file():
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.NOT_FILE",
            message=f"{label} must be a file",
            path=str(candidate),
        )
    return resolved


def _manifest_files(root: Path, directory: Path) -> tuple[Path, ...]:
    paths = sorted(
        directory.rglob("*"),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    manifests: list[Path] = []
    for path in paths:
        if path.is_symlink():
            raise DescriptorLoadError(
                code="DESCRIPTOR.PATH.SYMLINK",
                message="symlinks are not allowed in descriptor directories",
                path=str(path),
            )
        resolved = path.resolve(strict=True)
        _assert_within_root(root, resolved, path=path)
        if resolved.is_file() and resolved.suffix.lower() == ".jsonc":
            manifests.append(resolved)
    return tuple(manifests)


def _validate_source_locators(
    descriptor: object,
    *,
    root: Path,
    path: Path,
) -> None:
    implementations = getattr(descriptor, "implementations", ())
    for implementation in implementations:
        source = implementation.source
        if source.kind != "file":
            continue
        raw = Path(source.ref)
        if _looks_absolute(raw):
            raise DescriptorLoadError(
                code="DESCRIPTOR.SOURCE.ABSOLUTE",
                message="file source refs must be project-relative",
                path=str(path),
                field=source.ref,
            )
        candidate = root / raw
        try:
            _reject_symlink_components(root, candidate)
            resolved = candidate.resolve(strict=False)
            _assert_within_root(root, resolved, path=candidate)
        except DescriptorLoadError as exc:
            raise DescriptorLoadError(
                code="DESCRIPTOR.SOURCE.UNSAFE",
                message=exc.message,
                path=str(path),
                field=source.ref,
            ) from exc
        if resolved.exists() and not resolved.is_file():
            raise DescriptorLoadError(
                code="DESCRIPTOR.SOURCE.NOT_FILE",
                message="file source ref must identify a regular file",
                path=str(path),
                field=source.ref,
            )


def _reject_symlink_components(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        resolved = candidate.resolve(strict=False)
        _assert_within_root(root, resolved, path=candidate)
        relative = resolved.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DescriptorLoadError(
                code="DESCRIPTOR.PATH.SYMLINK",
                message="symlinks are not allowed in descriptor paths",
                path=str(current),
            )


def _assert_within_root(root: Path, resolved: Path, *, path: Path) -> None:
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DescriptorLoadError(
            code="DESCRIPTOR.PATH.ESCAPE",
            message="descriptor path escapes the project root",
            path=str(path),
        ) from exc


def _looks_absolute(path: Path) -> bool:
    text = str(path)
    return path.is_absolute() or bool(PureWindowsPath(text).drive)
