from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from vibeflow.config.resources import PluginInfo, PluginResource, normalize_plugin_config, normalize_plugin_info, plugin_status


class PolicyPlugin(Protocol):
    name: str
    priority: int


class CompilerPlugin(Protocol):
    name: str
    priority: int


class RuntimePlugin(Protocol):
    name: str
    priority: int


@dataclass(frozen=True)
class PluginDescriptor:
    name: str
    plugin_type: str
    priority: int
    scope: str
    source: str
    class_name: str = "Plugin"
    info: PluginInfo | None = None
    config_keys: tuple[str, ...] = ()
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = {
            "name": self.name,
            "type": self.plugin_type,
            "priority": self.priority,
            "scope": self.scope,
            "source": self.source,
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, list[object]] = {"policy": [], "compiler": [], "runtime": []}
        self._descriptors: dict[int, PluginDescriptor] = {}

    def register(
        self,
        plugin: object,
        *,
        plugin_type: str = "policy",
        name: str | None = None,
        priority: int | None = None,
        scope: str = "project",
        source: str = "manual",
        class_name: str = "Plugin",
        info: PluginInfo | None = None,
        config_keys: tuple[str, ...] = (),
        root_id: str = "",
        root_path: str = "",
        source_path: str = "",
        conflict: str = "error",
    ) -> None:
        normalized_type = _normalize_type(plugin_type)
        plugin_name = str(name or getattr(plugin, "name", plugin.__class__.__name__)).strip()
        if not plugin_name:
            raise ValueError("plugin name cannot be empty")
        plugin_priority = int(priority if priority is not None else getattr(plugin, "priority", 100))
        if conflict not in {"error", "replace"}:
            raise ValueError("plugin conflict must be error or replace")
        existing = [item for item in self._plugins[normalized_type] if _plugin_name(item) == plugin_name]
        if existing and conflict == "error":
            raise ValueError(f"duplicate {normalized_type} plugin: {plugin_name}")
        if existing and conflict == "replace":
            self._plugins[normalized_type] = [item for item in self._plugins[normalized_type] if _plugin_name(item) != plugin_name]
        setattr(plugin, "name", plugin_name)
        setattr(plugin, "priority", plugin_priority)
        setattr(plugin, "scope", scope)
        self._plugins[normalized_type].append(plugin)
        self._plugins[normalized_type].sort(key=lambda item: (int(getattr(item, "priority", 100)), _plugin_name(item)))
        self._descriptors[id(plugin)] = PluginDescriptor(
            plugin_name,
            normalized_type,
            plugin_priority,
            scope,
            source,
            class_name,
            info,
            tuple(config_keys),
            root_id,
            root_path,
            source_path,
        )

    def policy_plugins(self) -> tuple[object, ...]:
        return tuple(self._plugins["policy"])

    def compiler_plugins(self) -> tuple[object, ...]:
        return tuple(self._plugins["compiler"])

    def runtime_plugins(self) -> tuple[object, ...]:
        return tuple(self._plugins["runtime"])

    def descriptors(self) -> tuple[PluginDescriptor, ...]:
        ordered: list[PluginDescriptor] = []
        for plugin_type in ("policy", "compiler", "runtime"):
            for plugin in self._plugins[plugin_type]:
                ordered.append(self._descriptors[id(plugin)])
        return tuple(ordered)

    def to_dict(self) -> dict[str, object]:
        return {"plugins": [descriptor.to_dict() for descriptor in self.descriptors()]}

    def resource_map(self) -> dict[tuple[str, str, str], PluginResource]:
        resources: dict[tuple[str, str, str], PluginResource] = {}
        for descriptor in self.descriptors():
            key = (descriptor.source, descriptor.class_name, descriptor.plugin_type)
            resources[key] = PluginResource(
                name=descriptor.name,
                plugin_type=descriptor.plugin_type,
                status="implemented",
                module=descriptor.source,
                class_name=descriptor.class_name,
                description=descriptor.info.description if descriptor.info is not None else "",
                config_keys=descriptor.config_keys,
                info=descriptor.info,
                root_id=descriptor.root_id,
                root_path=descriptor.root_path,
                source_path=descriptor.source_path,
            )
        return resources


def load_plugins_from_config(
    config: Mapping[str, Any],
    *,
    base_path: Path,
    root_id: str = "",
    root_path: str = "",
    source_path: str = "",
) -> tuple[PluginRegistry, tuple[object, ...]]:
    registry = PluginRegistry()
    findings: list[object] = []
    raw = config.get("plugins", [])
    if raw in (None, []):
        return registry, ()
    if not isinstance(raw, list):
        findings.append(_plugin_finding("PLUGIN.CONFIG.SCHEMA", "plugins must be a list", "plugins"))
        return registry, tuple(findings)
    for index, item in enumerate(raw):
        object_id = f"plugins[{index}]"
        if isinstance(item, str):
            spec = {"module": item}
        elif isinstance(item, Mapping):
            spec = dict(item)
        else:
            findings.append(_plugin_finding("PLUGIN.CONFIG.SCHEMA", f"{object_id} must be a string or object", object_id))
            continue
        if spec.get("enabled", True) is False:
            continue
        try:
            if plugin_status(spec) == "planned":
                continue
        except Exception as exc:
            findings.append(_plugin_finding("PLUGIN.CONFIG.SCHEMA", str(exc), object_id))
            continue
        try:
            plugin, info, config_keys = _load_plugin(spec, base_path=base_path)
            registry.register(
                plugin,
                plugin_type=str(spec.get("type", getattr(plugin, "plugin_type", "policy"))),
                name=str(spec.get("name", getattr(plugin, "name", plugin.__class__.__name__))),
                priority=int(spec.get("priority", getattr(plugin, "priority", 100))),
                scope=str(spec.get("scope", getattr(plugin, "scope", "project"))),
                source=str(spec.get("module", spec.get("path", "plugin"))),
                class_name=str(spec.get("class", spec.get("factory", "Plugin"))),
                info=info,
                config_keys=config_keys,
                root_id=root_id,
                root_path=root_path,
                source_path=source_path,
                conflict=str(spec.get("conflict", "error")),
            )
        except Exception as exc:
            findings.append(_plugin_finding("PLUGIN.LOAD", f"plugin load failed: {exc}", object_id))
    return registry, tuple(findings)


def plugin_error(rule_id: str, message: str, object_id: str, *, details: Mapping[str, object] | None = None):
    return _plugin_finding(rule_id, message, object_id, details=details)


def _load_plugin(spec: Mapping[str, Any], *, base_path: Path) -> tuple[object, PluginInfo, tuple[str, ...]]:
    module_ref = str(spec.get("module", spec.get("path", ""))).strip()
    if not module_ref:
        raise ValueError("plugin module/path is required")
    class_name = str(spec.get("class", spec.get("factory", "Plugin"))).strip()
    module = _import_plugin_module(module_ref, base_path=base_path)
    target = getattr(module, class_name)
    plugin = target() if isinstance(target, type) or callable(target) else target
    if not plugin:
        raise ValueError(f"plugin factory returned empty value: {module_ref}.{class_name}")
    plugin_config = normalize_plugin_config(spec)
    setattr(plugin, "config", dict(plugin_config))
    configure = getattr(plugin, "configure", None)
    if callable(configure):
        configure(dict(plugin_config))
    plugin_type = str(spec.get("type", getattr(plugin, "plugin_type", "policy")))
    if getattr(plugin, "PLUGIN_INFO", None) is None and getattr(module, "PLUGIN_INFO", None) is not None:
        setattr(plugin, "PLUGIN_INFO", getattr(module, "PLUGIN_INFO"))
    info = normalize_plugin_info(plugin, plugin_type=plugin_type)
    return plugin, info, tuple(sorted(plugin_config))


def _import_plugin_module(module_ref: str, *, base_path: Path):
    candidate = (base_path / module_ref).resolve()
    if module_ref.endswith(".py") or candidate.exists():
        path = Path(module_ref).resolve() if Path(module_ref).is_absolute() else candidate
        module_name = f"_vibeflow_plugin_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load plugin module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_ref)


def _plugin_name(plugin: object) -> str:
    return str(getattr(plugin, "name", plugin.__class__.__name__))


def _normalize_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized == "boundary":
        raise ValueError("boundary plugins are removed; use runtime plugins")
    if normalized not in {"policy", "compiler", "runtime"}:
        raise ValueError(f"unknown plugin type: {value}")
    return normalized


def _plugin_finding(rule_id: str, message: str, object_id: str, *, details: Mapping[str, object] | None = None):
    from vibeflow.health.types import HealthFinding

    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="plugin",
        object_id=object_id,
        failure_layer="plugin",
        message=message,
        suggested_fix_type="fix_plugin",
        details=dict(details or {}),
    )
