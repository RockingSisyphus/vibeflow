from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

from .graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from .health_types import HealthFinding


STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PLANNED})


@dataclass(frozen=True)
class BaseLibInfo:
    module: str
    display_name: str
    category: str
    description: str
    version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
        }


@dataclass(frozen=True)
class PluginInfo:
    name: str
    plugin_type: str
    display_name: str
    category: str
    description: str
    version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.plugin_type,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
        }


@dataclass(frozen=True)
class BaseLibResource:
    module: str
    status: str = STATUS_IMPLEMENTED
    description: str = ""
    info: BaseLibInfo | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "module": self.module,
            "status": self.status,
            "description": self.description,
        }
        if self.info is not None:
            payload["info"] = self.info.to_dict()
        return payload


@dataclass(frozen=True)
class PluginResource:
    name: str
    plugin_type: str = "policy"
    status: str = STATUS_IMPLEMENTED
    module: str = ""
    class_name: str = "Plugin"
    description: str = ""
    config_keys: tuple[str, ...] = ()
    info: PluginInfo | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "type": self.plugin_type,
            "status": self.status,
            "module": self.module,
            "class": self.class_name,
            "description": self.description,
            "config_keys": list(self.config_keys),
        }
        if self.info is not None:
            payload["info"] = self.info.to_dict()
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
        return {
            "global_config": dict(self.global_config),
            "base_lib": {
                "paths": list(self.base_lib_paths),
                "modules": [item.to_dict() for item in self.base_libs],
            },
            "plugins": [item.to_dict() for item in self.plugins],
        }


def load_config_resources(
    config: Mapping[str, Any],
    *,
    base_path: Path,
    plugin_registry: object | None = None,
) -> tuple[ConfigResources, tuple[HealthFinding, ...]]:
    findings: list[HealthFinding] = []
    global_config = _global_config(config, findings)
    base_lib_paths, base_libs = _base_lib_resources(config, base_path=base_path, findings=findings)
    plugins = _plugin_resources(config, plugin_registry=plugin_registry, findings=findings)
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
            module = str(item.get("module", item.get("name", ""))).strip()
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
) -> tuple[tuple[str, ...], list[BaseLibResource]]:
    raw = config.get("base_lib")
    if raw in (None, {}):
        return (), []
    if not isinstance(raw, Mapping):
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB", "base_lib must be an object", "base_lib", "base_lib"))
        return (), []
    paths = tuple(_resolve_paths(_string_list(raw.get("paths", ())), base_path=base_path))
    modules = raw.get("modules", ())
    if modules in (None, ()):
        return paths, []
    if not isinstance(modules, list):
        findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULES", "base_lib.modules must be a list", "base_lib.modules", "base_lib"))
        return paths, []

    resources: list[BaseLibResource] = []
    for index, item in enumerate(modules):
        prefix = f"base_lib.modules[{index}]"
        spec = _base_lib_spec(item, prefix=prefix, findings=findings)
        if spec is None:
            continue
        module, status, description = spec
        info = None
        if status == STATUS_IMPLEMENTED:
            info = _load_base_lib_info(module, paths=paths, findings=findings, object_id=prefix)
            if info is not None:
                description = description or info.description
        resources.append(BaseLibResource(module=module, status=status, description=description, info=info))
    return paths, resources


def _base_lib_spec(item: object, *, prefix: str, findings: list[HealthFinding]) -> tuple[str, str, str] | None:
    if isinstance(item, str):
        module = item.strip()
        if not module:
            findings.append(_finding("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix} must be a non-empty module string", prefix, "base_lib"))
            return None
        return module, STATUS_IMPLEMENTED, ""
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
    return module, status, str(item.get("description", "")).strip()


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


def _plugin_resources(
    config: Mapping[str, Any],
    *,
    plugin_registry: object | None,
    findings: list[HealthFinding],
) -> list[PluginResource]:
    raw = config.get("plugins", [])
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        findings.append(_finding("CONFIG.SCHEMA.PLUGINS_LIST", "plugins must be a list", "plugins", "plugin"))
        return []

    registry_resources = {}
    if plugin_registry is not None and callable(getattr(plugin_registry, "resource_map", None)):
        registry_resources = plugin_registry.resource_map()

    resources: list[PluginResource] = []
    for index, item in enumerate(raw):
        prefix = f"plugins[{index}]"
        if isinstance(item, str):
            spec: dict[str, object] = {"module": item}
        elif isinstance(item, Mapping):
            spec = {str(key): value for key, value in item.items()}
        else:
            continue
        if spec.get("enabled", True) is False:
            continue
        status = str(spec.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
        if status not in STATUSES:
            status = STATUS_IMPLEMENTED
        module = str(spec.get("module", spec.get("path", ""))).strip()
        class_name = str(spec.get("class", spec.get("factory", "Plugin"))).strip() or "Plugin"
        plugin_type = str(spec.get("type", "policy")).strip() or "policy"
        try:
            config_keys = tuple(sorted(normalize_plugin_config(spec).keys())) if isinstance(spec, Mapping) else ()
        except ValueError as exc:
            findings.append(_finding("CONFIG.SCHEMA.PLUGIN_CONFIG", str(exc), f"{prefix}.config", "plugin"))
            config_keys = ()
        registered = registry_resources.get((module, class_name, plugin_type))
        if registered is not None:
            resources.append(registered)
            continue
        name = str(spec.get("name", "")).strip() or module or class_name
        resources.append(
            PluginResource(
                name=name,
                plugin_type=plugin_type,
                status=status,
                module=module,
                class_name=class_name,
                description=str(spec.get("description", "")).strip(),
                config_keys=config_keys,
            )
        )
    return resources


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


def _resolve_paths(values: tuple[str, ...], *, base_path: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            path = base_path / path
        paths.append(str(path.resolve()))
    return tuple(dict.fromkeys(paths))


@contextmanager
def _module_search_path(module_name: str, paths: tuple[str, ...]) -> Iterator[None]:
    first = module_name.split(".", 1)[0]
    additions: list[str] = []
    for value in paths:
        path = Path(value)
        candidate = path.parent if path.name == first else path
        additions.append(str(candidate.resolve()))
    for value in reversed(tuple(dict.fromkeys(additions))):
        if value not in sys.path:
            sys.path.insert(0, value)
    try:
        yield
    finally:
        for value in additions:
            try:
                sys.path.remove(value)
            except ValueError:
                pass


def _finding(rule_id: str, message: str, object_id: str, failure_layer: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=failure_layer,
        object_id=object_id,
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
    )
