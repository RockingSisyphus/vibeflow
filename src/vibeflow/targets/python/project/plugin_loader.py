from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Mapping

from vibeflow.targets.python.project.resources import (
    PluginInfo,
    PluginResourceRegistry,
    normalize_plugin_config,
    normalize_plugin_info,
    plugin_status,
)
from vibeflow.targets.python.project.plugins import (
    CompilerPlugin,
    PluginDescriptor,
    PluginRegistry,
    PolicyPlugin,
    RuntimePlugin,
    plugin_error,
)


def load_plugins_from_config(
    config: Mapping[str, Any],
    *,
    base_path: Path,
    root_id: str = "",
    root_path: str = "",
    source_path: str = "",
    plugin_resource_registry: PluginResourceRegistry | None = None,
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
        resolved = _resolve_registered_plugin_spec(spec, item, registry=plugin_resource_registry, object_id=object_id, findings=findings)
        if resolved is None:
            if plugin_resource_registry is not None and _looks_like_plugin_id_reference(spec, item):
                continue
        else:
            spec = resolved
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


def _resolve_registered_plugin_spec(
    spec: Mapping[str, Any],
    item: object,
    *,
    registry: PluginResourceRegistry | None,
    object_id: str,
    findings: list[object],
) -> dict[str, object] | None:
    if registry is None or not _looks_like_plugin_id_reference(spec, item):
        return None
    resource_id = item.strip() if isinstance(item, str) else str(spec.get("id", "")).strip()
    registered = registry.get(resource_id)
    if registered is None:
        findings.append(_plugin_finding("PLUGIN.CONFIG.UNKNOWN_RESOURCE", f"unknown plugin resource id: {resource_id}", object_id))
        return None
    resolved: dict[str, object] = dict(spec)
    resolved.setdefault("name", registered.name)
    resolved.setdefault("type", registered.plugin_type)
    resolved.setdefault("module", registered.module)
    resolved.setdefault("class", registered.class_name)
    resolved.setdefault("display_name", registered.display_name)
    resolved.setdefault("description", registered.description)
    resolved.setdefault("category", registered.category)
    resolved.setdefault("version", registered.version)
    return resolved


def _looks_like_plugin_id_reference(spec: Mapping[str, Any], item: object) -> bool:
    if isinstance(item, str):
        return True
    return "id" in spec and "module" not in spec and "path" not in spec


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
    base = str(base_path.resolve())
    inserted = base not in sys.path
    if inserted:
        sys.path.insert(0, base)
    try:
        return importlib.import_module(module_ref)
    finally:
        if inserted:
            try:
                sys.path.remove(base)
            except ValueError:
                pass


def _plugin_finding(rule_id: str, message: str, object_id: str, *, details: Mapping[str, object] | None = None):
    return plugin_error(rule_id, message, object_id, details=details)

__all__ = ["load_plugins_from_config"]
