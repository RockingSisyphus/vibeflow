"""File-backed descriptor catalogs with provenance kept outside Core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vibeflow.core.descriptors.catalogs import (
    BaseLibCatalog,
    CapabilityCatalog,
    DataSchemaRegistry,
    DescriptorCatalogError,
    DescriptorCatalogs as CoreDescriptorCatalogs,
    HostExtensionCatalog,
    NodeCatalog,
    PluginCatalog,
    SchemaRegistry,
)


@dataclass(frozen=True)
class DescriptorCatalogs(CoreDescriptorCatalogs):
    """File-backed aggregate returned by project descriptor loaders."""

    source_files: tuple[Path, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["source_files"] = [str(path) for path in self.source_files]
        return payload


__all__ = [
    "BaseLibCatalog",
    "CapabilityCatalog",
    "DataSchemaRegistry",
    "DescriptorCatalogError",
    "DescriptorCatalogs",
    "HostExtensionCatalog",
    "NodeCatalog",
    "PluginCatalog",
    "SchemaRegistry",
]
