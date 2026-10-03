"""Portable Node presentation values."""

from __future__ import annotations

from typing import Any, Mapping

from vibeflow.core.descriptors.models import (
    DescriptorModelError, _freeze_mapping, _required_text,
)
from vibeflow.core.style import NODE_SHAPES, is_hex_color, is_reserved_system_color


PRESENTATION_FIELDS = frozenset({"fill", "stroke", "text", "shape", "icon"})


def normalize_presentation(value: object, *, field_name: str) -> Mapping[str, Any]:
    result = _freeze_mapping(value, field_name=field_name)
    unknown = set(result) - PRESENTATION_FIELDS
    if unknown:
        raise DescriptorModelError(f"{field_name} has unknown fields: {sorted(unknown)}")
    for name in ("fill", "stroke", "text"):
        if name in result and not is_hex_color(result[name]):
            raise DescriptorModelError(f"{field_name}.{name} must be a six-digit hex color")
        if name in result and is_reserved_system_color(result[name]):
            raise DescriptorModelError(f"{field_name}.{name} uses a reserved system color")
    if "shape" in result and (not isinstance(result["shape"], str) or result["shape"] not in NODE_SHAPES):
        raise DescriptorModelError(f"{field_name}.shape must be one of {sorted(NODE_SHAPES)}")
    if "icon" in result:
        _required_text(result["icon"], field_name=f"{field_name}.icon")
    return result
