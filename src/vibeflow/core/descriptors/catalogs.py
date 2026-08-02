from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Iterable, Iterator, TypeVar

from vibeflow.core.descriptors.models import (
    BaseLibDescriptor,
    CapabilityDescriptor,
    DataSchemaDescriptor,
    HostExtensionDescriptor,
    NodeDescriptor,
    PluginDescriptor,
)


DescriptorT = TypeVar(
    "DescriptorT",
    NodeDescriptor,
    BaseLibDescriptor,
    DataSchemaDescriptor,
    CapabilityDescriptor,
    HostExtensionDescriptor,
    PluginDescriptor,
)


@dataclass(frozen=True)
class DescriptorCatalogError(ValueError):
    code: str
    message: str
    descriptor_id: str = ""
    source: str = ""
    previous_source: str = ""

    def __str__(self) -> str:
        locations = [
            value for value in (self.previous_source, self.source) if value
        ]
        suffix = f" ({' vs '.join(locations)})" if locations else ""
        return f"{self.code}: {self.message}{suffix}"


class _DescriptorCatalog(Generic[DescriptorT]):
    descriptor_label = "descriptor"
    descriptor_type: type[object] = object

    def __init__(self, descriptors: Iterable[DescriptorT] = ()) -> None:
        self._descriptors: dict[str, DescriptorT] = {}
        self._sources: dict[str, str] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(
        self,
        descriptor: DescriptorT,
        *,
        source: str | None = None,
    ) -> None:
        if not isinstance(descriptor, self.descriptor_type):
            raise DescriptorCatalogError(
                code="DESCRIPTOR.TYPE",
                message=(
                    f"{self.descriptor_label} catalog requires "
                    f"{self.descriptor_type.__name__}, got "
                    f"{type(descriptor).__name__}"
                ),
                source=str(source) if source is not None else "",
            )
        descriptor_id = self._descriptor_id(descriptor)
        source_text = str(source) if source is not None else ""
        previous = self._descriptors.get(descriptor_id)
        if previous is not None:
            code = (
                "DESCRIPTOR.DUPLICATE"
                if previous == descriptor
                else "DESCRIPTOR.CONFLICT"
            )
            description = (
                f"duplicate {self.descriptor_label} id '{descriptor_id}'"
                if code == "DESCRIPTOR.DUPLICATE"
                else f"conflicting {self.descriptor_label} id '{descriptor_id}'"
            )
            raise DescriptorCatalogError(
                code=code,
                message=description,
                descriptor_id=descriptor_id,
                source=source_text,
                previous_source=self._sources.get(descriptor_id, ""),
            )
        self._descriptors[descriptor_id] = descriptor
        self._sources[descriptor_id] = source_text

    def get(self, descriptor_id: str) -> DescriptorT | None:
        return self._descriptors.get(str(descriptor_id).strip())

    def require(self, descriptor_id: str) -> DescriptorT:
        normalized = str(descriptor_id).strip()
        descriptor = self.get(normalized)
        if descriptor is None:
            raise DescriptorCatalogError(
                code="DESCRIPTOR.UNKNOWN",
                message=f"unknown {self.descriptor_label} id '{normalized}'",
                descriptor_id=normalized,
            )
        return descriptor

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptors(self) -> tuple[DescriptorT, ...]:
        return tuple(
            self._descriptors[key] for key in self.available()
        )

    def source_for(self, descriptor_id: str) -> str:
        return self._sources.get(str(descriptor_id).strip(), "")

    def __len__(self) -> int:
        return len(self._descriptors)

    def __iter__(self) -> Iterator[DescriptorT]:
        return iter(self.descriptors())

    def to_dict(self) -> dict[str, object]:
        return {
            descriptor_id: self._descriptors[descriptor_id].to_dict()
            for descriptor_id in self.available()
        }

    @staticmethod
    def _descriptor_id(descriptor: DescriptorT) -> str:
        return str(getattr(descriptor, "id")).strip()


class NodeCatalog(_DescriptorCatalog[NodeDescriptor]):
    descriptor_label = "node"
    descriptor_type = NodeDescriptor


class BaseLibCatalog(_DescriptorCatalog[BaseLibDescriptor]):
    descriptor_label = "base_lib"
    descriptor_type = BaseLibDescriptor


class SchemaRegistry(_DescriptorCatalog[DataSchemaDescriptor]):
    descriptor_label = "data schema"
    descriptor_type = DataSchemaDescriptor


class CapabilityCatalog(_DescriptorCatalog[CapabilityDescriptor]):
    descriptor_label = "capability"
    descriptor_type = CapabilityDescriptor


class HostExtensionCatalog(_DescriptorCatalog[HostExtensionDescriptor]):
    descriptor_label = "host_extension"
    descriptor_type = HostExtensionDescriptor


class PluginCatalog(_DescriptorCatalog[PluginDescriptor]):
    descriptor_label = "plugin"
    descriptor_type = PluginDescriptor


@dataclass(frozen=True)
class DescriptorCatalogs:
    nodes: NodeCatalog
    base_libs: BaseLibCatalog
    schemas: SchemaRegistry
    capabilities: CapabilityCatalog
    host_extensions: HostExtensionCatalog
    plugins: PluginCatalog = field(default_factory=PluginCatalog)
    @classmethod
    def empty(cls) -> DescriptorCatalogs:
        return cls(
            nodes=NodeCatalog(),
            base_libs=BaseLibCatalog(),
            schemas=SchemaRegistry(),
            capabilities=CapabilityCatalog(),
            host_extensions=HostExtensionCatalog(),
            plugins=PluginCatalog(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": self.nodes.to_dict(),
            "base_lib": self.base_libs.to_dict(),
            "data_schemas": self.schemas.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "host_extensions": self.host_extensions.to_dict(),
            "plugins": self.plugins.to_dict(),
        }

    @property
    def base_lib(self) -> BaseLibCatalog:
        return self.base_libs

    @property
    def data_schemas(self) -> SchemaRegistry:
        return self.schemas


DataSchemaRegistry = SchemaRegistry
