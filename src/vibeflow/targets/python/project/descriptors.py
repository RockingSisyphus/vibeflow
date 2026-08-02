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


def node_descriptor_from_registry(
    registry: NodeRegistry,
    type_key: str,
) -> NodeDescriptor:
    """Convert one legacy NodeRegistry entry without retaining its class."""

    normalized = str(type_key).strip()
    node_cls = registry.get(normalized)
    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)
    if info is None or contract is None:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_NODE.SHAPE",
            message=(
                f"registered node '{normalized}' must declare NODE_INFO "
                "and CONTRACT"
            ),
            descriptor_id=normalized,
        )
    info_type_key = str(getattr(info, "type_key", "") or "").strip()
    if info_type_key != normalized:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_NODE.TYPE_KEY",
            message=(
                f"registry key '{normalized}' does not match "
                f"NODE_INFO.type_key '{info_type_key}'"
            ),
            descriptor_id=normalized,
        )
    config_spec = registry.get_config_spec(normalized)
    contract_params_schema = getattr(contract, "params_schema", {})
    if dict(contract_params_schema) != {
        key: dict(value) for key, value in config_spec.schema.items()
    }:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_NODE.PARAMS_SCHEMA",
            message=(
                f"node '{normalized}' CONTRACT.params_schema does not match "
                "its NodeRegistry config schema"
            ),
            descriptor_id=normalized,
        )
    try:
        descriptor_contract = NodeContractDescriptor(
            requires=tuple(getattr(contract, "requires", ())),
            provides=tuple(getattr(contract, "provides", ())),
            input_semantics=getattr(contract, "input_semantics", {}),
            output_semantics=getattr(contract, "output_semantics", {}),
            params_schema=config_spec.schema,
            params_defaults=config_spec.defaults,
            output_schema=getattr(contract, "output_schema", {}),
            examples=tuple(getattr(contract, "examples", ())),
        )
        implementation = ImplementationDescriptor(
            language="python",
            targets=("python",),
            source=SourceLocator(
                kind="module",
                ref=str(getattr(node_cls, "__module__", "")),
                export=str(getattr(node_cls, "__qualname__", "")),
            ),
        )
        return NodeDescriptor(
            type_key=normalized,
            display_name=str(getattr(info, "display_name", "") or ""),
            category=str(getattr(info, "category", "") or ""),
            description=str(getattr(info, "description", "") or ""),
            version=str(getattr(info, "version", "") or ""),
            flow_kind=str(getattr(info, "flow_kind", "") or ""),
            purity=str(getattr(info, "purity", "pure") or "pure"),
            author=getattr(info, "author", None),
            tags=tuple(getattr(info, "tags", ())),
            external=getattr(info, "external", False),
            contract=descriptor_contract,
            implementations=(implementation,),
        )
    except DescriptorModelError as exc:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.LEGACY_NODE.INVALID",
            message=f"node '{normalized}' cannot be described: {exc}",
            descriptor_id=normalized,
        ) from exc


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


def adapt_node_registry(
    registry: NodeRegistry,
    *,
    static_catalog: NodeCatalog | None = None,
) -> PythonNodeAdapterResult:
    """Merge legacy Python bindings into static, language-neutral metadata."""

    catalog = NodeCatalog()
    if static_catalog is not None:
        for descriptor in static_catalog:
            catalog.register(
                descriptor,
                source=static_catalog.source_for(descriptor.type_key),
            )
    bindings: dict[str, type] = {}
    for type_key in registry.available():
        legacy = node_descriptor_from_registry(registry, type_key)
        static = catalog.get(type_key)
        if static is None:
            catalog.register(legacy, source="python:NodeRegistry")
        else:
            _assert_node_contract_match(static, legacy)
            merged = _merge_python_node_implementation(static, legacy)
            catalog = _replace_node(catalog, merged)
        bindings[type_key] = registry.get(type_key)
    return PythonNodeAdapterResult(
        catalog=catalog,
        bindings=MappingProxyType(bindings),
    )


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


def _assert_node_contract_match(
    static: NodeDescriptor,
    legacy: NodeDescriptor,
) -> None:
    fields = (
        "type_key",
        "display_name",
        "category",
        "description",
        "version",
        "flow_kind",
        "purity",
        "author",
        "tags",
        "external",
        "contract",
    )
    mismatches = [
        field
        for field in fields
        if getattr(static, field) != getattr(legacy, field)
    ]
    if mismatches:
        raise LegacyDescriptorError(
            code="DESCRIPTOR.STATIC_PYTHON.CONFLICT",
            message=(
                f"static descriptor and Python registry disagree for "
                f"node '{static.type_key}': {mismatches}"
            ),
            descriptor_id=static.type_key,
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


def _merge_python_node_implementation(
    static: NodeDescriptor,
    legacy: NodeDescriptor,
) -> NodeDescriptor:
    python_impl = legacy.implementations[0]
    existing = [
        item for item in static.implementations if "python" in item.targets
    ]
    if existing:
        if existing != [python_impl]:
            raise LegacyDescriptorError(
                code="DESCRIPTOR.STATIC_PYTHON.SOURCE_CONFLICT",
                message=(
                    f"static Python source for node '{static.type_key}' "
                    "does not match its registered class"
                ),
                descriptor_id=static.type_key,
            )
        return static
    return replace(
        static,
        implementations=(*static.implementations, python_impl),
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


def _replace_node(catalog: NodeCatalog, replacement: NodeDescriptor) -> NodeCatalog:
    out = NodeCatalog()
    for descriptor in catalog:
        selected = (
            replacement
            if descriptor.type_key == replacement.type_key
            else descriptor
        )
        out.register(
            selected,
            source=catalog.source_for(descriptor.type_key),
        )
    return out


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
