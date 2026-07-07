from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable, Mapping

from vibeflow.node_config import NodeConfigError, NodeConfigSpec, merge_node_config, normalize_node_config_spec
from vibeflow.node import PureNode
from vibeflow.registry_base import RegistryBase


@dataclass
class NodeRegistryError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Node registry error: {self.detail}"


@dataclass(frozen=True)
class NodeRegistrationInfo:
    key: str
    function: str
    path: str
    line: int


class NodeRegistry(RegistryBase[type[PureNode]]):
    def __init__(self) -> None:
        super().__init__()
        self._config_specs: dict[str, NodeConfigSpec] = {}
        self._registration_info: dict[str, NodeRegistrationInfo] = {}

    def register(
        self,
        key: str,
        value: type[PureNode] | None = None,
        *,
        config_schema: Mapping[str, Any] | None = None,
        config_defaults: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> type[PureNode] | Callable[[type[PureNode]], type[PureNode]]:
        config_spec = _config_spec_or_error(config_schema, config_defaults)
        if value is None:
            return self._decorator_for_node(key, config_spec, overwrite=overwrite)
        self._register_node(key, value, config_spec, overwrite=overwrite)
        return value

    def get_config_spec(self, key: str) -> NodeConfigSpec:
        normalized = self._normalize_key(key)
        if normalized not in self._config_specs:
            raise self._unknown_error(normalized)
        return self._config_specs[normalized]

    def merge_config(self, key: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        try:
            return merge_node_config(self.get_config_spec(key), overrides)
        except NodeConfigError as exc:
            raise NodeRegistryError(str(exc)) from exc

    def registration_info(self) -> tuple[NodeRegistrationInfo, ...]:
        return tuple(self._registration_info[key] for key in sorted(self._registration_info))

    def _decorator_for_node(
        self,
        key: str,
        config_spec: NodeConfigSpec,
        *,
        overwrite: bool,
    ) -> Callable[[type[PureNode]], type[PureNode]]:
        def decorator(value: type[PureNode]) -> type[PureNode]:
            self._register_node(key, value, config_spec, overwrite=overwrite)
            return value

        return decorator

    def _register_node(
        self,
        key: str,
        value: type[PureNode],
        config_spec: NodeConfigSpec,
        *,
        overwrite: bool,
    ) -> None:
        normalized = self._normalize_key(key)
        self._validate_value(normalized, value)
        if normalized in self._registry and not overwrite:
            raise self._duplicate_error(normalized)
        self._registry[normalized] = value
        self._config_specs[normalized] = config_spec
        self._registration_info[normalized] = _capture_registration_info(normalized)

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


def _capture_registration_info(key: str) -> NodeRegistrationInfo:
    for frame in inspect.stack(context=0)[2:]:
        if frame.filename.endswith(("registry.py", "registry_base.py")):
            continue
        return NodeRegistrationInfo(key=key, function=frame.function, path=frame.filename, line=frame.lineno)
    return NodeRegistrationInfo(key=key, function="", path="", line=0)


def _config_spec_or_error(
    schema: Mapping[str, Any] | None,
    defaults: Mapping[str, Any] | None,
) -> NodeConfigSpec:
    if schema is None or defaults is None:
        raise NodeRegistryError("node registration requires config_schema and config_defaults")
    try:
        return normalize_node_config_spec(schema, defaults)
    except NodeConfigError as exc:
        raise NodeRegistryError(str(exc)) from exc
