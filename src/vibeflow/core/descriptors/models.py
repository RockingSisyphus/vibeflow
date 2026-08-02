from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from vibeflow.core.constants import FLOW_KINDS
from vibeflow.core.contracts import CARDINALITIES, DataProvider, DataRequirement


JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
IMPLEMENTATION_LANGUAGES = frozenset({"python", "javascript", "typescript"})
IMPLEMENTATION_TARGETS = frozenset({"python", "node", "browser"})
IMPLEMENTATION_COMPLETIONS = frozenset({"immediate", "suspend"})
SOURCE_LOCATOR_KINDS = frozenset({"module", "file", "package", "generated"})


class DescriptorModelError(ValueError):
    """Raised when a descriptor cannot be normalized safely."""


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DescriptorModelError(f"{field_name} must be a non-empty string")
    return text


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple(value: object, *, field_name: str, unique: bool = True) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (tuple, list, set, frozenset)):
        raise DescriptorModelError(f"{field_name} must be a list of strings")
    normalized = tuple(_required_text(item, field_name=field_name) for item in value)
    if unique and len(set(normalized)) != len(normalized):
        raise DescriptorModelError(f"{field_name} contains duplicate values")
    return normalized


def _freeze_json(value: Any, *, field_name: str) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DescriptorModelError(f"{field_name} object keys must be strings")
            frozen[key] = _freeze_json(item, field_name=f"{field_name}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(
            _freeze_json(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DescriptorModelError(f"{field_name} must contain finite JSON numbers")
        return value
    raise DescriptorModelError(
        f"{field_name} must contain JSON values, got {type(value).__name__}"
    )


def _freeze_mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if value in (None, {}):
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise DescriptorModelError(f"{field_name} must be an object")
    frozen = _freeze_json(value, field_name=field_name)
    assert isinstance(frozen, Mapping)
    return frozen


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _semantic_mapping(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, tuple[str, ...]]:
    if value in (None, {}):
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise DescriptorModelError(f"{field_name} must be an object")
    normalized: dict[str, tuple[str, ...]] = {}
    for key, item in value.items():
        text_key = _required_text(key, field_name=f"{field_name} key")
        normalized[text_key] = _string_tuple(
            item,
            field_name=f"{field_name}.{text_key}",
            unique=False,
        )
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class SourceLocator:
    """A language-neutral pointer to implementation source."""

    kind: str
    ref: str
    export: str | None = None

    def __post_init__(self) -> None:
        kind = _required_text(self.kind, field_name="source.kind")
        if kind not in SOURCE_LOCATOR_KINDS:
            raise DescriptorModelError(
                f"source.kind must be one of {sorted(SOURCE_LOCATOR_KINDS)}"
            )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "ref", _required_text(self.ref, field_name="source.ref"))
        object.__setattr__(self, "export", _optional_text(self.export))

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind, "ref": self.ref}
        if self.export is not None:
            payload["export"] = self.export
        return payload


@dataclass(frozen=True)
class ImplementationDescriptor:
    language: str
    targets: tuple[str, ...]
    source: SourceLocator
    completion: str = "immediate"

    def __post_init__(self) -> None:
        language = _required_text(self.language, field_name="implementation.language")
        if language == "js":
            language = "javascript"
        elif language == "ts":
            language = "typescript"
        if language not in IMPLEMENTATION_LANGUAGES:
            raise DescriptorModelError(
                "implementation.language must be one of "
                f"{sorted(IMPLEMENTATION_LANGUAGES)}"
            )
        targets = _string_tuple(
            self.targets,
            field_name="implementation.targets",
        )
        if not targets:
            raise DescriptorModelError("implementation.targets cannot be empty")
        unknown = sorted(set(targets) - IMPLEMENTATION_TARGETS)
        if unknown:
            raise DescriptorModelError(
                f"implementation.targets contains unsupported targets: {unknown}"
            )
        if not isinstance(self.source, SourceLocator):
            raise DescriptorModelError(
                "implementation.source must be a SourceLocator"
            )
        if language == "python" and targets != ("python",):
            raise DescriptorModelError(
                "python implementations must target only 'python'"
            )
        if language != "python" and "python" in targets:
            raise DescriptorModelError(
                "JavaScript/TypeScript implementations cannot target 'python'"
            )
        completion = _required_text(
            self.completion,
            field_name="implementation.completion",
        )
        if completion not in IMPLEMENTATION_COMPLETIONS:
            raise DescriptorModelError(
                "implementation.completion must be one of "
                f"{sorted(IMPLEMENTATION_COMPLETIONS)}"
            )
        if language == "python" and completion != "immediate":
            raise DescriptorModelError(
                "Python implementations currently support only immediate completion"
            )
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "completion", completion)

    @property
    def source_locator(self) -> SourceLocator:
        return self.source

    def to_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "targets": list(self.targets),
            "source": self.source.to_dict(),
            "completion": self.completion,
        }


@dataclass(frozen=True)
class NodeContractDescriptor:
    requires: tuple[DataRequirement, ...] = ()
    provides: tuple[DataProvider, ...] = ()
    input_semantics: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    output_semantics: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    params_schema: Mapping[str, Any] = field(default_factory=dict)
    params_defaults: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    examples: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        requires = tuple(self.requires)
        provides = tuple(self.provides)
        if not all(isinstance(item, DataRequirement) for item in requires):
            raise DescriptorModelError(
                "contract.requires must contain DataRequirement values"
            )
        if not all(isinstance(item, DataProvider) for item in provides):
            raise DescriptorModelError(
                "contract.provides must contain DataProvider values"
            )
        requirement_types = tuple(item.type for item in requires)
        provider_keys = tuple(item.key for item in provides)
        if len(set(requirement_types)) != len(requirement_types):
            raise DescriptorModelError(
                "contract.requires contains duplicate data types"
            )
        if len(set(provider_keys)) != len(provider_keys):
            raise DescriptorModelError(
                "contract.provides contains duplicate provider keys"
            )
        for requirement in requires:
            if requirement.cardinality not in CARDINALITIES:
                raise DescriptorModelError(
                    f"unsupported requirement cardinality: {requirement.cardinality}"
                )
        examples = tuple(
            _freeze_mapping(item, field_name=f"contract.examples[{index}]")
            for index, item in enumerate(self.examples)
        )
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "provides", provides)
        object.__setattr__(
            self,
            "input_semantics",
            _semantic_mapping(
                self.input_semantics,
                field_name="contract.input_semantics",
            ),
        )
        object.__setattr__(
            self,
            "output_semantics",
            _semantic_mapping(
                self.output_semantics,
                field_name="contract.output_semantics",
            ),
        )
        object.__setattr__(
            self,
            "params_schema",
            _freeze_mapping(
                self.params_schema,
                field_name="contract.params_schema",
            ),
        )
        object.__setattr__(
            self,
            "params_defaults",
            _freeze_mapping(
                self.params_defaults,
                field_name="contract.params_defaults",
            ),
        )
        object.__setattr__(
            self,
            "output_schema",
            _freeze_mapping(
                self.output_schema,
                field_name="contract.output_schema",
            ),
        )
        object.__setattr__(self, "examples", examples)

    def to_dict(self) -> dict[str, object]:
        return {
            "requires": [item.to_dict() for item in self.requires],
            "provides": [item.to_dict() for item in self.provides],
            "input_semantics": {
                key: list(value) for key, value in self.input_semantics.items()
            },
            "output_semantics": {
                key: list(value) for key, value in self.output_semantics.items()
            },
            "params_schema": _thaw_json(self.params_schema),
            "params_defaults": _thaw_json(self.params_defaults),
            "output_schema": _thaw_json(self.output_schema),
            "examples": [_thaw_json(item) for item in self.examples],
        }


@dataclass(frozen=True)
class CapabilityRequirementDescriptor:
    id: str
    operations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _required_text(self.id, field_name="capability requirement id"),
        )
        operations = _string_tuple(
            self.operations,
            field_name="capability requirement operations",
        )
        if not operations:
            raise DescriptorModelError(
                "capability requirement operations cannot be empty"
            )
        object.__setattr__(self, "operations", operations)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "operations": list(self.operations)}


@dataclass(frozen=True)
class NodeDescriptor:
    type_key: str
    display_name: str
    category: str
    description: str
    version: str
    flow_kind: str
    contract: NodeContractDescriptor
    implementations: tuple[ImplementationDescriptor, ...] = ()
    base_libs: tuple[str, ...] = ()
    capabilities: tuple[CapabilityRequirementDescriptor, ...] = ()
    purity: str = "pure"
    author: str | None = None
    tags: tuple[str, ...] = ()
    external: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "type_key",
            _required_text(self.type_key, field_name="node.type_key"),
        )
        object.__setattr__(
            self,
            "display_name",
            _required_text(self.display_name, field_name="node.display_name"),
        )
        object.__setattr__(self, "category", str(self.category or "").strip())
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, field_name="node.description"),
        )
        object.__setattr__(
            self,
            "version",
            _required_text(self.version, field_name="node.version"),
        )
        flow_kind = _required_text(self.flow_kind, field_name="node.flow_kind")
        if flow_kind not in FLOW_KINDS:
            raise DescriptorModelError(
                f"node.flow_kind must be one of {sorted(FLOW_KINDS)}"
            )
        object.__setattr__(self, "flow_kind", flow_kind)
        if not isinstance(self.contract, NodeContractDescriptor):
            raise DescriptorModelError(
                "node.contract must be a NodeContractDescriptor"
            )
        implementations = tuple(self.implementations)
        if not all(
            isinstance(item, ImplementationDescriptor)
            for item in implementations
        ):
            raise DescriptorModelError(
                "node.implementations must contain ImplementationDescriptor values"
            )
        _validate_implementation_coverage(
            implementations,
            field_name="node.implementations",
        )
        capabilities = tuple(self.capabilities)
        if not all(
            isinstance(item, CapabilityRequirementDescriptor)
            for item in capabilities
        ):
            raise DescriptorModelError(
                "node.capabilities must contain CapabilityRequirementDescriptor values"
            )
        capability_ids = tuple(item.id for item in capabilities)
        if len(set(capability_ids)) != len(capability_ids):
            raise DescriptorModelError(
                "node.capabilities contains duplicate capability ids"
            )
        if not isinstance(self.external, bool):
            raise DescriptorModelError("node.external must be a boolean")
        object.__setattr__(self, "implementations", implementations)
        object.__setattr__(
            self,
            "base_libs",
            _string_tuple(self.base_libs, field_name="node.base_libs"),
        )
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(
            self,
            "purity",
            _required_text(self.purity, field_name="node.purity"),
        )
        object.__setattr__(self, "author", _optional_text(self.author))
        object.__setattr__(
            self,
            "tags",
            _string_tuple(self.tags, field_name="node.tags"),
        )

    @property
    def id(self) -> str:
        return self.type_key

    @property
    def required_base_libs(self) -> tuple[str, ...]:
        return self.base_libs

    @property
    def required_capabilities(
        self,
    ) -> tuple[CapabilityRequirementDescriptor, ...]:
        return self.capabilities

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": "node",
            "type_key": self.type_key,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "flow_kind": self.flow_kind,
            "purity": self.purity,
            "tags": list(self.tags),
            "external": self.external,
            "contract": self.contract.to_dict(),
            "implementations": [
                item.to_dict() for item in self.implementations
            ],
            "base_libs": list(self.base_libs),
            "capabilities": [item.to_dict() for item in self.capabilities],
        }
        if self.author is not None:
            payload["author"] = self.author
        return payload

def _validate_implementation_coverage(
    implementations: tuple[ImplementationDescriptor, ...],
    *,
    field_name: str,
) -> None:
    seen: dict[str, ImplementationDescriptor] = {}
    for implementation in implementations:
        for target in implementation.targets:
            previous = seen.get(target)
            if previous is not None:
                raise DescriptorModelError(
                    f"{field_name} has multiple implementations for target "
                    f"'{target}'"
                )
            seen[target] = implementation


from vibeflow.core.descriptors._resource_models import (  # noqa: E402
    BaseLibDescriptor,
    CapabilityDescriptor,
    CapabilityOperationDescriptor,
    DataSchemaDescriptor,
    HostExtensionDescriptor,
)

CapabilityOperation = CapabilityOperationDescriptor
CapabilityRequirement = CapabilityRequirementDescriptor
