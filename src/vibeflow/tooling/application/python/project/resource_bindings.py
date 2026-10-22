"""Bind the shared resource-use result to native Python implementations."""
from dataclasses import dataclass, field
from typing import Mapping

from vibeflow.targets.python.project.resource_bindings import PythonResourceBinding
from vibeflow.core.descriptors.resource_use import ResourceUse



@dataclass(frozen=True)
class PythonResources:
    global_config: Mapping[str, object] = field(default_factory=dict)
    base_libs: tuple[PythonResourceBinding, ...] = ()
    plugins: tuple[PythonResourceBinding, ...] = ()

    resource_use: ResourceUse | None = None

    @property
    def has_planned(self):
        return any(item.status == "planned" for item in (*self.base_libs, *self.plugins))

    def to_dict(self):
        return {"global_config": dict(self.global_config),
                "base_lib": {"modules": [item.to_dict() for item in self.base_libs]},
                "plugins": [item.to_dict() for item in self.plugins],
                "resource_use": self.resource_use.to_dict() if self.resource_use else None}


def resource_binding(registry, group, descriptor, *, config=None, selection=None):
    root = registry.resource_roots.get((group, descriptor.id))
    catalogs = registry.prepared_resources.catalogs
    origin = catalogs.origins.get((group, descriptor.id))
    implementation = next((item for item in descriptor.implementations if item.language == "python"), None)
    return PythonResourceBinding(descriptor, implementation,
        root_id=root.id if root else "", root_path=str(root.path) if root else "",
        source_path=origin.path if origin else "", config=config or {}, selection=selection or {})


def bind_python_resources(registry, resource_use):
    loaded = registry.prepared_resources
    libraries = [resource_binding(registry, "base_libs", descriptor,
        selection=resource_use.selection("base_lib", descriptor.id))
        for descriptor in loaded.catalogs.base_libs if resource_use.allows("base_lib", descriptor.id)
        and any(item.language == "python" for item in descriptor.implementations)]
    libraries.extend(PythonResourceBinding(None, status="planned", selection=item)
                     for item in resource_use.planned if item["kind"] == "base_lib")
    plugins = []
    for selection in loaded.lifecycle_selections:
        if selection.get("status") == "planned":
            plugins.append(PythonResourceBinding(None, status="planned", selection=selection))
            continue
        descriptor = loaded.catalogs.plugins.require(selection["id"])
        if resource_use.allows("plugin", descriptor.id) and any(item.language == "python" for item in descriptor.implementations):
            plugins.append(resource_binding(registry, "plugins", descriptor, config=selection.get("config", {}), selection=selection))
    config = loaded.document.data.get("global_config", {}) if loaded.document else {}
    return PythonResources(dict(config), tuple(libraries), tuple(plugins), resource_use)
