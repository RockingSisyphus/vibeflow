"""Python resource metadata and registries.

These values bind Python modules and plugin classes to otherwise portable
resource identities. File discovery and configuration loading stay outside
the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vibeflow.core.flow import STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.targets.python.project.node import EFFECT_SCOPE_TRUSTED


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
            "effect_scope": EFFECT_SCOPE_TRUSTED,
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


class BaseLibRegistry:
    def __init__(self) -> None:
        self._resources: dict[str, BaseLibResource] = {}

    def register(
        self,
        id: str,
        *,
        module: str,
        display_name: str,
        description: str,
        category: str = "",
        version: str = "",
    ) -> None:
        resource_id = _required_id(id, "base_lib id")
        if resource_id in self._resources:
            raise ValueError(f"duplicate base_lib resource id: {resource_id}")
        self._resources[resource_id] = BaseLibResource(
            id=resource_id,
            module=_required_id(module, "base_lib module"),
            status=STATUS_IMPLEMENTED,
            display_name=str(display_name).strip(),
            category=str(category).strip(),
            description=str(description).strip(),
            version=str(version).strip(),
        )

    def get(self, id: str) -> BaseLibResource | None:
        return self._resources.get(str(id).strip())

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._resources))

    def resources(self) -> tuple[BaseLibResource, ...]:
        return tuple(self._resources[key] for key in self.available())


class PluginResourceRegistry:
    def __init__(self) -> None:
        self._resources: dict[str, PluginResource] = {}

    def register(
        self,
        id: str,
        *,
        module: str,
        class_name: str = "Plugin",
        plugin_type: str = "policy",
        display_name: str,
        description: str,
        category: str = "",
        version: str = "",
    ) -> None:
        resource_id = _required_id(id, "plugin id")
        if resource_id in self._resources:
            raise ValueError(f"duplicate plugin resource id: {resource_id}")
        self._resources[resource_id] = PluginResource(
            id=resource_id,
            name=resource_id,
            plugin_type=str(plugin_type).strip() or "policy",
            status=STATUS_IMPLEMENTED,
            module=_required_id(module, "plugin module"),
            class_name=str(class_name).strip() or "Plugin",
            display_name=str(display_name).strip(),
            category=str(category).strip(),
            description=str(description).strip(),
            version=str(version).strip(),
        )

    def get(self, id: str) -> PluginResource | None:
        return self._resources.get(str(id).strip())

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._resources))

    def resources(self) -> tuple[PluginResource, ...]:
        return tuple(self._resources[key] for key in self.available())


def normalize_plugin_config(spec: Mapping[str, Any]) -> dict[str, object]:
    raw = spec.get("config", spec.get("settings", {}))
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("plugin config/settings must be an object")
    return {str(key): value for key, value in raw.items()}


def plugin_status(spec: Mapping[str, Any]) -> str:
    status = (
        str(spec.get("status", STATUS_IMPLEMENTED)).strip()
        or STATUS_IMPLEMENTED
    )
    if status not in STATUSES:
        raise ValueError("plugin status must be implemented or planned")
    return status


def normalize_plugin_info(plugin: object, *, plugin_type: str) -> PluginInfo:
    raw = getattr(plugin, "PLUGIN_INFO", None)
    if raw is None:
        raw = getattr(plugin, "plugin_info", None)
    if raw is None:
        raw = plugin
    fallback = str(getattr(plugin, "name", plugin.__class__.__name__))
    if isinstance(raw, PluginInfo):
        info = raw
    else:
        info = PluginInfo(
            name=_field(raw, "name", fallback),
            plugin_type=_field(
                raw,
                "plugin_type",
                _field(raw, "type", plugin_type),
            ),
            display_name=_field(raw, "display_name"),
            category=_field(raw, "category"),
            description=_field(raw, "description"),
            version=_field(raw, "version"),
        )
    _require_info_fields(info.to_dict(), "PLUGIN_INFO")
    return info


def normalize_base_lib_info(
    raw: object,
    *,
    fallback_module: str,
) -> BaseLibInfo:
    """Normalize metadata exported by a Python base_lib module."""

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


def _required_id(value: object, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized


def _require_info_fields(payload: Mapping[str, object], label: str) -> None:
    missing = [
        key
        for key, value in payload.items()
        if key != "type" and not str(value).strip()
    ]
    if missing:
        raise ValueError(f"{label} missing required fields: {missing}")


def _field(raw: object, name: str, default: str = "") -> str:
    if isinstance(raw, Mapping):
        return str(raw.get(name, default)).strip()
    return str(getattr(raw, name, default)).strip()

__all__ = [
    "BaseLibInfo",
    "BaseLibRegistry",
    "BaseLibResource",
    "PluginInfo",
    "PluginResource",
    "PluginResourceRegistry",
    "normalize_base_lib_info",
    "normalize_plugin_config",
    "normalize_plugin_info",
    "plugin_status",
]
