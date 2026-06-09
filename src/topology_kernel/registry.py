from __future__ import annotations

from dataclasses import dataclass

from .node import PureNode
from .registry_base import RegistryBase


@dataclass
class NodeRegistryError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Node registry error: {self.detail}"


class NodeRegistry(RegistryBase[type[PureNode]]):
    def _validate_value(self, normalized: str, node_cls: type[PureNode]) -> None:
        if getattr(node_cls, "__topology_boundary__", False) or _looks_boundary_class(node_cls):
            raise NodeRegistryError(f"boundary class cannot be registered as a node: {normalized}")

    def _empty_key_error(self) -> Exception:
        return NodeRegistryError("registry key cannot be empty")

    def _duplicate_error(self, normalized: str) -> Exception:
        return NodeRegistryError(f"key already registered: {normalized}")

    def _unknown_error(self, normalized: str) -> Exception:
        return NodeRegistryError(f"unknown node key '{normalized}'")


GLOBAL_NODE_REGISTRY = NodeRegistry()


def _looks_boundary_class(value: object) -> bool:
    return all(callable(getattr(value, method, None)) for method in ("before_run", "after_run", "before_iteration", "after_iteration"))
