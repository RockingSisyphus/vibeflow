"""JavaScript Target parsing and static binding for plugin descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from vibeflow.block_compiler import SourceRef
from vibeflow.core.descriptors import (
    DescriptorModelError,
    ImplementationDescriptor,
    PluginCatalog,
    PluginDescriptor,
    PluginResolution,
    PluginSelection,
    PluginSelectionError,
    ResolvedPluginSelection,
    SourceLocator,
    resolve_plugin_selections,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptPluginBinding,
)


PLUGIN_ERROR_CODES = {
    "PLUGIN.SELECTION.UNKNOWN": "VF_AOT_PLUGIN_UNKNOWN",
    "PLUGIN.SELECTION.DEPENDENCY": "VF_AOT_PLUGIN_UNKNOWN",
    "PLUGIN.SELECTION.TARGET": "VF_AOT_TARGET_IMPLEMENTATION_MISSING",
    "PLUGIN.SELECTION.CONTRACT": "VF_AOT_PLUGIN_CONFIG",
    "PLUGIN.SELECTION.CONFIG_SCHEMA": "VF_AOT_PLUGIN_CONFIG",
    "PLUGIN.SELECTION.TYPE": "VF_AOT_PLUGIN_KIND",
    "PLUGIN.SELECTION.CYCLE": "VF_AOT_PLUGIN_CYCLE",
    "PLUGIN.SELECTION.PLANNED_DEPENDENCY": (
        "VF_AOT_PLUGIN_PLANNED_DEPENDENCY"
    ),
}
PLUGIN_ABI_VERSION = "vibeflow.plugin.v1"


class JavascriptPluginError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        plugin_id: str = "",
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)
        self.message = str(message)
        self.plugin_id = str(plugin_id)
        self.details = dict(details or {})
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class JavascriptPluginBindingPlan:
    """Static Target binding split by lifecycle role and Planned status."""

    policy_plugins: tuple[JavascriptPluginBinding, ...] = ()
    compiler_plugins: tuple[JavascriptPluginBinding, ...] = ()
    runtime_plugins: tuple[JavascriptPluginBinding, ...] = ()
    planned_plugins: tuple[JavascriptPluginBinding, ...] = ()

    def __post_init__(self) -> None:
        groups = {
            "policy": tuple(self.policy_plugins),
            "compiler": tuple(self.compiler_plugins),
            "runtime": tuple(self.runtime_plugins),
        }
        active_ids: list[str] = []
        for plugin_type, bindings in groups.items():
            if not all(isinstance(item, JavascriptPluginBinding) for item in bindings):
                raise TypeError(f"{plugin_type}_plugins contains an invalid binding")
            if any(
                item.plugin_type != plugin_type or item.status != "implemented"
                for item in bindings
            ):
                raise ValueError(
                    f"{plugin_type}_plugins must contain active {plugin_type} bindings"
                )
            object.__setattr__(self, f"{plugin_type}_plugins", bindings)
            active_ids.extend(item.id for item in bindings)
        planned = tuple(self.planned_plugins)
        if not all(isinstance(item, JavascriptPluginBinding) for item in planned):
            raise TypeError("planned_plugins contains an invalid binding")
        if any(item.status != "planned" for item in planned):
            raise ValueError("planned_plugins must contain only planned bindings")
        all_ids = (*active_ids, *(item.id for item in planned))
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("JavaScript plugin binding ids must be unique")
        object.__setattr__(self, "planned_plugins", planned)

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": [item.to_dict() for item in self.policy_plugins],
            "compiler": [item.to_dict() for item in self.compiler_plugins],
            "runtime": [item.to_dict() for item in self.runtime_plugins],
            "planned": [item.to_dict() for item in self.planned_plugins],
        }


def parse_javascript_plugin_descriptor(
    data: Mapping[str, Any],
) -> PluginDescriptor:
    """Parse one decoded plugin manifest without reading or importing source."""

    if not isinstance(data, Mapping):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_DESCRIPTOR",
            "plugin descriptor must be an object",
        )
    _check_fields(
        data,
        {
            "kind",
            "id",
            "type",
            "targets",
            "implementations",
            "dependencies",
            "external_packages",
            "config",
            "priority",
            "display_name",
            "category",
            "description",
            "version",
        },
        field="plugin",
    )
    kind = _required_string(data.get("kind"), field="plugin.kind")
    if kind != "plugin":
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_KIND",
            "plugin.kind must be 'plugin'",
            str(data.get("id", "") or "").strip(),
        )
    plugin_id = _required_string(data.get("id"), field="plugin.id")
    config = _mapping(data.get("config", {}), field="plugin.config")
    _check_fields(
        config,
        {"schema", "defaults"},
        field="plugin.config",
    )
    priority = data.get("priority", 100)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            "plugin.priority must be an integer",
            plugin_id,
        )
    try:
        descriptor = PluginDescriptor(
            id=plugin_id,
            plugin_type=_required_string(data.get("type"), field="plugin.type"),
            targets=_string_tuple(data.get("targets"), field="plugin.targets"),
            implementations=_parse_implementations(
                data.get("implementations"),
                plugin_id=plugin_id,
            ),
            dependencies=_string_tuple(
                data.get("dependencies", ()),
                field="plugin.dependencies",
            ),
            external_packages=_string_tuple(
                data.get("external_packages", ()),
                field="plugin.external_packages",
            ),
            config_schema=_mapping(
                config.get("schema", {}),
                field="plugin.config.schema",
            ),
            config_defaults=_mapping(
                config.get("defaults", {}),
                field="plugin.config.defaults",
            ),
            priority=priority,
            display_name=_optional_string(data.get("display_name")),
            category=_optional_string(data.get("category")),
            description=_optional_string(data.get("description")),
            version=_optional_string(data.get("version")),
        )
    except JavascriptPluginError:
        raise
    except DescriptorModelError as exc:
        code = (
            "VF_AOT_CONTRACT_INVALID"
            if "target" in str(exc)
            else "VF_AOT_PLUGIN_CONFIG"
            if "config" in str(exc) or "priority" in str(exc)
            else "VF_AOT_PLUGIN_DESCRIPTOR"
        )
        raise JavascriptPluginError(code, str(exc), plugin_id) from exc
    _validate_javascript_descriptor(descriptor)
    return descriptor


def parse_javascript_plugin_selection(
    value: str | Mapping[str, Any],
) -> PluginSelection:
    """Parse one workflow plugin reference without resolving its source."""

    if isinstance(value, str):
        data: Mapping[str, Any] = {"id": value}
    elif isinstance(value, Mapping):
        data = value
    else:
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            "plugin selection must be a string id or object",
        )
    _check_fields(
        data,
        {
            "id",
            "status",
            "type",
            "targets",
            "dependencies",
            "config",
            "priority",
            "display_name",
            "description",
            "version",
        },
        field="plugin selection",
    )
    try:
        return PluginSelection(
            id=_required_string(data.get("id"), field="plugin selection.id"),
            status=str(data.get("status", "implemented")),
            plugin_type=str(data.get("type", "")),
            targets=_string_tuple(
                data.get("targets", ()),
                field="plugin selection.targets",
            ),
            dependencies=_string_tuple(
                data.get("dependencies", ()),
                field="plugin selection.dependencies",
            ),
            config=_mapping(
                data.get("config", {}),
                field="plugin selection.config",
            ),
            priority=data.get("priority"),
            display_name=_optional_string(data.get("display_name")),
            description=_optional_string(data.get("description")),
            version=_optional_string(data.get("version")),
        )
    except PluginSelectionError as exc:
        raise JavascriptPluginError(
            PLUGIN_ERROR_CODES.get(exc.code, "VF_AOT_PLUGIN_CONFIG"),
            exc.message,
            exc.plugin_id,
        ) from exc


def resolve_javascript_plugins(
    selections: Sequence[PluginSelection],
    *,
    catalog: PluginCatalog,
    target: str,
    entry_mode: str,
    project_root: Path | None = None,
    source_hashes: Mapping[str, str] | None = None,
) -> JavascriptPluginBindingPlan:
    """Resolve Core plugin declarations into static JS/TS factory bindings."""

    if entry_mode not in {"sync", "async"}:
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            "entry_mode must be sync or async",
        )
    try:
        resolution = resolve_plugin_selections(
            tuple(selections),
            catalog=catalog,
            target=target,
        )
    except PluginSelectionError as exc:
        raise JavascriptPluginError(
            PLUGIN_ERROR_CODES.get(exc.code, "VF_AOT_PLUGIN_CONFIG"),
            exc.message,
            exc.plugin_id,
        ) from exc
    return build_javascript_plugin_binding_plan(
        resolution,
        target=target,
        entry_mode=entry_mode,
        project_root=project_root,
        source_hashes=source_hashes,
    )


def build_javascript_plugin_binding_plan(
    resolution: PluginResolution,
    *,
    target: str,
    entry_mode: str,
    project_root: Path | None = None,
    source_hashes: Mapping[str, str] | None = None,
) -> JavascriptPluginBindingPlan:
    if not isinstance(resolution, PluginResolution):
        raise TypeError("resolution must be a PluginResolution")
    hashes = source_hashes or {}
    active = tuple(
        _binding_from_resolved(
            item,
            target=target,
            entry_mode=entry_mode,
            project_root=project_root,
            source_hash=str(hashes.get(item.id, "")),
        )
        for item in resolution.active
    )
    planned = tuple(
        _binding_from_resolved(
            item,
            target=target,
            entry_mode=entry_mode,
            project_root=None,
            source_hash="",
        )
        for item in resolution.planned
    )
    return JavascriptPluginBindingPlan(
        policy_plugins=tuple(
            item for item in active if item.plugin_type == "policy"
        ),
        compiler_plugins=tuple(
            item for item in active if item.plugin_type == "compiler"
        ),
        runtime_plugins=tuple(
            item for item in active if item.plugin_type == "runtime"
        ),
        planned_plugins=planned,
    )


def _binding_from_resolved(
    resolved: ResolvedPluginSelection,
    *,
    target: str,
    entry_mode: str,
    project_root: Path | None,
    source_hash: str,
) -> JavascriptPluginBinding:
    implementation = resolved.implementation
    if resolved.status == "planned":
        return JavascriptPluginBinding(
            id=resolved.id,
            plugin_type=resolved.plugin_type,
            status="planned",
            target=target,
            implementation=None,
            config=resolved.config,
            priority=resolved.priority,
            dependencies=resolved.dependencies,
        )
    assert implementation is not None
    if implementation.language not in {"javascript", "typescript"}:
        raise JavascriptPluginError(
            "VF_AOT_TARGET_IMPLEMENTATION_MISSING",
            f"plugin '{resolved.id}' has no JavaScript implementation for '{target}'",
            resolved.id,
        )
    if resolved.plugin_type in {"policy", "compiler"} and (
        implementation.completion != "immediate"
    ):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_FACTORY",
            f"{resolved.plugin_type} plugin '{resolved.id}' factory must be immediate",
            resolved.id,
        )
    if entry_mode == "sync" and implementation.completion == "suspend":
        raise JavascriptPluginError(
            "VF_ENTRY_MODE_PLUGIN_SUSPEND_IN_SYNC",
            f"sync workflow cannot use suspending plugin '{resolved.id}'",
            resolved.id,
        )
    source = implementation.source
    if not source.export:
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_FACTORY",
            f"plugin '{resolved.id}' implementation source.export is required",
            resolved.id,
        )
    source_ref = _javascript_source_ref(
        source,
        plugin_id=resolved.id,
        project_root=project_root,
    )
    return JavascriptPluginBinding(
        id=resolved.id,
        plugin_type=resolved.plugin_type,
        status="implemented",
        target=target,
        implementation=source_ref,
        config=resolved.config,
        completion=implementation.completion,
        priority=resolved.priority,
        dependencies=resolved.dependencies,
        external_packages=(
            resolved.descriptor.external_packages
            if resolved.descriptor is not None
            else ()
        ),
        language=implementation.language,
        source_hash=source_hash,
    )


def _parse_implementations(
    value: object,
    *,
    plugin_id: str,
) -> tuple[ImplementationDescriptor, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_DESCRIPTOR",
            "plugin.implementations must be a list",
            plugin_id,
        )
    implementations: list[ImplementationDescriptor] = []
    for index, raw in enumerate(value):
        field = f"plugin.implementations[{index}]"
        item = _mapping(raw, field=field)
        _check_fields(
            item,
            {"language", "targets", "source", "completion"},
            field=field,
        )
        source = _mapping(item.get("source"), field=f"{field}.source")
        _check_fields(
            source,
            {"kind", "ref", "export"},
            field=f"{field}.source",
        )
        default_export = "createPlugin"
        try:
            implementations.append(
                ImplementationDescriptor(
                    language=_required_string(
                        item.get("language"),
                        field=f"{field}.language",
                    ),
                    targets=_string_tuple(
                        item.get("targets"),
                        field=f"{field}.targets",
                    ),
                    source=SourceLocator(
                        kind=_required_string(
                            source.get("kind"),
                            field=f"{field}.source.kind",
                        ),
                        ref=_required_string(
                            source.get("ref"),
                            field=f"{field}.source.ref",
                        ),
                        export=(
                            _optional_string(source.get("export"))
                            or default_export
                        ),
                    ),
                    completion=str(item.get("completion", "immediate")),
                )
            )
        except DescriptorModelError as exc:
            raise JavascriptPluginError(
                "VF_AOT_PLUGIN_DESCRIPTOR",
                str(exc),
                plugin_id,
            ) from exc
    return tuple(implementations)


def _validate_javascript_descriptor(descriptor: PluginDescriptor) -> None:
    for implementation in descriptor.implementations:
        if implementation.language == "python":
            continue
        if descriptor.plugin_type in {"policy", "compiler"} and (
            implementation.completion != "immediate"
        ):
            raise JavascriptPluginError(
                "VF_AOT_PLUGIN_FACTORY",
                f"{descriptor.plugin_type} plugin factory must be immediate",
                descriptor.id,
            )


def _javascript_source_ref(
    source: SourceLocator,
    *,
    plugin_id: str,
    project_root: Path | None,
) -> SourceRef:
    ref = source.ref
    if source.kind == "file" and project_root is None:
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_SOURCE",
            f"plugin '{plugin_id}' file source requires project_root",
            plugin_id,
        )
    if source.kind == "file":
        assert project_root is not None
        root = Path(project_root).resolve()
        candidate = Path(ref)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (root / candidate).resolve()
        )
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise JavascriptPluginError(
                "VF_AOT_PLUGIN_SOURCE",
                f"plugin '{plugin_id}' source escapes project root: {ref}",
                plugin_id,
            ) from exc
        ref = str(resolved)
    return SourceRef(kind=source.kind, ref=ref, export=source.export or "")


def _check_fields(
    value: Mapping[str, Any],
    allowed: set[str],
    *,
    field: str,
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            f"{field} contains unknown fields: {unknown}",
        )


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            f"{field} must be a non-empty string",
        )
    return value.strip()


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            "optional plugin metadata must be strings",
        )
    return value.strip()


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            f"{field} must be a list of strings",
        )
    values = tuple(_required_string(item, field=field) for item in value)
    if len(set(values)) != len(values):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            f"{field} contains duplicate values",
        )
    return values


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise JavascriptPluginError(
            "VF_AOT_PLUGIN_CONFIG",
            f"{field} must be an object",
        )
    return value


__all__ = [
    "PLUGIN_ABI_VERSION",
    "JavascriptPluginBindingPlan",
    "JavascriptPluginError",
    "build_javascript_plugin_binding_plan",
    "parse_javascript_plugin_descriptor",
    "parse_javascript_plugin_selection",
    "resolve_javascript_plugins",
]
