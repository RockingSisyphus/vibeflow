"""Language-neutral, workflow-local extension declarations."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import copy
from types import MappingProxyType
from typing import Any, Mapping

from vibeflow.core.descriptors.catalogs import DescriptorCatalogs, DescriptorCatalogError
from vibeflow.core.descriptors.json_values import freeze_mapping
from vibeflow.core.descriptors.models import DescriptorModelError, _required_text


PLUGIN_ABI = "vibeflow.plugin.v3"
RESOURCE_GROUPS = {
    "node": "nodes", "rule": "rules", "ruleset": "rulesets",
    "data_schema": "schemas", "base_lib": "base_libs",
    "capability": "capabilities", "host_extension": "host_extensions", "plugin": "plugins",
}


def resource_kind(descriptor: Any) -> str:
    """Read typed declaration identity without serializing its contents."""
    from vibeflow.core.descriptors.models import NodeDescriptor, DataSchemaDescriptor, BaseLibDescriptor, CapabilityDescriptor, HostExtensionDescriptor, PluginDescriptor
    from vibeflow.core.rules.models import RuleDescriptor, RulesetDescriptor
    from vibeflow.core.descriptors.source_bundle import PluginDeclarationDescriptor
    types = ((NodeDescriptor, "node"), (RuleDescriptor, "rule"), (RulesetDescriptor, "ruleset"),
             (DataSchemaDescriptor, "data_schema"), (BaseLibDescriptor, "base_lib"),
             (CapabilityDescriptor, "capability"), (HostExtensionDescriptor, "host_extension"),
             (PluginDescriptor, "plugin"), (PluginDeclarationDescriptor, "plugin_declaration"))
    for descriptor_type, kind in types:
        if isinstance(descriptor, descriptor_type):
            return kind
    raise DescriptorCatalogError("DESCRIPTOR.TYPE", f"plugin resources require a resource descriptor, got {type(descriptor).__name__}")


@dataclass(frozen=True)
class ResourceOrigin:
    plugin_id: str
    path: str
    line: int | None = None
    column: int | None = None
    symbol: str = ""

    def __post_init__(self) -> None:
        _required_text(self.plugin_id, field_name="origin.plugin_id")
        for field_name in ("path", "symbol"):
            if not isinstance(getattr(self, field_name), str):
                raise DescriptorModelError(f"origin.{field_name} must be a string")
        for field_name in ("line", "column"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value <= 0):
                raise DescriptorModelError(f"origin.{field_name} must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {"plugin_id": self.plugin_id, "path": self.path,
                **({"line": self.line} if self.line is not None else {}),
                **({"column": self.column} if self.column is not None else {}), "symbol": self.symbol}


@dataclass(frozen=True)
class ResourceDeclaration:
    descriptor: Any
    origin: ResourceOrigin


@dataclass(frozen=True)
class PluginContributions:
    id: str
    resources: tuple[ResourceDeclaration, ...]
    config: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    declaration: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, field_name="plugin.id"))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "config", freeze_mapping(self.config, field_name="plugin.config"))
        object.__setattr__(self, "declaration", freeze_mapping(self.declaration, field_name="plugin.declaration"))
        if self.declaration:
            from vibeflow.core.descriptors.source_bundle import declaration_descriptor
            declaration_descriptor(self.declaration)
        checker = ContributionBuilder(self.id, source=self.source)
        for entry in self.resources:
            if not isinstance(entry, ResourceDeclaration):
                raise DescriptorModelError("plugin.resources must contain resource declarations")
            checker.add(entry.descriptor, origin=entry.origin)

    def _with_config(self, config: Mapping[str, Any] | None = None) -> PluginContributions:
        """Bind one workflow's settings; fixed fields were checked at construction."""
        snapshot = copy(self)
        object.__setattr__(snapshot, "config", freeze_mapping({} if config is None else config, field_name="plugin.config"))
        return snapshot


class ContributionBuilder:
    """Collect validated descriptors without Target objects or filesystem I/O."""

    def __init__(self, plugin_id: str, *, source: str = "") -> None:
        self.id = _required_text(plugin_id, field_name="plugin.id")
        self.source = source
        self._catalogs = DescriptorCatalogs.empty()
        self._entries: list[ResourceDeclaration] = []
        self._closed = False

    def add(self, descriptor: Any, *, origin: ResourceOrigin | None = None) -> Any:
        if self._closed:
            raise DescriptorModelError("plugin contributions are already frozen")
        kind = resource_kind(descriptor)
        if kind not in RESOURCE_GROUPS:
            raise DescriptorModelError(f"unsupported plugin resource kind: {kind}")
        location = origin or ResourceOrigin(self.id, self.source)
        if not isinstance(location, ResourceOrigin) or location.plugin_id != self.id:
            raise DescriptorModelError("resource origin must name the contributing plugin")
        try:
            getattr(self._catalogs, RESOURCE_GROUPS[kind]).register(descriptor, source=location.path, source_location=location.to_dict())
        except DescriptorCatalogError as exc:
            if not exc.code.endswith((".DUPLICATE", ".CONFLICT")):
                raise
            previous = next(item.origin for item in self._entries if resource_kind(item.descriptor) == kind and item.descriptor.id == descriptor.id)
            raise DescriptorCatalogError(exc.code, exc.message, exc.descriptor_id, exc.source, exc.previous_source,
                {"location": {key:value for key,value in location.to_dict().items() if key in {"line","column"}}, "origins": {"current": location.to_dict(), "previous": previous.to_dict()}}) from exc
        self._entries.append(ResourceDeclaration(descriptor, location))
        return descriptor

    def finish(self, *, config: Mapping[str, Any] | None = None) -> PluginContributions:
        if self._closed:
            raise DescriptorModelError("plugin contributions are already frozen")
        self._closed = True
        return PluginContributions(self.id, tuple(self._entries), config or {}, self.source)


def compose_contributions(contributions: tuple[PluginContributions, ...]) -> DescriptorCatalogs:
    catalogs = DescriptorCatalogs.empty()
    origins, settings, seen = {}, {}, {}
    files = []
    for plugin in contributions:
        if plugin.id in seen:
            previous = seen[plugin.id]
            raise DescriptorCatalogError("PLUGIN.DUPLICATE", f"duplicate selected plugin '{plugin.id}'",
                descriptor_id=plugin.id, source=plugin.source, previous_source=previous.source,
                details={"origins": {"current": {"plugin_id":plugin.id,"path":plugin.source},
                                    "previous": {"plugin_id":previous.id,"path":previous.source}}})
        seen[plugin.id] = plugin
        settings[plugin.id] = plugin.config
        for entry in plugin.resources:
            descriptor, origin = entry.descriptor, entry.origin
            group = RESOURCE_GROUPS[resource_kind(descriptor)]
            key = (group, descriptor.id)
            try:
                getattr(catalogs, group).register(descriptor, source=origin.path, source_location={"path":origin.path, **({"line":origin.line} if origin.line else {}), **({"column":origin.column} if origin.column else {})})
            except DescriptorCatalogError as exc:
                previous = origins.get(key)
                error = DescriptorCatalogError(exc.code, exc.message, exc.descriptor_id, exc.source, exc.previous_source,
                    {"location": {key:value for key,value in origin.to_dict().items() if key in {"line","column"}},
                     "origins": {"current": origin.to_dict(), "previous": previous.to_dict() if previous else {}}})
                raise error from exc
            origins[key] = origin
            if origin.path not in files:
                files.append(origin.path)
    from dataclasses import replace
    for group in RESOURCE_GROUPS.values():
        getattr(catalogs, group).freeze()
    return replace(catalogs, source_files=tuple(files), origins=MappingProxyType(origins),
                   plugin_settings=MappingProxyType(settings))


def contribution_facts(catalogs: DescriptorCatalogs) -> Mapping[str, Any]:
    """Portable declaration/provenance facts, separate from Target load facts."""
    declarations = []
    for kind, group in RESOURCE_GROUPS.items():
        for descriptor in getattr(catalogs, group):
            origin = catalogs.origins.get((group, descriptor.id))
            declarations.append({"kind":kind, "id":descriptor.id, "descriptor":descriptor.to_dict(),
                                 "origin":origin.to_dict() if origin is not None else {}})
    return {"plugins":catalogs.plugin_settings, "plugin_selections":catalogs.plugin_records,
            "source_load_states":catalogs.source_load_states,
            "declarations":tuple(declarations)}
