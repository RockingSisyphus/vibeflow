"""Select canonical declarations without reconstructing resource registries."""
from dataclasses import dataclass, field, replace
from typing import Mapping

from vibeflow.core.descriptors.json_values import freeze_mapping
from vibeflow.targets.python.project.resource_bindings import PythonResourceBinding
from vibeflow.core.findings import HealthFinding
from vibeflow.tooling.project.host_extensions import (
    HostExtensionResource, host_extension_resources,
)


@dataclass(frozen=True)
class PythonResources:
    global_config: Mapping[str, object] = field(default_factory=dict)
    base_libs: tuple[PythonResourceBinding, ...] = ()
    plugins: tuple[PythonResourceBinding, ...] = ()
    host_extensions: tuple[HostExtensionResource, ...] = ()
    selection_facts: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "selection_facts", freeze_mapping(self.selection_facts, field_name="resource selections"))

    @property
    def has_planned(self):
        return any(item.status == "planned" for item in (*self.base_libs, *self.plugins, *self.host_extensions))

    def to_dict(self):
        return {"global_config": dict(self.global_config),
                "base_lib": {"modules": [item.to_dict() for item in self.base_libs]},
                "plugins": [item.to_dict() for item in self.plugins],
                "host_extensions": [item.to_dict() for item in self.host_extensions]}


def resource_binding(registry, group, descriptor, *, config=None, selection=None):
    root = registry.resource_roots.get((group, descriptor.id))
    catalogs = registry.loaded_plugins.catalogs
    origin = catalogs.origins.get((group, descriptor.id))
    implementation = next((item for item in descriptor.implementations if item.language == "python"), None)
    return PythonResourceBinding(descriptor, implementation,
        root_id=root.id if root else "", root_path=str(root.path) if root else "",
        source_path=origin.path if origin else "", config=config or {}, selection=selection or {})


def select_python_resources(config, *, registry=None, base_path=None):
    findings = []
    global_config = config.get("global_config", {})
    if not isinstance(global_config, Mapping):
        findings.append(HealthFinding(rule_id="CONFIG.SCHEMA.GLOBAL_CONFIG", severity="error",
            object_type="config", object_id="global_config", message="global_config must be an object"))
        global_config = {}
    loaded = getattr(registry, "loaded_plugins", None)
    libraries, plugins = [], []
    if loaded is not None:
        for descriptor in loaded.catalogs.base_libs:
            if any(item.language == "python" for item in descriptor.implementations):
                libraries.append(resource_binding(registry, "base_libs", descriptor))
        for selection in loaded.lifecycle_selections:
            if selection.get("status") == "planned":
                plugins.append(PythonResourceBinding(None, status="planned", selection=selection))
                continue
            descriptor = loaded.catalogs.plugins.require(selection["id"])
            if any(item.language == "python" for item in descriptor.implementations):
                plugins.append(resource_binding(registry, "plugins", descriptor, config=selection.get("config", {}), selection=selection))
    raw_libraries = config.get("base_lib")
    if raw_libraries:
        if not isinstance(raw_libraries, Mapping) or set(raw_libraries) - {"modules"}:
            findings.append(HealthFinding(rule_id="CONFIG.RESOURCE.REGISTRATION_REMOVED", severity="error",
                object_type="config", object_id="base_lib", message="base_lib only selects contributed IDs; paths/module registration was removed"))
        else:
            selected = []
            available = {item.id:item for item in libraries}
            for index, value in enumerate(raw_libraries.get("modules", ())):
                spec = {"id":value} if isinstance(value,str) else dict(value) if isinstance(value,Mapping) else {}
                key = str(spec.get("id", ""))
                if key and spec.get("status") == "planned":
                    selected.append(PythonResourceBinding(None, status="planned", selection={"kind":"base_lib", **spec}))
                elif key in available:
                    selected.append(replace(available[key], selection=spec))
                else:
                    findings.append(HealthFinding(rule_id="CONFIG.RESOURCE.UNKNOWN_BASE_LIB",severity="error",
                        object_type="config",object_id=f"base_lib.modules[{index}]",message=f"unknown contributed BaseLib ID: {key}"))
            libraries = selected
    if loaded is None and config.get("plugins"):
        findings.append(HealthFinding(rule_id="PLUGIN.CONFIG.ROOT", severity="error", object_type="config",
            object_id="plugins", message="plugin resources require an owning SDK catalog"))
    hosts = host_extension_resources(config, findings=findings)
    selections = {key:config[key] for key in ("base_lib", "host_extensions") if key in config}
    return PythonResources(dict(global_config), tuple(libraries), tuple(plugins), tuple(hosts), selections), tuple(findings)
