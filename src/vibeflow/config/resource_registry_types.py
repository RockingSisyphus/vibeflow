from __future__ import annotations

from vibeflow.config.resources import BaseLibResource, PluginResource
from vibeflow.graph_config import STATUS_IMPLEMENTED


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


def _required_id(value: object, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return normalized
