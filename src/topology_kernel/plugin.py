from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


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

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.plugin_type,
            "priority": self.priority,
            "scope": self.scope,
            "source": self.source,
        }


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
        self._descriptors[id(plugin)] = PluginDescriptor(plugin_name, normalized_type, plugin_priority, scope, source)

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


def load_plugins_from_config(config: Mapping[str, Any], *, base_path: Path) -> tuple[PluginRegistry, tuple[object, ...]]:
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
            plugin = _load_plugin(spec, base_path=base_path)
            registry.register(
                plugin,
                plugin_type=str(spec.get("type", getattr(plugin, "plugin_type", "policy"))),
                name=str(spec.get("name", getattr(plugin, "name", plugin.__class__.__name__))),
                priority=int(spec.get("priority", getattr(plugin, "priority", 100))),
                scope=str(spec.get("scope", getattr(plugin, "scope", "project"))),
                source=str(spec.get("module", spec.get("path", "plugin"))),
                conflict=str(spec.get("conflict", "error")),
            )
        except Exception as exc:
            findings.append(_plugin_finding("PLUGIN.LOAD", f"plugin load failed: {exc}", object_id))
    return registry, tuple(findings)


def plugin_error(rule_id: str, message: str, object_id: str, *, details: Mapping[str, object] | None = None):
    return _plugin_finding(rule_id, message, object_id, details=details)


def _load_plugin(spec: Mapping[str, Any], *, base_path: Path) -> object:
    module_ref = str(spec.get("module", spec.get("path", ""))).strip()
    if not module_ref:
        raise ValueError("plugin module/path is required")
    class_name = str(spec.get("class", spec.get("factory", "Plugin"))).strip()
    module = _import_plugin_module(module_ref, base_path=base_path)
    target = getattr(module, class_name)
    plugin = target() if isinstance(target, type) or callable(target) else target
    if not plugin:
        raise ValueError(f"plugin factory returned empty value: {module_ref}.{class_name}")
    return plugin


def _import_plugin_module(module_ref: str, *, base_path: Path):
    candidate = (base_path / module_ref).resolve()
    if module_ref.endswith(".py") or candidate.exists():
        path = candidate if candidate.exists() else Path(module_ref).resolve()
        module_name = f"_topology_kernel_plugin_{abs(hash(path))}"
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
    from .health_types import HealthFinding

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
