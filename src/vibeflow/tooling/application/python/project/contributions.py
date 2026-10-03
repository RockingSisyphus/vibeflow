"""Adapt a workflow's portable contributions to native Python resources."""

from dataclasses import replace
import inspect
from pathlib import Path
from types import MappingProxyType

from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.resources import BaseLibRegistry, PluginResourceRegistry, PluginInfo
from vibeflow.tooling.application.python.project.resources import ConfigResources
from vibeflow.tooling.application.python.project.types import WorkspaceResourceRegistries


def contributed_resources(workspace, registry):
    catalog = registry.rule_catalogs[0]
    base_registry, plugin_resources = BaseLibRegistry(), PluginResourceRegistry()
    for descriptor in catalog.base_libs:
        implementation = next((item for item in descriptor.implementations if item.language == "python"), None)
        if implementation is None:
            continue
        root = registry.resource_roots[("base_libs", descriptor.id)]
        origin = catalog.origins[("base_libs", descriptor.id)]
        source = implementation.source
        path = (root.path / source.ref).resolve()
        module = source.ref if source.kind == "module" else (
            ".".join(path.relative_to(root.path).with_suffix("").parts) if path.is_relative_to(root.path)
            else str(path))
        base_registry.register(descriptor.id, module=module, display_name=descriptor.display_name,
            description=descriptor.description, category=descriptor.category, version=descriptor.version,
            rulesets=descriptor.rulesets, root_id=root.id, root_path=str(root.path), source_path=origin.path)
    for descriptor in catalog.plugins:
        implementation = next((item for item in descriptor.implementations if item.language == "python"), None)
        if implementation is None:
            continue
        root = registry.resource_roots[("plugins", descriptor.id)]
        origin = catalog.origins[("plugins", descriptor.id)]
        source = implementation.source
        module = source.ref if source.kind == "module" else str((root.path / source.ref).resolve())
        plugin_resources.register(descriptor.id, module=module, class_name=source.export or "create_plugin",
            plugin_type=descriptor.plugin_type, display_name=descriptor.display_name or descriptor.id,
            description=descriptor.description or descriptor.id, version=descriptor.version,
            config_schema=descriptor.config_schema, config_defaults=descriptor.config_defaults,
            priority=descriptor.priority, rulesets=descriptor.rulesets,
            root_id=root.id, root_path=str(root.path), source_path=origin.path)
    paths = tuple(str(root.path) for root in workspace.roots if root.project_target == "python")
    resources = ConfigResources(base_lib_paths=paths, base_libs=base_registry.resources(), plugins=plugin_resources.resources())
    registries = {root.id: WorkspaceResourceRegistries(base_registry, plugin_resources, paths, True, True)
                  for root in workspace.roots if root.project_target == "python"}
    return registries, resources, ()


def lifecycle_registry(registry, *, workflow_id, config_path, plugin_types=("compiler", "runtime")):
    """Create instances at the native compile/run boundary, not declaration time."""
    result = PluginRegistry()
    loaded = registry.loaded_plugins
    created = []
    try:
        for selection in loaded.lifecycle_selections:
            if selection.get("status") == "planned":
                continue
            descriptor = loaded.catalogs.plugins.require(selection["id"])
            if descriptor.plugin_type not in plugin_types:
                continue
            factory = registry.direct_bindings.get(("plugin", descriptor.id))
            if factory is None:
                from vibeflow.tooling.application.python.project.declarations import _load_rule_handler, _implementation_path
                root = registry.resource_roots[("plugins", descriptor.id)]
                source = descriptor.implementations[0].source
                factory = _load_rule_handler(_implementation_path(source.kind, source.ref, root.path, registry.source_roots), source.export, root, registry)
            config = MappingProxyType(dict(selection["config"]))
            context = MappingProxyType({"config": config, "workflow_id": workflow_id, "config_path": str(config_path)})
            from vibeflow.targets.python.sdk.loading import source_paths
            with source_paths(registry.source_roots):
                instance = factory(context)
            if inspect.isawaitable(instance):
                raise ValueError("Python lifecycle factories must return an instance synchronously")
            if instance is None:
                raise ValueError("lifecycle factory must return an instance")
            created.append(instance)
            result.register(instance, plugin_type=descriptor.plugin_type, name=descriptor.id,
                priority=descriptor.priority, source=descriptor.implementations[0].source.ref,
                class_name=descriptor.implementations[0].source.export or "", config_keys=tuple(config),
                source_path=loaded.catalogs.plugins.source_for(descriptor.id), rulesets=descriptor.rulesets, conflict="error",
                info=PluginInfo(
                    descriptor.id, descriptor.plugin_type, descriptor.display_name, "", descriptor.description, descriptor.version))
    except BaseException:
        for instance in reversed(created):
            dispose = getattr(instance, "dispose", None)
            if callable(dispose):
                dispose()
        raise
    return result


def release_plugins(plugin_registry, *, plugin_type):
    instances = plugin_registry.runtime_plugins() if plugin_type == "runtime" else plugin_registry.compiler_plugins()
    for instance in reversed(instances):
        dispose = getattr(instance, "dispose", None)
        if callable(dispose):
            dispose()


def release_runtime_plugins(plugin_registry):
    release_plugins(plugin_registry, plugin_type="runtime")
