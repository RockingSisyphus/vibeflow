from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .registry_base import RegistryBase


class GlobalBoundary(Protocol):
    def before_run(self, run_config: Mapping[str, object]) -> Mapping[str, object]:
        ...

    def after_run(self, outputs: Mapping[str, object], run_config: Mapping[str, object]) -> Mapping[str, object]:
        ...

    def before_iteration(self, iteration: int, state: Mapping[str, object]) -> Mapping[str, object]:
        ...

    def after_iteration(
        self,
        iteration: int,
        outputs: Mapping[str, object],
        state: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...


@dataclass(frozen=True)
class BoundarySpec:
    boundary_type: str
    config: Mapping[str, object] = field(default_factory=dict)
    consumes: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()


@dataclass
class BoundaryRegistryError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Boundary registry error: {self.detail}"


class BoundaryRegistry(RegistryBase[type[GlobalBoundary]]):
    def _validate_value(self, normalized: str, boundary_cls: type[GlobalBoundary]) -> None:
        _validate_boundary_class(boundary_cls)
        setattr(boundary_cls, "__topology_boundary__", True)

    def _empty_key_error(self) -> Exception:
        return BoundaryRegistryError("boundary registry key cannot be empty")

    def _duplicate_error(self, normalized: str) -> Exception:
        return BoundaryRegistryError(f"key already registered: {normalized}")

    def _unknown_error(self, normalized: str) -> Exception:
        return BoundaryRegistryError(f"unknown boundary key '{normalized}'")


def _validate_boundary_class(boundary_cls: type[GlobalBoundary]) -> None:
    for method in ("before_run", "after_run", "before_iteration", "after_iteration"):
        if not callable(getattr(boundary_cls, method, None)):
            raise BoundaryRegistryError(f"boundary class must define {method}")


GLOBAL_BOUNDARY_REGISTRY = BoundaryRegistry()
