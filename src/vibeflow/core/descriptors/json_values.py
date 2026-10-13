"""Public conversion between ordinary JSON data and read-only JSON values.

Both conversions create independent containers. Read-only settings remain
protected when an editable/serializable copy is requested with thaw_json.
This module has no dependency on descriptor models or Target implementations.
"""
from __future__ import annotations

import math
from types import MappingProxyType
from typing import Any, Mapping

__all__ = ["DescriptorModelError", "freeze_json", "freeze_mapping", "thaw_json"]


class DescriptorModelError(ValueError):
    """Raised when a descriptor cannot be normalized safely."""


def freeze_json(value: Any, *, field_name: str = "value") -> Any:
    """Copy a JSON tree into read-only mappings and tuples at every depth."""
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DescriptorModelError(f"{field_name} object keys must be strings")
            frozen[key] = freeze_json(item, field_name=f"{field_name}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(
            freeze_json(item, field_name=f"{field_name}[{index}]")
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


def freeze_mapping(value: object, *, field_name: str = "value") -> Mapping[str, Any]:
    """Freeze a JSON object; None means an empty object for optional settings."""
    if value in (None, {}):
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise DescriptorModelError(f"{field_name} must be an object")
    frozen = freeze_json(value, field_name=field_name)
    assert isinstance(frozen, Mapping)
    return frozen


def thaw_json(value: Any) -> Any:
    """Copy a JSON tree into ordinary dicts/lists without changing the original."""
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_json(item) for item in value]
    return value


