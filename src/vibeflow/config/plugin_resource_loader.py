from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from vibeflow.config.resource_helpers import _finding
from vibeflow.config.resources import (
    PluginResource,
    PluginResourceRegistry,
    _append_legacy_resource_warning,
    _append_missing_resource_metadata_warnings,
    _resource_metadata,
    normalize_plugin_config,
)
from vibeflow.graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.health.types import HealthFinding


STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PLANNED})


def plugin_resources(config: Mapping[str, Any], *, plugin_registry: object | None, plugin_resource_registry: PluginResourceRegistry | None, findings: list[HealthFinding]) -> list[PluginResource]:
    raw = config.get("plugins", [])
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        findings.append(_finding("CONFIG.SCHEMA.PLUGINS_LIST", "plugins must be a list", "plugins", "plugin"))
        return []
    registry_resources = plugin_registry.resource_map() if plugin_registry is not None and callable(getattr(plugin_registry, "resource_map", None)) else {}
    resources: list[PluginResource] = []
    for index, item in enumerate(raw):
        spec = _plugin_spec(item)
        if spec is None or spec.get("enabled", True) is False:
            continue
        prefix = f"plugins[{index}]"
        registered_resource = _registered_plugin_resource(spec, item, registry=plugin_resource_registry, prefix=prefix, findings=findings)
        if registered_resource is not None:
            resources.append(replace(registered_resource, config_keys=_plugin_config_keys(spec, prefix, findings) or registered_resource.config_keys))
            continue
        module = str(spec.get("module", spec.get("path", ""))).strip()
        class_name = str(spec.get("class", spec.get("factory", "Plugin"))).strip() or "Plugin"
        plugin_type = str(spec.get("type", "policy")).strip() or "policy"
        registered = registry_resources.get((module, class_name, plugin_type))
        config_keys = _plugin_config_keys(spec, prefix, findings)
        if registered is not None:
            metadata = _resource_metadata(spec)
            _append_missing_resource_metadata_warnings(metadata, prefix, "plugin", findings)
            resources.append(replace(registered, display_name=metadata["display_name"], category=metadata["category"], description=metadata["description"], version=metadata["version"], config_keys=config_keys or registered.config_keys))
            continue
        if plugin_resource_registry is not None:
            _append_legacy_resource_warning(prefix, "plugin", findings)
        _append_missing_resource_metadata_warnings(_resource_metadata(spec), prefix, "plugin", findings)
        resources.append(_inline_plugin_resource(spec, module=module, class_name=class_name, plugin_type=plugin_type, config_keys=config_keys))
    return resources


def _plugin_spec(item: object) -> dict[str, object] | None:
    if isinstance(item, str):
        return {"module": item}
    if isinstance(item, Mapping):
        return {str(key): value for key, value in item.items()}
    return None


def _plugin_config_keys(spec: Mapping[str, object], prefix: str, findings: list[HealthFinding]) -> tuple[str, ...]:
    try:
        return tuple(sorted(normalize_plugin_config(spec).keys()))
    except ValueError as exc:
        findings.append(_finding("CONFIG.SCHEMA.PLUGIN_CONFIG", str(exc), f"{prefix}.config", "plugin"))
        return ()


def _registered_plugin_resource(spec: Mapping[str, object], item: object, *, registry: PluginResourceRegistry | None, prefix: str, findings: list[HealthFinding]) -> PluginResource | None:
    if registry is None:
        return None
    resource_id = item.strip() if isinstance(item, str) else str(spec.get("id", "")).strip() if "id" in spec and "module" not in spec and "path" not in spec else ""
    if not resource_id:
        return None
    registered = registry.get(resource_id)
    if registered is None:
        findings.append(_finding("CONFIG.RESOURCE.UNKNOWN_PLUGIN", f"unknown plugin resource id: {resource_id}", prefix, "plugin"))
        return None
    return _overlay_plugin_metadata(registered, spec)


def _overlay_plugin_metadata(resource: PluginResource, spec: Mapping[str, object]) -> PluginResource:
    metadata = _resource_metadata(spec)
    return replace(
        resource,
        name=str(spec.get("name", resource.name)).strip() or resource.name,
        plugin_type=str(spec.get("type", resource.plugin_type)).strip() or resource.plugin_type,
        class_name=str(spec.get("class", spec.get("factory", resource.class_name))).strip() or resource.class_name,
        display_name=metadata["display_name"] or resource.display_name,
        category=metadata["category"] or resource.category,
        description=metadata["description"] or resource.description,
        version=metadata["version"] or resource.version,
    )


def _inline_plugin_resource(spec: Mapping[str, object], *, module: str, class_name: str, plugin_type: str, config_keys: tuple[str, ...]) -> PluginResource:
    metadata = _resource_metadata(spec)
    status = str(spec.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
    return PluginResource(
        id=str(spec.get("id", "")).strip(),
        name=str(spec.get("name", "")).strip() or module or class_name,
        plugin_type=plugin_type,
        status=status if status in STATUSES else STATUS_IMPLEMENTED,
        module=module,
        class_name=class_name,
        display_name=metadata["display_name"],
        category=metadata["category"],
        description=metadata["description"],
        version=metadata["version"],
        config_keys=config_keys,
    )
