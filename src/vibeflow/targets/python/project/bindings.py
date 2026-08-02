"""Opaque Python implementation bindings kept beside the portable plan.

The public ``WorkflowPlan``/``BlockPlan`` records only language-neutral
``SourceRef`` values.  This module keeps the live Python objects required by
the Python target without making them part of that portable intermediate
representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from types import (
    BuiltinFunctionType,
    BuiltinMethodType,
    FunctionType,
    MappingProxyType,
    MethodType,
    ModuleType,
)
from typing import Any, Mapping

from vibeflow.block_compiler.model import SourceRef


class PythonBindingError(ValueError):
    """Raised when a Python binding sidecar is structurally ambiguous."""


@dataclass(frozen=True)
class PythonCallBinding:
    """Live Python implementation and effective parameters for one call."""

    path: tuple[str, ...]
    type_key: str
    implementation: object = field(compare=False, repr=False)
    effective_params: Mapping[str, object] = field(compare=False, repr=False)
    source: SourceRef
    source_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _binding_path(self.path))
        object.__setattr__(self, "type_key", _required_text(self.type_key, "type_key"))
        if self.implementation is None:
            raise PythonBindingError("implementation cannot be None")
        if not isinstance(self.source, SourceRef):
            raise PythonBindingError("source must be a SourceRef")
        if not isinstance(self.source_hash, str):
            raise PythonBindingError("source_hash must be a string")
        if not isinstance(self.effective_params, Mapping):
            raise PythonBindingError("effective_params must be a mapping")
        frozen = _freeze_mapping(
            self.effective_params,
            path="effective_params",
            active=set(),
        )
        object.__setattr__(self, "effective_params", frozen)

    def to_metadata(self) -> dict[str, object]:
        """Return deterministic JSON-safe metadata without executing objects."""

        return {
            "path": list(self.path),
            "type_key": self.type_key,
            "implementation": _stable_python_reference(self.implementation),
            "effective_params": _metadata_value(
                self.effective_params,
                active=set(),
            ),
            "source": self.source.to_dict(),
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True)
class PythonBindingPlan:
    """Recursive Python-only sidecar corresponding to portable blocks."""

    block_id: str
    calls: tuple[PythonCallBinding, ...] = ()
    children: tuple["PythonBindingPlan", ...] = ()
    plugin_registry: object | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _required_text(self.block_id, "block_id"))
        calls = tuple(self.calls)
        children = tuple(self.children)
        if not all(isinstance(item, PythonCallBinding) for item in calls):
            raise PythonBindingError("calls must contain PythonCallBinding values")
        if not all(isinstance(item, PythonBindingPlan) for item in children):
            raise PythonBindingError("children must contain PythonBindingPlan values")
        child_ids = tuple(child.block_id for child in children)
        if len(set(child_ids)) != len(child_ids):
            raise PythonBindingError("children contain duplicate block_id values")
        object.__setattr__(self, "calls", calls)
        object.__setattr__(self, "children", children)
        paths = [binding.path for binding in self.all_bindings()]
        if len(set(paths)) != len(paths):
            raise PythonBindingError("binding paths must be unique across children")

    def get(self, path: tuple[str, ...]) -> PythonCallBinding | None:
        normalized = _binding_path(path)
        for binding in self.calls:
            if binding.path == normalized:
                return binding
        for child in self.children:
            found = child.get(normalized)
            if found is not None:
                return found
        return None

    def binding(self, path: tuple[str, ...]) -> PythonCallBinding:
        found = self.get(path)
        if found is None:
            raise KeyError(".".join(path))
        return found

    def all_bindings(self) -> tuple[PythonCallBinding, ...]:
        return (
            *self.calls,
            *(
                binding
                for child in self.children
                for binding in child.all_bindings()
            ),
        )

    def to_metadata(self) -> dict[str, object]:
        """Project the sidecar to deterministic ordinary metadata."""

        return {
            "block_id": self.block_id,
            "calls": [
                binding.to_metadata()
                for binding in sorted(self.calls, key=lambda item: item.path)
            ],
            "children": [
                child.to_metadata()
                for child in sorted(self.children, key=lambda item: item.block_id)
            ],
            "plugin_registry": (
                None
                if self.plugin_registry is None
                else _stable_python_reference(self.plugin_registry)
            ),
        }


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise PythonBindingError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise PythonBindingError(f"{label} must be a non-empty string")
    return normalized


def _binding_path(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise PythonBindingError("binding path must be a non-empty tuple")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise PythonBindingError("binding path entries must be non-empty strings")
    return tuple(item.strip() for item in value)


def _freeze_mapping(
    value: Mapping[str, object],
    *,
    path: str,
    active: set[int],
) -> Mapping[str, object]:
    object_id = id(value)
    if object_id in active:
        raise PythonBindingError(f"{path} contains a circular mapping")
    keys = tuple(value)
    if not all(isinstance(key, str) for key in keys):
        raise PythonBindingError(f"{path} contains a non-string mapping key")
    active.add(object_id)
    try:
        frozen = {
            key: _freeze_value(value[key], path=f"{path}.{key}", active=active)
            for key in sorted(keys)
        }
    finally:
        active.remove(object_id)
    return MappingProxyType(frozen)


def _freeze_value(value: object, *, path: str, active: set[int]) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value, path=path, active=active)
    if isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in active:
            raise PythonBindingError(f"{path} contains a circular sequence")
        active.add(object_id)
        try:
            return tuple(
                _freeze_value(item, path=f"{path}[{index}]", active=active)
                for index, item in enumerate(value)
            )
        finally:
            active.remove(object_id)
    if isinstance(value, (set, frozenset)):
        return frozenset(value)
    return value


def _metadata_value(value: object, *, active: set[int]) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"$python": {"kind": "float", "value": str(value)}}
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in active:
            raise PythonBindingError("metadata contains a circular mapping")
        active.add(object_id)
        try:
            return {
                key: _metadata_value(value[key], active=active)
                for key in sorted(value)
            }
        finally:
            active.remove(object_id)
    if isinstance(value, tuple):
        return [_metadata_value(item, active=active) for item in value]
    if isinstance(value, frozenset):
        items = [_metadata_value(item, active=active) for item in value]
        return {
            "$python": {
                "kind": "set",
                "items": sorted(items, key=_metadata_sort_key),
            }
        }
    if isinstance(value, bytes):
        return {"$python": {"kind": "bytes", "hex": value.hex()}}
    return {"$python": _stable_python_reference(value)}


def _metadata_sort_key(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_python_reference(value: object) -> dict[str, object]:
    if isinstance(value, type):
        return {"kind": "type", **_type_reference(value)}
    if isinstance(value, FunctionType):
        return _named_reference("function", value)
    if isinstance(value, (BuiltinFunctionType, BuiltinMethodType)):
        return _named_reference("builtin", value)
    if isinstance(value, MethodType):
        return {
            "kind": "bound_method",
            "function": _named_reference("function", value.__func__),
            "owner": _type_reference(type(value.__self__)),
        }
    if isinstance(value, ModuleType):
        return {
            "kind": "module",
            "module": object.__getattribute__(value, "__name__"),
        }
    return {"kind": "instance", "type": _type_reference(type(value))}


def _named_reference(kind: str, value: object) -> dict[str, object]:
    return {
        "kind": kind,
        "module": getattr(value, "__module__", ""),
        "qualname": getattr(value, "__qualname__", getattr(value, "__name__", "")),
    }


def _type_reference(value: type[object]) -> dict[str, str]:
    return {
        "module": type.__getattribute__(value, "__module__"),
        "qualname": type.__getattribute__(value, "__qualname__"),
    }


__all__ = [
    "PythonBindingError",
    "PythonBindingPlan",
    "PythonCallBinding",
]
