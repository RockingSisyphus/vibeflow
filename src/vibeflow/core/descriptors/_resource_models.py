from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from vibeflow.core.descriptors.models import (
    JSON_SCHEMA_2020_12,
    DescriptorModelError,
    ImplementationDescriptor,
    _freeze_mapping,
    _required_text,
    _string_tuple,
    _thaw_json,
    _validate_implementation_coverage,
)


PLUGIN_TYPES = frozenset({"policy", "compiler", "runtime"})


@dataclass(frozen=True)
class BaseLibDescriptor:
    id: str
    display_name: str
    description: str
    implementations: tuple[ImplementationDescriptor, ...]
    dependencies: tuple[str, ...] = ()
    external_packages: tuple[str, ...] = ()
    category: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _required_text(self.id, field_name="base_lib.id"),
        )
        object.__setattr__(
            self,
            "display_name",
            _required_text(
                self.display_name,
                field_name="base_lib.display_name",
            ),
        )
        object.__setattr__(
            self,
            "description",
            _required_text(
                self.description,
                field_name="base_lib.description",
            ),
        )
        implementations = tuple(self.implementations)
        if not implementations:
            raise DescriptorModelError(
                "base_lib.implementations cannot be empty"
            )
        if not all(
            isinstance(item, ImplementationDescriptor)
            for item in implementations
        ):
            raise DescriptorModelError(
                "base_lib.implementations must contain ImplementationDescriptor values"
            )
        _validate_implementation_coverage(
            implementations,
            field_name="base_lib.implementations",
        )
        object.__setattr__(self, "implementations", implementations)
        object.__setattr__(
            self,
            "dependencies",
            _string_tuple(
                self.dependencies,
                field_name="base_lib.dependencies",
            ),
        )
        if self.id in self.dependencies:
            raise DescriptorModelError("base_lib cannot depend on itself")
        object.__setattr__(
            self,
            "external_packages",
            _string_tuple(
                self.external_packages,
                field_name="base_lib.external_packages",
            ),
        )
        object.__setattr__(self, "category", str(self.category or "").strip())
        object.__setattr__(self, "version", str(self.version or "").strip())

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "base_lib",
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "implementations": [
                item.to_dict() for item in self.implementations
            ],
            "dependencies": list(self.dependencies),
            "external_packages": list(self.external_packages),
        }


@dataclass(frozen=True)
class DataSchemaDescriptor:
    type_key: str
    schema: Mapping[str, Any]
    representation: str = "json"
    display_name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "type_key",
            _required_text(
                self.type_key,
                field_name="data_schema.type_key",
            ),
        )
        representation = _required_text(
            self.representation,
            field_name="data_schema.representation",
        )
        if representation != "json":
            raise DescriptorModelError(
                "data_schema.representation must be 'json'"
            )
        if not isinstance(self.schema, Mapping):
            raise DescriptorModelError("data_schema.schema must be an object")
        schema = dict(self.schema)
        dialect = schema.get("$schema")
        if dialect is not None and dialect != JSON_SCHEMA_2020_12:
            raise DescriptorModelError(
                "data_schema.schema.$schema must use JSON Schema draft 2020-12"
            )
        schema["$schema"] = JSON_SCHEMA_2020_12
        object.__setattr__(
            self,
            "schema",
            _freeze_mapping(schema, field_name="data_schema.schema"),
        )
        object.__setattr__(self, "representation", representation)
        object.__setattr__(
            self,
            "display_name",
            str(self.display_name or "").strip(),
        )
        object.__setattr__(
            self,
            "description",
            str(self.description or "").strip(),
        )

    @property
    def id(self) -> str:
        return self.type_key

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "data_schema",
            "type_key": self.type_key,
            "representation": self.representation,
            "display_name": self.display_name,
            "description": self.description,
            "schema": _thaw_json(self.schema),
        }


@dataclass(frozen=True)
class CapabilityOperationDescriptor:
    input_type: str
    output_type: str
    completion: str = "immediate"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_type",
            _required_text(
                self.input_type,
                field_name="capability operation input_type",
            ),
        )
        object.__setattr__(
            self,
            "output_type",
            _required_text(
                self.output_type,
                field_name="capability operation output_type",
            ),
        )
        completion = _required_text(
            self.completion,
            field_name="capability operation completion",
        )
        if completion not in {"immediate", "suspend"}:
            raise DescriptorModelError(
                "capability operation completion must be immediate or suspend"
            )
        object.__setattr__(self, "completion", completion)

    def to_dict(self) -> dict[str, str]:
        return {
            "input_type": self.input_type,
            "output_type": self.output_type,
            "completion": self.completion,
        }


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    targets: tuple[str, ...]
    operations: Mapping[str, CapabilityOperationDescriptor]
    display_name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _required_text(self.id, field_name="capability.id"),
        )
        targets = _string_tuple(
            self.targets,
            field_name="capability.targets",
        )
        if not targets:
            raise DescriptorModelError("capability.targets cannot be empty")
        unknown = sorted(set(targets) - {"node", "browser"})
        if unknown:
            raise DescriptorModelError(
                f"capability.targets contains unsupported targets: {unknown}"
            )
        if not isinstance(self.operations, Mapping) or not self.operations:
            raise DescriptorModelError(
                "capability.operations must be a non-empty object"
            )
        operations: dict[str, CapabilityOperationDescriptor] = {}
        for key, operation in self.operations.items():
            operation_name = _required_text(
                key,
                field_name="capability operation name",
            )
            if not isinstance(operation, CapabilityOperationDescriptor):
                raise DescriptorModelError(
                    "capability.operations values must be "
                    "CapabilityOperationDescriptor values"
                )
            operations[operation_name] = operation
        object.__setattr__(self, "targets", targets)
        object.__setattr__(
            self,
            "operations",
            MappingProxyType(operations),
        )
        object.__setattr__(
            self,
            "display_name",
            str(self.display_name or "").strip(),
        )
        object.__setattr__(
            self,
            "description",
            str(self.description or "").strip(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "capability",
            "id": self.id,
            "targets": list(self.targets),
            "display_name": self.display_name,
            "description": self.description,
            "operations": {
                key: value.to_dict()
                for key, value in self.operations.items()
            },
        }


@dataclass(frozen=True)
class HostExtensionDescriptor:
    id: str
    targets: tuple[str, ...]
    implementations: tuple[ImplementationDescriptor, ...]
    provides: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    external_packages: tuple[str, ...] = ()
    display_name: str = ""
    description: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _required_text(self.id, field_name="host_extension.id"),
        )
        targets = _string_tuple(
            self.targets,
            field_name="host_extension.targets",
        )
        if not targets:
            raise DescriptorModelError(
                "host_extension.targets cannot be empty"
            )
        unknown = sorted(set(targets) - {"node", "browser"})
        if unknown:
            raise DescriptorModelError(
                "host_extension.targets contains unsupported targets: "
                f"{unknown}"
            )
        implementations = tuple(self.implementations)
        if not implementations:
            raise DescriptorModelError(
                "host_extension.implementations cannot be empty"
            )
        if not all(
            isinstance(item, ImplementationDescriptor)
            for item in implementations
        ):
            raise DescriptorModelError(
                "host_extension.implementations must contain "
                "ImplementationDescriptor values"
            )
        if any(item.language == "python" for item in implementations):
            raise DescriptorModelError(
                "host_extension implementations must use JavaScript or TypeScript"
            )
        _validate_implementation_coverage(
            implementations,
            field_name="host_extension.implementations",
        )
        provides = _string_tuple(
            self.provides,
            field_name="host_extension.provides",
        )
        dependencies = _string_tuple(
            self.dependencies,
            field_name="host_extension.dependencies",
        )
        if self.id in dependencies:
            raise DescriptorModelError(
                "host_extension cannot depend on itself"
            )
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "implementations", implementations)
        object.__setattr__(self, "provides", provides)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(
            self,
            "external_packages",
            _string_tuple(
                self.external_packages,
                field_name="host_extension.external_packages",
            ),
        )
        object.__setattr__(
            self,
            "display_name",
            str(self.display_name or "").strip(),
        )
        object.__setattr__(
            self,
            "description",
            str(self.description or "").strip(),
        )
        object.__setattr__(self, "version", str(self.version or "").strip())

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "host_extension",
            "id": self.id,
            "targets": list(self.targets),
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "implementations": [
                item.to_dict() for item in self.implementations
            ],
            "provides": list(self.provides),
            "dependencies": list(self.dependencies),
            "external_packages": list(self.external_packages),
        }


@dataclass(frozen=True)
class PluginDescriptor:
    """Language-neutral metadata for one plugin implementation family.

    The descriptor contains only frozen values and source locators.  Loading a
    module, constructing a plugin, or retaining a Target-specific object is a
    Target responsibility.
    """

    id: str
    plugin_type: str
    targets: tuple[str, ...]
    implementations: tuple[ImplementationDescriptor, ...]
    dependencies: tuple[str, ...] = ()
    external_packages: tuple[str, ...] = ()
    config_schema: Mapping[str, Any] = field(default_factory=dict)
    config_defaults: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 100
    display_name: str = ""
    category: str = ""
    description: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        plugin_id = _required_text(self.id, field_name="plugin.id")
        plugin_type = _required_text(
            self.plugin_type,
            field_name="plugin.type",
        ).lower()
        if plugin_type not in PLUGIN_TYPES:
            raise DescriptorModelError(
                f"plugin.type must be one of {sorted(PLUGIN_TYPES)}"
            )
        targets = _string_tuple(self.targets, field_name="plugin.targets")
        if not targets:
            raise DescriptorModelError("plugin.targets cannot be empty")
        unknown_targets = sorted(set(targets) - {"python", "node", "browser"})
        if unknown_targets:
            raise DescriptorModelError(
                "plugin.targets contains unsupported targets: "
                f"{unknown_targets}"
            )
        implementations = tuple(self.implementations)
        if not implementations:
            raise DescriptorModelError(
                "plugin.implementations cannot be empty"
            )
        if not all(
            isinstance(item, ImplementationDescriptor)
            for item in implementations
        ):
            raise DescriptorModelError(
                "plugin.implementations must contain "
                "ImplementationDescriptor values"
            )
        _validate_implementation_coverage(
            implementations,
            field_name="plugin.implementations",
        )
        implementation_targets = {
            target
            for implementation in implementations
            for target in implementation.targets
        }
        if set(targets) != implementation_targets:
            raise DescriptorModelError(
                "plugin.targets must exactly match implementation target coverage"
            )
        dependencies = _string_tuple(
            self.dependencies,
            field_name="plugin.dependencies",
        )
        if plugin_id in dependencies:
            raise DescriptorModelError("plugin cannot depend on itself")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise DescriptorModelError("plugin.priority must be an integer")
        object.__setattr__(self, "id", plugin_id)
        object.__setattr__(self, "plugin_type", plugin_type)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "implementations", implementations)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(
            self,
            "external_packages",
            _string_tuple(
                self.external_packages,
                field_name="plugin.external_packages",
            ),
        )
        object.__setattr__(
            self,
            "config_schema",
            _freeze_mapping(
                self.config_schema,
                field_name="plugin.config_schema",
            ),
        )
        object.__setattr__(
            self,
            "config_defaults",
            _freeze_mapping(
                self.config_defaults,
                field_name="plugin.config_defaults",
            ),
        )
        object.__setattr__(self, "display_name", str(self.display_name or "").strip())
        object.__setattr__(self, "category", str(self.category or "").strip())
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "version", str(self.version or "").strip())

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "plugin",
            "id": self.id,
            "type": self.plugin_type,
            "targets": list(self.targets),
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "priority": self.priority,
            "implementations": [
                item.to_dict() for item in self.implementations
            ],
            "dependencies": list(self.dependencies),
            "external_packages": list(self.external_packages),
            "config": {
                "schema": _thaw_json(self.config_schema),
                "defaults": _thaw_json(self.config_defaults),
            },
        }
