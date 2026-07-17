from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.config.resource_helpers import _finding
from vibeflow.config.resources import BaseLibRegistry, ConfigResources, PluginResourceRegistry
from vibeflow.health.types import HealthFinding


@dataclass(frozen=True)
class ConfigResourceRegistryContext:
    base_path: Path
    base_lib_registry: BaseLibRegistry | None = None
    plugin_resource_registry: PluginResourceRegistry | None = None
    base_lib_paths: tuple[str, ...] = ()
    available_resources: ConfigResources = field(default_factory=ConfigResources)
    findings: tuple[HealthFinding, ...] = ()


def discover_config_resource_registry_context(config: Mapping[str, Any], *, config_path: Path) -> ConfigResourceRegistryContext:
    if not _config_uses_resource_ids(config):
        return ConfigResourceRegistryContext(base_path=config_path.parent.resolve())
    registry_path = _find_registry_file(config_path.parent)
    if registry_path is None:
        return ConfigResourceRegistryContext(base_path=config_path.parent.resolve())
    findings: list[HealthFinding] = []
    base_registry: BaseLibRegistry | None = None
    plugin_registry: PluginResourceRegistry | None = None
    try:
        module = _import_resource_registry_file(registry_path)
    except Exception as exc:
        findings.append(_finding("CONFIG.RESOURCE.REGISTRY_IMPORT", f"resource registry import failed: {exc}", str(registry_path), "config"))
        return ConfigResourceRegistryContext(base_path=registry_path.parent.resolve(), findings=tuple(findings))
    base_registry = _call_optional_registry_factory(module, "build_base_lib_registry", BaseLibRegistry, "base_lib", findings)
    plugin_registry = _call_optional_registry_factory(module, "build_plugin_registry", PluginResourceRegistry, "plugin", findings)
    available = ConfigResources(
        base_lib_paths=(str(registry_path.parent.resolve()),),
        base_libs=tuple(replace(item, root_path=str(registry_path.parent.resolve()), source_path=str(registry_path)) for item in (base_registry.resources() if base_registry else ())),
        plugins=tuple(replace(item, root_path=str(registry_path.parent.resolve()), source_path=str(registry_path)) for item in (plugin_registry.resources() if plugin_registry else ())),
    )
    return ConfigResourceRegistryContext(
        base_path=registry_path.parent.resolve(),
        base_lib_registry=base_registry,
        plugin_resource_registry=plugin_registry,
        base_lib_paths=(str(registry_path.parent.resolve()),),
        available_resources=available,
        findings=tuple(findings),
    )


def _call_optional_registry_factory(module: object, function_name: str, expected_type: type, object_type: str, findings: list[HealthFinding]):
    factory = getattr(module, function_name, None)
    if not callable(factory):
        return None
    try:
        value = factory()
    except Exception as exc:
        findings.append(_finding("CONFIG.RESOURCE.REGISTRY_FACTORY", f"{function_name} failed: {exc}", function_name, object_type))
        return None
    if not isinstance(value, expected_type):
        findings.append(_finding("CONFIG.RESOURCE.REGISTRY_RETURN", f"{function_name} must return {expected_type.__name__}", function_name, object_type))
        return None
    return value


def _config_uses_resource_ids(config: Mapping[str, Any]) -> bool:
    raw_base_lib = config.get("base_lib")
    if isinstance(raw_base_lib, Mapping):
        modules = raw_base_lib.get("modules")
        if isinstance(modules, list) and any(isinstance(item, Mapping) and "id" in item and "module" not in item and "name" not in item for item in modules):
            return True
    raw_plugins = config.get("plugins")
    return isinstance(raw_plugins, list) and any(isinstance(item, Mapping) and "id" in item and "module" not in item and "path" not in item for item in raw_plugins)


def _find_registry_file(start: Path) -> Path | None:
    resolved = start.resolve()
    for directory in (resolved, *resolved.parents):
        candidate = directory / "registry.py"
        if candidate.is_file():
            return candidate
    return None


def _import_resource_registry_file(path: Path):
    module_name = f"_vibeflow_resource_registry_{abs(hash(path.resolve()))}"
    parent = str(path.parent.resolve())
    inserted = parent not in sys.path
    if inserted:
        sys.path.insert(0, parent)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load registry module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            try:
                sys.path.remove(parent)
            except ValueError:
                pass
