from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator, Mapping

from vibeflow.graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.config.resource_helpers import _finding, _module_search_path, _resolve_paths
from vibeflow.health.types import HealthFinding


STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PLANNED})


@dataclass(frozen=True)
class BaseLibInfo:
    module: str
    display_name: str
    category: str
    description: str
    version: str

    def to_dict(self) -> dict[str, object]:
        return {"module": self.module, "display_name": self.display_name, "category": self.category, "description": self.description, "version": self.version}


@dataclass(frozen=True)
class PluginInfo:
    name: str
    plugin_type: str
    display_name: str
    category: str
    description: str
    version: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "type": self.plugin_type, "display_name": self.display_name, "category": self.category, "description": self.description, "version": self.version}


@dataclass(frozen=True)
class BaseLibResource:
    module: str
    id: str = ""
    status: str = STATUS_IMPLEMENTED
    display_name: str = ""
    category: str = ""
    description: str = ""
    version: str = ""
    info: BaseLibInfo | None = None
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "module": self.module,
            "status": self.status,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
        }
        if self.info is not None:
            payload["info"] = self.info.to_dict()
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


@dataclass(frozen=True)
class PluginResource:
    name: str
    id: str = ""
    plugin_type: str = "policy"
    status: str = STATUS_IMPLEMENTED
    module: str = ""
    class_name: str = "Plugin"
    display_name: str = ""
    category: str = ""
    description: str = ""
    version: str = ""
    config_keys: tuple[str, ...] = ()
    info: PluginInfo | None = None
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "type": self.plugin_type,
            "status": self.status,
            "module": self.module,
            "class": self.class_name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "config_keys": list(self.config_keys),
        }
        if self.info is not None:
            payload["info"] = self.info.to_dict()
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


@dataclass(frozen=True)
class ConfigResources:
    global_config: Mapping[str, object] = field(default_factory=dict)
    base_lib_paths: tuple[str, ...] = ()
    base_libs: tuple[BaseLibResource, ...] = ()
    plugins: tuple[PluginResource, ...] = ()

    @property
    def implemented_base_lib_modules(self) -> tuple[str, ...]:
        return tuple(item.module for item in self.base_libs if item.status == STATUS_IMPLEMENTED and item.module)

    def to_dict(self) -> dict[str, object]:
        return {"global_config": dict(self.global_config), "base_lib": {"paths": list(self.base_lib_paths), "modules": [item.to_dict() for item in self.base_libs]}, "plugins": [item.to_dict() for item in self.plugins]}


from vibeflow.config.resource_registry_types import BaseLibRegistry, PluginResourceRegistry


def load_config_resources(
    config: Mapping[str, Any],
    *,
    base_path: Path,
    plugin_registry: object | None = None,
    base_lib_registry: BaseLibRegistry | None = None,
    plugin_resource_registry: PluginResourceRegistry | None = None,
    base_lib_paths: tuple[str, ...] = (),
) -> tuple[ConfigResources, tuple[HealthFinding, ...]]:
    findings: list[HealthFinding] = []
    global_config = _global_config(config, findings)
    base_lib_paths, base_libs = _base_lib_resources(
        config,
        base_path=base_path,
        findings=findings,
        base_lib_registry=base_lib_registry,
        default_paths=base_lib_paths,
    )
    from vibeflow.config.plugin_resource_loader import plugin_resources

    plugins = plugin_resources(config, plugin_registry=plugin_registry, plugin_resource_registry=plugin_resource_registry, findings=findings)
    return (
        ConfigResources(
            global_config=global_config,
            base_lib_paths=base_lib_paths,
            base_libs=tuple(base_libs),
            plugins=tuple(plugins),
        ),
        tuple(findings),
    )


def config_base_lib_policy(config: Mapping[str, Any], *, base_path: Path) -> dict[str, tuple[str, ...]]:
    raw = config.get("base_lib")
    if not isinstance(raw, Mapping):
        return {}
    paths = _string_list(raw.get("paths", ()))
    modules = []
    for item in raw.get("modules", ()):
        if isinstance(item, str):
            modules.append(item)
            continue
        if isinstance(item, Mapping):
            status = str(item.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
            if status != STATUS_IMPLEMENTED:
                continue
            module = str(item.get("module", item.get("name", item.get("id", "")))).strip()
            if module:
                modules.append(module)
    return {
        "allowed_paths": tuple(_resolve_paths(paths, base_path=base_path)),
        "allowed_modules": tuple(dict.fromkeys(modules)),
    }


def normalize_plugin_config(spec: Mapping[str, Any]) -> dict[str, object]:
    raw = spec.get("config", spec.get("settings", {}))
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("plugin config/settings must be an object")
    return {str(key): value for key, value in raw.items()}


def plugin_status(spec: Mapping[str, Any]) -> str:
    status = str(spec.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
    if status not in STATUSES:
        raise ValueError("plugin status must be implemented or planned")
    return status


def normalize_plugin_info(plugin: object, *, plugin_type: str) -> PluginInfo:
    raw = getattr(plugin, "PLUGIN_INFO", None)
    if raw is None:
        raw = getattr(plugin, "plugin_info", None)
    if raw is None:
        raw = plugin
    return _normalize_plugin_info(raw, fallback_name=str(getattr(plugin, "name", plugin.__class__.__name__)), plugin_type=plugin_type)


def _global_config(config: Mapping[str, Any], findings: list[HealthFinding]) -> dict[str, object]:
    raw = config.get("global_config", {})
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        findings.append(_finding("CONFIG.SCHEMA.GLOBAL_CONFIG", "global_config must be an object", "global_config", "config"))
        return {}
    return {str(key): value for key, value in raw.items()}


def _base_lib_resources(
    config: Mapping[str, Any],
    *,
    base_path: Path,
    findings: list[HealthFinding],
    base_lib_registry: BaseLibRegistry | None,
    default_paths: tuple[str, ...],
) -> tuple[tuple[str, ...], list[BaseLibResource]]:
    raw = config.get("base_lib")
    if raw in (None, {}):
        return (), []
    if not isinstance(raw, Mapping):
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB", "base_lib must be an object", "base_lib", "base_lib"))
        return (), []
    explicit_paths = tuple(_resolve_paths(_string_list(raw.get("paths", ())), base_path=base_path))
    paths = explicit_paths or tuple(str(Path(path).resolve()) for path in default_paths) or (str(base_path.resolve()),)
    modules = raw.get("modules", ())
    if modules in (None, ()):
        return paths, []
    if not isinstance(modules, list):
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULES", "base_lib.modules must be a list", "base_lib.modules", "base_lib"))
        return paths, []

    resources: list[BaseLibResource] = []
    for index, item in enumerate(modules):
        prefix = f"base_lib.modules[{index}]"
        registered = _registered_base_lib_resource(item, registry=base_lib_registry, prefix=prefix, findings=findings)
        if registered is not None:
            info = _load_base_lib_info(registered.module, paths=paths, findings=findings, object_id=prefix)
            resources.append(replace(registered, status=STATUS_IMPLEMENTED, info=info))
            continue
        spec = _base_lib_spec(item, prefix=prefix, findings=findings)
        if spec is None:
            continue
        if base_lib_registry is not None:
            _append_legacy_resource_warning(prefix, "base_lib", findings)
        module, status, metadata = spec
        _append_missing_resource_metadata_warnings(metadata, prefix, "base_lib", findings)
        info = None
        if status == STATUS_IMPLEMENTED:
            info = _load_base_lib_info(module, paths=paths, findings=findings, object_id=prefix)
        resources.append(
            BaseLibResource(
                id=str(item.get("id", "")).strip() if isinstance(item, Mapping) else "",
                module=module,
                status=status,
                display_name=metadata["display_name"],
                category=metadata["category"],
                description=metadata["description"],
                version=metadata["version"],
                info=info,
            )
        )
    return paths, resources


def _base_lib_spec(item: object, *, prefix: str, findings: list[HealthFinding]) -> tuple[str, str, dict[str, str]] | None:
    if isinstance(item, str):
        module = item.strip()
        if not module:
            findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix} must be a non-empty module string", prefix, "base_lib"))
            return None
        return module, STATUS_IMPLEMENTED, _empty_resource_metadata()
    if not isinstance(item, Mapping):
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix} must be a string or object", prefix, "base_lib"))
        return None
    module = str(item.get("module", item.get("name", ""))).strip()
    if not module:
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix}.module or name must be a non-empty string", f"{prefix}.module", "base_lib"))
        return None
    status = str(item.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
    if status not in STATUSES:
        findings.append(_finding("CONFIG.SCHEMA.RESOURCE_STATUS", f"{prefix}.status must be implemented or planned", f"{prefix}.status", "base_lib"))
        status = STATUS_IMPLEMENTED
    return module, status, _resource_metadata(item)


def _registered_base_lib_resource(
    item: object,
    *,
    registry: BaseLibRegistry | None,
    prefix: str,
    findings: list[HealthFinding],
) -> BaseLibResource | None:
    if registry is None:
        return None
    resource_id = ""
    if isinstance(item, str):
        resource_id = item.strip()
    elif isinstance(item, Mapping) and "id" in item and "module" not in item and "name" not in item:
        resource_id = str(item.get("id", "")).strip()
    if not resource_id:
        return None
    registered = registry.get(resource_id)
    if registered is None:
        findings.append(_finding("CONFIG.RESOURCE.UNKNOWN_BASE_LIB", f"unknown base_lib resource id: {resource_id}", prefix, "base_lib"))
        return None
    return _overlay_base_lib_metadata(registered, item)


def _overlay_base_lib_metadata(resource: BaseLibResource, item: object) -> BaseLibResource:
    if not isinstance(item, Mapping):
        return resource
    metadata = _resource_metadata(item)
    return replace(
        resource,
        display_name=metadata["display_name"] or resource.display_name,
        category=metadata["category"] or resource.category,
        description=metadata["description"] or resource.description,
        version=metadata["version"] or resource.version,
    )


def _load_base_lib_info(
    module_name: str,
    *,
    paths: tuple[str, ...],
    findings: list[HealthFinding],
    object_id: str,
) -> BaseLibInfo | None:
    try:
        with _module_search_path(module_name, paths):
            module = importlib.import_module(module_name)
    except Exception as exc:
        findings.append(_finding("BASE_LIB.LOAD", f"base_lib load failed: {exc}", object_id, "base_lib"))
        return None
    raw = getattr(module, "BASE_LIB_INFO", None)
    if raw is None:
        findings.append(_finding("BASE_LIB.INFO.MISSING", f"implemented base_lib must define BASE_LIB_INFO: {module_name}", object_id, "base_lib"))
        return None
    try:
        return _normalize_base_lib_info(raw, fallback_module=module_name)
    except ValueError as exc:
        findings.append(_finding("BASE_LIB.INFO.INVALID", str(exc), object_id, "base_lib"))
        return None


def _empty_resource_metadata() -> dict[str, str]:
    return {"display_name": "", "category": "", "description": "", "version": ""}


def _resource_metadata(spec: Mapping[str, object]) -> dict[str, str]:
    return {
        "display_name": str(spec.get("display_name", "")).strip(),
        "category": str(spec.get("category", "")).strip(),
        "description": str(spec.get("description", "")).strip(),
        "version": str(spec.get("version", "")).strip(),
    }


def _append_missing_resource_metadata_warnings(
    metadata: Mapping[str, str],
    object_id: str,
    resource_kind: str,
    findings: list[HealthFinding],
) -> None:
    label = "plugin" if resource_kind == "plugin" else "base_lib"
    for field, rule_id in (
        ("display_name", f"CONFIG.SMELL.MISSING_{label.upper()}_DISPLAY_NAME"),
        ("description", f"CONFIG.SMELL.MISSING_{label.upper()}_DESCRIPTION"),
    ):
        if str(metadata.get(field, "")).strip():
            continue
        findings.append(
            HealthFinding(
                rule_id=rule_id,
                severity="warning",
                object_type=label,
                object_id=object_id,
                failure_layer=resource_kind,
                message=f"config {label} declaration '{object_id}' should declare {field} for readable SVG diagrams",
                suggested_fix_type="fix_config",
                details={"field": field, "resource_kind": label},
            )
        )


def _append_legacy_resource_warning(object_id: str, resource_kind: str, findings: list[HealthFinding]) -> None:
    label = "plugin" if resource_kind == "plugin" else "base_lib"
    findings.append(
        HealthFinding(
            rule_id="CONFIG.SMELL.LEGACY_INLINE_RESOURCE",
            severity="warning",
            object_type=label,
            object_id=object_id,
            failure_layer=resource_kind,
            message=f"inline {label} declarations are legacy in registry-backed configs; use an id registered in project/registry.py",
            suggested_fix_type="fix_config",
            details={"resource_kind": label},
        )
    )


def _normalize_base_lib_info(raw: object, *, fallback_module: str) -> BaseLibInfo:
    if isinstance(raw, BaseLibInfo):
        info = raw
    else:
        info = BaseLibInfo(
            module=_field(raw, "module", fallback_module),
            display_name=_field(raw, "display_name"),
            category=_field(raw, "category"),
            description=_field(raw, "description"),
            version=_field(raw, "version"),
        )
    _require_info_fields(info.to_dict(), "BASE_LIB_INFO")
    return info


def _normalize_plugin_info(raw: object, *, fallback_name: str, plugin_type: str) -> PluginInfo:
    if isinstance(raw, PluginInfo):
        info = raw
    else:
        info = PluginInfo(
            name=_field(raw, "name", fallback_name),
            plugin_type=_field(raw, "plugin_type", _field(raw, "type", plugin_type)),
            display_name=_field(raw, "display_name"),
            category=_field(raw, "category"),
            description=_field(raw, "description"),
            version=_field(raw, "version"),
        )
    _require_info_fields(info.to_dict(), "PLUGIN_INFO")
    return info


def _require_info_fields(payload: Mapping[str, object], label: str) -> None:
    missing = [key for key, value in payload.items() if key != "type" and not str(value).strip()]
    if missing:
        raise ValueError(f"{label} missing required fields: {missing}")


def _field(raw: object, name: str, default: str = "") -> str:
    if isinstance(raw, Mapping):
        return str(raw.get(name, default)).strip()
    return str(getattr(raw, name, default)).strip()


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())
