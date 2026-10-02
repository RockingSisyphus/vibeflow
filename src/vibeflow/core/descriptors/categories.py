"""Portable business categories and explicit contribution bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.core.descriptors.models import (
    DescriptorModelError, _freeze_mapping, _required_text, _string_tuple, _thaw_json,
)
from vibeflow.core.style import NODE_SHAPES, is_hex_color


PRESENTATION_FIELDS = frozenset({"fill", "stroke", "text", "shape", "icon"})


def normalize_presentation(value: object, *, field_name: str) -> Mapping[str, Any]:
    result = _freeze_mapping(value, field_name=field_name)
    unknown = set(result) - PRESENTATION_FIELDS
    if unknown:
        raise DescriptorModelError(f"{field_name} has unknown fields: {sorted(unknown)}")
    for name in ("fill", "stroke", "text"):
        if name in result and not is_hex_color(result[name]):
            raise DescriptorModelError(f"{field_name}.{name} must be a six-digit hex color")
    if "shape" in result and result["shape"] not in NODE_SHAPES:
        raise DescriptorModelError(f"{field_name}.shape must be one of {sorted(NODE_SHAPES)}")
    if "icon" in result:
        _required_text(result["icon"], field_name=f"{field_name}.icon")
    return result


@dataclass(frozen=True)
class NodeCategoryDescriptor:
    id: str
    display_name: str = ""
    description: str = ""
    default_rulesets: tuple[str, ...] = ()
    presentation: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, field_name="category.id"))
        object.__setattr__(self, "default_rulesets", _string_tuple(self.default_rulesets, field_name="category.default_rulesets"))
        object.__setattr__(self, "presentation", normalize_presentation(self.presentation, field_name="category.presentation"))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, field_name="category.metadata"))

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "node_category", "id": self.id, "display_name": self.display_name,
            "description": self.description, "default_rulesets": list(self.default_rulesets),
            "presentation": _thaw_json(self.presentation), "metadata": _thaw_json(self.metadata),
        }


BUNDLE_RESOURCE_GROUPS = (
    "categories", "nodes", "rules", "rulesets", "base_lib", "data_schemas",
    "capabilities", "host_extensions", "plugins", "bundles",
)


@dataclass(frozen=True)
class ContributionBundle:
    """Explicit resource file references, resolved relative to the bundle file."""

    id: str
    resources: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, field_name="bundle.id"))
        if not isinstance(self.resources, Mapping):
            raise DescriptorModelError("bundle.resources must be an object")
        unknown = set(self.resources) - set(BUNDLE_RESOURCE_GROUPS)
        if unknown:
            raise DescriptorModelError(f"bundle.resources has unknown groups: {sorted(unknown)}")
        resources = {name: _string_tuple(value, field_name=f"bundle.resources.{name}") for name, value in self.resources.items()}
        object.__setattr__(self, "resources", _freeze_mapping(resources, field_name="bundle.resources"))

    def to_dict(self) -> dict[str, object]:
        return {"kind": "bundle", "id": self.id, "description": self.description, "resources": _thaw_json(self.resources)}


def selected_node_rulesets(node: object, categories: object) -> tuple[str, ...]:
    """An explicit empty selection stays empty; identity never grants permissions."""
    selection = getattr(node, "rulesets", None)
    if selection is not None:
        return tuple(selection)
    category = categories.get(getattr(node, "category", ""))
    return tuple(category.default_rulesets) if category is not None else ()
