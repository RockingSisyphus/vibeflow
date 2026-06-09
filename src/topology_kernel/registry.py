from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .node import PureNode


@dataclass
class NodeRegistryError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Node registry error: {self.detail}"


class NodeRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, type[PureNode]] = {}

    def register(
        self,
        key: str,
        node_cls: type[PureNode] | None = None,
        *,
        overwrite: bool = False,
    ) -> type[PureNode] | Callable[[type[PureNode]], type[PureNode]]:
        if node_cls is None:
            def decorator(cls: type[PureNode]) -> type[PureNode]:
                self._register(key, cls, overwrite=overwrite)
                return cls
            return decorator
        self._register(key, node_cls, overwrite=overwrite)
        return node_cls

    def _register(self, key: str, node_cls: type[PureNode], *, overwrite: bool) -> None:
        normalized = str(key).strip()
        if not normalized:
            raise NodeRegistryError("registry key cannot be empty")
        if getattr(node_cls, "__topology_boundary__", False) or _looks_boundary_class(node_cls):
            raise NodeRegistryError(f"boundary class cannot be registered as a node: {normalized}")
        if normalized in self._registry and not overwrite:
            raise NodeRegistryError(f"key already registered: {normalized}")
        self._registry[normalized] = node_cls

    def get(self, key: str) -> type[PureNode]:
        normalized = str(key).strip()
        try:
            return self._registry[normalized]
        except KeyError as exc:
            raise NodeRegistryError(f"unknown node key '{normalized}'") from exc

    def available(self) -> list[str]:
        return sorted(self._registry)


GLOBAL_NODE_REGISTRY = NodeRegistry()


def _looks_boundary_class(value: object) -> bool:
    return all(callable(getattr(value, method, None)) for method in ("before_run", "after_run", "before_iteration", "after_iteration"))
