from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


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


class BoundaryRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, type[GlobalBoundary]] = {}

    def register(
        self,
        key: str,
        boundary_cls: type[GlobalBoundary] | None = None,
        *,
        overwrite: bool = False,
    ) -> type[GlobalBoundary] | Callable[[type[GlobalBoundary]], type[GlobalBoundary]]:
        if boundary_cls is None:
            def decorator(cls: type[GlobalBoundary]) -> type[GlobalBoundary]:
                self._register(key, cls, overwrite=overwrite)
                return cls
            return decorator
        self._register(key, boundary_cls, overwrite=overwrite)
        return boundary_cls

    def _register(self, key: str, boundary_cls: type[GlobalBoundary], *, overwrite: bool) -> None:
        normalized = str(key).strip()
        if not normalized:
            raise BoundaryRegistryError("boundary registry key cannot be empty")
        _validate_boundary_class(boundary_cls)
        setattr(boundary_cls, "__topology_boundary__", True)
        if normalized in self._registry and not overwrite:
            raise BoundaryRegistryError(f"key already registered: {normalized}")
        self._registry[normalized] = boundary_cls

    def get(self, key: str) -> type[GlobalBoundary]:
        normalized = str(key).strip()
        try:
            return self._registry[normalized]
        except KeyError as exc:
            raise BoundaryRegistryError(f"unknown boundary key '{normalized}'") from exc

    def available(self) -> list[str]:
        return sorted(self._registry)


def _validate_boundary_class(boundary_cls: type[GlobalBoundary]) -> None:
    for method in ("before_run", "after_run", "before_iteration", "after_iteration"):
        if not callable(getattr(boundary_cls, method, None)):
            raise BoundaryRegistryError(f"boundary class must define {method}")


GLOBAL_BOUNDARY_REGISTRY = BoundaryRegistry()
