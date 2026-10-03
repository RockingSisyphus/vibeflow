"""Explicit resource file references for trusted extension packages."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping
from vibeflow.core.descriptors.models import (DescriptorModelError, _freeze_mapping, _required_text, _string_tuple, _thaw_json)


BUNDLE_RESOURCE_GROUPS = (
    "nodes", "rules", "rulesets", "base_lib", "data_schemas",
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
