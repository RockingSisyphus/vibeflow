"""In-memory Python plugin protocols and registry semantics.

This module is the Python Target boundary for plugin objects.  It deliberately
does not discover configuration files, alter ``sys.path`` or import project
modules; those operations remain in the outer loading layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.node import EFFECT_SCOPE_TRUSTED
from vibeflow.targets.python.project.resources import PluginInfo, PluginResource


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
            "effect_scope": EFFECT_SCOPE_TRUSTED,
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


class PluginRegistry:
    """Register already-created Python plugins in deterministic hook order."""

    def __init__(self) -> None:
        self._plugins: dict[str, list[object]] = {
            "policy": [],
            "compiler": [],
            "runtime": [],
        }
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
        plugin_name = str(
            name or getattr(plugin, "name", plugin.__class__.__name__)
        ).strip()
        if not plugin_name:
            raise ValueError("plugin name cannot be empty")
        plugin_priority = int(
            priority if priority is not None else getattr(plugin, "priority", 100)
        )
        if conflict not in {"error", "replace"}:
            raise ValueError("plugin conflict must be error or replace")
        existing = [
            item
            for item in self._plugins[normalized_type]
            if _plugin_name(item) == plugin_name
        ]
        if existing and conflict == "error":
            raise ValueError(f"duplicate {normalized_type} plugin: {plugin_name}")
        if existing and conflict == "replace":
            self._plugins[normalized_type] = [
                item
                for item in self._plugins[normalized_type]
                if _plugin_name(item) != plugin_name
            ]
        setattr(plugin, "name", plugin_name)
        setattr(plugin, "priority", plugin_priority)
        setattr(plugin, "scope", scope)
        self._plugins[normalized_type].append(plugin)
        self._plugins[normalized_type].sort(
            key=lambda item: (
                int(getattr(item, "priority", 100)),
                _plugin_name(item),
            )
        )
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
        return {
            "plugins": [descriptor.to_dict() for descriptor in self.descriptors()]
        }

    def resource_map(self) -> dict[tuple[str, str, str], PluginResource]:
        resources: dict[tuple[str, str, str], PluginResource] = {}
        for descriptor in self.descriptors():
            key = (
                descriptor.source,
                descriptor.class_name,
                descriptor.plugin_type,
            )
            resources[key] = PluginResource(
                name=descriptor.name,
                id=descriptor.name,
                plugin_type=descriptor.plugin_type,
                status="implemented",
                module=descriptor.source,
                class_name=descriptor.class_name,
                description=(
                    descriptor.info.description
                    if descriptor.info is not None
                    else ""
                ),
                config_keys=descriptor.config_keys,
                info=descriptor.info,
                root_id=descriptor.root_id,
                root_path=descriptor.root_path,
                source_path=descriptor.source_path,
            )
        return resources


def plugin_error(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    details: Mapping[str, object] | None = None,
) -> HealthFinding:
    fields: dict[str, object] = {
        "rule_id": rule_id,
        "severity": "error",
        "object_type": "plugin",
        "object_id": object_id,
        "failure_layer": "plugin",
        "message": message,
        "suggested_fix_type": "fix_plugin",
        "details": dict(details or {}),
    }
    return HealthFinding(**fields)


def _plugin_name(plugin: object) -> str:
    return str(getattr(plugin, "name", plugin.__class__.__name__))


def _normalize_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized == "boundary":
        raise ValueError("boundary plugins are removed; use runtime plugins")
    if normalized not in {"policy", "compiler", "runtime"}:
        raise ValueError(f"unknown plugin type: {value}")
    return normalized

__all__ = [
    "CompilerPlugin",
    "PluginDescriptor",
    "PluginRegistry",
    "PolicyPlugin",
    "RuntimePlugin",
    "plugin_error",
]
