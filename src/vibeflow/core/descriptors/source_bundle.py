
from vibeflow.core.rules.selection.models import selection_refs, selection_data
"""Portable source membership for executable resources and plugin declarations."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.core.descriptors.models import (
    ImplementationDescriptor, DescriptorModelError, _required_text, _string_tuple,
)
from vibeflow.core.descriptors.presentation import normalize_presentation


def implementation_sources(implementation):
    """The entry is distinct from explicitly registered support sources."""
    return (("entry", implementation.source),
            *(("support", source) for source in getattr(implementation, "implementation_files", ())))


@dataclass(frozen=True)
class PluginDeclarationDescriptor:
    id: str
    implementations: tuple[ImplementationDescriptor, ...]
    rulesets: tuple[str, ...] = ()
    base_libs: tuple[str, ...] = ()
    presentation: Mapping[str, Any] = field(default_factory=dict)
    display_name: str = ""
    description: str = ""
    version: str = ""

    def __post_init__(self):
        object.__setattr__(self, "id", _required_text(self.id, field_name="plugin.id"))
        object.__setattr__(self, "rulesets", selection_refs(self.rulesets))
        for name in ("base_libs",):
            object.__setattr__(self, name, _string_tuple(getattr(self, name), field_name="plugin." + name))
        if not isinstance(self.implementations,(tuple,list)) or not self.implementations or not all(isinstance(item,ImplementationDescriptor) for item in self.implementations):
            raise DescriptorModelError("plugin.declaration.implementations requires implementation descriptors")
        object.__setattr__(self, "implementations", tuple(self.implementations))
        for name in ("display_name","description","version"):
            if not isinstance(getattr(self,name),str):
                raise DescriptorModelError("plugin.declaration."+name+" must be a string")
        object.__setattr__(self, "presentation", normalize_presentation(self.presentation, field_name="plugin.presentation"))

    def to_dict(self):
        return {"kind":"plugin_declaration", "id":self.id, "display_name":self.display_name or self.id,
                "description":self.description, "version":self.version,
                "rulesets":selection_data(self.rulesets), "base_libs":list(self.base_libs),
                "presentation":dict(self.presentation),
                "implementations":[item.to_dict() for item in self.implementations]}


def declaration_descriptor(value):
    from vibeflow.core.descriptors.decode import _parse_implementations
    return PluginDeclarationDescriptor(
        id=value["id"], implementations=_parse_implementations(value.get("implementations", ()), field="plugin.declaration.implementations"),
        rulesets=value.get("rulesets", ()), base_libs=value.get("base_libs", ()),
        presentation=value.get("presentation", {}), display_name=value.get("display_name", ""),
        description=value.get("description", ""), version=value.get("version", ""))


def source_resources(catalogs):
    """Fixed declarations in the selected workflow, including plugin packages."""
    for kind, name in (("node", "nodes"), ("base_lib", "base_libs"),
                       ("plugin", "plugins"), ("host_extension", "host_extensions")):
        for descriptor in getattr(catalogs, name):
            yield kind, descriptor
    for record in catalogs.plugin_records:
        if record.get("loaded") and record.get("declaration"):
            yield "plugin_declaration", declaration_descriptor(record["declaration"])


def ownership_resources(catalogs):
    """Rule code is also declared source, without becoming a runtime resource."""
    yield from source_resources(catalogs)
    for descriptor in catalogs.rules:
        if descriptor.implementations:
            yield "rule", descriptor
