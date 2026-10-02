from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from vibeflow.core.descriptors.catalogs import BaseLibCatalog, NodeCatalog
from vibeflow.core.descriptors.models import (
    BaseLibDescriptor,
    DescriptorModelError,
    ImplementationDescriptor,
    NodeContractDescriptor,
    NodeDescriptor,
    SourceLocator,
)
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.project.resources import BaseLibRegistry


@dataclass(frozen=True)
class LegacyDescriptorError(ValueError):
    code: str
    message: str
    descriptor_id: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class PythonNodeAdapterResult:
    catalog: NodeCatalog
    bindings: Mapping[str, type]

    def binding(self, type_key: str) -> type:
        try:
            return self.bindings[str(type_key).strip()]
        except KeyError as exc:
            raise LegacyDescriptorError(
                code="DESCRIPTOR.PYTHON_BINDING.UNKNOWN",
                message=f"unknown Python node binding '{type_key}'",
                descriptor_id=str(type_key).strip(),
            ) from exc


@dataclass(frozen=True)
class PythonBaseLibAdapterResult:
    catalog: BaseLibCatalog
    modules: Mapping[str, str]

    def module(self, resource_id: str) -> str:
        try:
            return self.modules[str(resource_id).strip()]
        except KeyError as exc:
            raise LegacyDescriptorError(
                code="DESCRIPTOR.PYTHON_BASE_LIB.UNKNOWN",
                message=f"unknown Python base_lib '{resource_id}'",
                descriptor_id=str(resource_id).strip(),
            ) from exc


def node_descriptor_from_registry(registry: NodeRegistry, type_key: str) -> NodeDescriptor:
    """Return the sole authoritative declaration; never inspect class metadata."""
    return registry.descriptor(type_key)


def base_lib_descriptor_from_registry(
    registry: BaseLibRegistry,
    resource_id: str,
) -> BaseLibDescriptor:
    normalized = str(resource_id).strip()
    resource = registry.get(normalized)
    if resource is None:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_BASE_LIB.UNKNOWN",
            message=f"unknown legacy base_lib '{normalized}'",
            descriptor_id=normalized,
        )
    try:
        return BaseLibDescriptor(
            id=normalized,
            display_name=resource.display_name,
            description=resource.description,
            category=resource.category,
            version=resource.version,
            implementations=(
                ImplementationDescriptor(
                    language="python",
                    targets=("python",),
                    source=SourceLocator(
                        kind="module",
                        ref=resource.module,
                    ),
                ),
            ),
        )
    except DescriptorModelError as exc:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_BASE_LIB.INVALID",
            message=f"base_lib '{normalized}' cannot be described: {exc}",
            descriptor_id=normalized,
        ) from exc


def adapt_node_registry(registry: NodeRegistry, *, static_catalog: NodeCatalog | None = None) -> PythonNodeAdapterResult:
    """Bind declared Python implementations beside a portable metadata catalog."""
    catalog = NodeCatalog()
    if static_catalog is not None:
        for descriptor in static_catalog:
            catalog.register(descriptor, source=static_catalog.source_for(descriptor.type_key))
    bindings = {}
    for type_key in registry.available():
        descriptor = registry.descriptor(type_key)
        existing = catalog.get(type_key)
        if existing is None:
            catalog.register(descriptor, source=registry.source_info(type_key).path)
        elif existing != descriptor:
            raise LegacyDescriptorError("DESCRIPTOR.PYTHON_DECLARATION.CONFLICT", f"conflicting authoritative Node declaration '{type_key}'", type_key)
        bindings[type_key] = registry.get(type_key)
    return PythonNodeAdapterResult(catalog, MappingProxyType(bindings))


def adapt_base_lib_registry(
    registry: BaseLibRegistry,
    *,
    static_catalog: BaseLibCatalog | None = None,
) -> PythonBaseLibAdapterResult:
    catalog = BaseLibCatalog()
    if static_catalog is not None:
        for descriptor in static_catalog:
            catalog.register(
                descriptor,
                source=static_catalog.source_for(descriptor.id),
            )
    modules: dict[str, str] = {}
    for resource_id in registry.available():
        legacy = base_lib_descriptor_from_registry(registry, resource_id)
        static = catalog.get(resource_id)
        if static is None:
            catalog.register(legacy, source="python:BaseLibRegistry")
        else:
            _assert_base_lib_metadata_match(static, legacy)
            merged = _merge_python_base_lib_implementation(static, legacy)
            catalog = _replace_base_lib(catalog, merged)
        resource = registry.get(resource_id)
        assert resource is not None
        modules[resource_id] = resource.module
    return PythonBaseLibAdapterResult(
        catalog=catalog,
        modules=MappingProxyType(modules),
    )


def _assert_base_lib_metadata_match(
    static: BaseLibDescriptor,
    legacy: BaseLibDescriptor,
) -> None:
    fields = ("id", "display_name", "description", "category", "version")
    mismatches = [
        field
        for field in fields
        if getattr(static, field) != getattr(legacy, field)
    ]
    if mismatches:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.STATIC_PYTHON.CONFLICT",
            message=(
                "static descriptor and Python registry disagree for "
                f"base_lib '{static.id}': {mismatches}"
            ),
            descriptor_id=static.id,
        )


def _merge_python_base_lib_implementation(
    static: BaseLibDescriptor,
    legacy: BaseLibDescriptor,
) -> BaseLibDescriptor:
    python_impl = legacy.implementations[0]
    existing = [
        item for item in static.implementations if "python" in item.targets
    ]
    if existing:
        if existing != [python_impl]:
            raise LegacyDescriptorError(
                code="DESCRIPTOR.STATIC_PYTHON.SOURCE_CONFLICT",
                message=(
                    f"static Python source for base_lib '{static.id}' "
                    "does not match its registered module"
                ),
                descriptor_id=static.id,
            )
        return static
    return replace(
        static,
        implementations=(*static.implementations, python_impl),
    )


def _replace_base_lib(
    catalog: BaseLibCatalog,
    replacement: BaseLibDescriptor,
) -> BaseLibCatalog:
    out = BaseLibCatalog()
    for descriptor in catalog:
        selected = replacement if descriptor.id == replacement.id else descriptor
        out.register(
            selected,
            source=catalog.source_for(descriptor.id),
        )
    return out


catalog_from_node_registry = adapt_node_registry
base_lib_catalog_from_registry = adapt_base_lib_registry

__all__ = [
    "LegacyDescriptorError",
    "PythonBaseLibAdapterResult",
    "PythonNodeAdapterResult",
    "adapt_base_lib_registry",
    "adapt_node_registry",
    "base_lib_catalog_from_registry",
    "base_lib_descriptor_from_registry",
    "catalog_from_node_registry",
    "node_descriptor_from_registry",
]
