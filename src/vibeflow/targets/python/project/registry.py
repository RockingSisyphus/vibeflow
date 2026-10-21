"""Canonical declarations and delayed Python implementation bindings."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any, Callable, Mapping

from vibeflow.core.config.node import NodeConfigError, NodeConfigSpec, normalize_node_config_spec
from vibeflow.core.config.concurrency import merge_call_config
from vibeflow.core.descriptors.models import NodeDescriptor


@dataclass
class NodeRegistryError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Node registry error: {self.detail}"


def load_node_implementation(registry, key, path, symbol, loader):
    """Bind a declared class with one source-aware error contract."""
    try:
        implementation = loader()
        if not isinstance(implementation, type):
            raise NodeRegistryError(f"declared Python symbol '{symbol}' must be a class")
        return implementation
    except Exception as cause:
        from vibeflow.core.findings import HealthFinding
        info = registry.source_info(key)
        error = NodeRegistryError(f"node '{key}' implementation '{symbol}' could not be bound: {cause}")
        error.findings = (HealthFinding(rule_id="NODE.IMPLEMENTATION.BINDING",severity="error",
            object_type="node",object_id=key,failure_layer="implementation",message=str(error),
            source_location={"path":info.path, **({"line":info.line} if info.line else {})},
            details={"implementation":{"path":str(path),"export":symbol}}),)
        raise error from cause


@dataclass(frozen=True)
class NodeRegistrationInfo:
    key: str
    function: str
    path: str
    line: int


class NodeRegistry:
    """Register metadata without importing project implementations.

    Classes provide execution only. All contracts, metadata, configuration and
    rule selections come from the declared NodeDescriptor.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, NodeDescriptor] = {}
        self._registry: dict[str, type] = {}
        self._loaders: dict[str, Callable[[], type]] = {}
        self._registration_info: dict[str, NodeRegistrationInfo] = {}
        self._config_specs: dict[str, NodeConfigSpec] = {}
        self.source_namespaces = {}
        self.rule_catalogs: tuple[object, ...] = ()
        self.rule_handler_loader = None
        self._effect_policies: dict[str, str] = {}
        self.call_effect_scopes: dict[tuple[str, ...], str] = {}
        self.call_capability_policies: dict[tuple[str, ...], object] = {}
        self.rule_policy_resolver: Callable[[str], str] | None = None
        self._rule_defaults: dict[str, object] = {"purity_policy":None,"quality_policy":None}

    def configure_rule_defaults(self, *, purity_policy=None, quality_policy=None) -> None:
        """Carry the current check's numeric defaults into delayed imports."""
        self._rule_defaults = {"purity_policy":purity_policy,"quality_policy":quality_policy}

    def rule_defaults(self) -> Mapping[str, object]:
        return dict(self._rule_defaults)

    def register(self, descriptor: NodeDescriptor, implementation: type | None = None, *, loader: Callable[[], type] | None = None, source: str = "", source_line: int | None = None, overwrite: bool = False) -> NodeDescriptor:
        if not isinstance(descriptor, NodeDescriptor):
            raise NodeRegistryError("registration requires a NodeDescriptor; class metadata and registry factories are not declarations")
        key = descriptor.id
        if key in self._descriptors and not overwrite:
            raise NodeRegistryError(f"key already registered: {key}")
        if implementation is not None and loader is not None:
            raise NodeRegistryError("provide an implementation or a delayed loader, not both")
        config_spec = normalize_node_config_spec(descriptor.contract.params_schema, descriptor.contract.params_defaults)
        self._descriptors[key] = descriptor
        self._effect_policies.pop(key,None)
        self._registry.pop(key, None)
        self._loaders.pop(key, None)
        if implementation is not None:
            self._registry[key] = implementation
        elif loader is not None:
            self._loaders[key] = loader
        self._config_specs[key] = config_spec
        frame = sys._getframe(1)
        self._registration_info[key] = NodeRegistrationInfo(key, "declaration" if source else frame.f_code.co_name, source or frame.f_code.co_filename, (source_line or 1) if source else frame.f_lineno)
        return descriptor

    def descriptor(self, key: str) -> NodeDescriptor:
        try:
            return self._descriptors[str(key).strip()]
        except KeyError as exc:
            raise NodeRegistryError(f"unknown node key '{key}'") from exc

    def get(self, key: str) -> type:
        normalized = self.descriptor(key).id
        if normalized not in self._registry:
            loader = self._loaders.get(normalized)
            if loader is None:
                raise NodeRegistryError(f"node '{normalized}' has no Python implementation binding")
            value = loader()
            if not isinstance(value, type):
                raise NodeRegistryError(f"node '{normalized}' implementation must be a class")
            self._registry[normalized] = value
        return self._registry[normalized]

    def available(self) -> list[str]:
        return sorted(self._descriptors)

    def rulesets(self, key: str) -> tuple[str, ...]:
        return self.descriptor(key).rulesets

    def source_info(self, key: str) -> NodeRegistrationInfo:
        return self._registration_info[self.descriptor(key).id]

    def effect_scope(self, key: str) -> str:
        """Describe a selected rule policy; this never grants OS permissions."""
        self.descriptor(key)
        if key in self._effect_policies:
            return self._effect_policies[key]
        if self.rule_policy_resolver is not None:
            return self.rule_policy_resolver(key)
        from vibeflow.targets.python.quality.rule_adapter import selected_effect_scope
        return selected_effect_scope(self, key)

    def record_effect_policy(self, key: str, scope: str) -> None:
        self.descriptor(key)
        self._effect_policies[key] = scope

    def reset_effect_policies(self, keys) -> None:
        self.call_effect_scopes.clear()
        for key in keys:
            self._effect_policies.pop(key,None)

    def get_config_spec(self, key: str) -> NodeConfigSpec:
        return self._config_specs[self.descriptor(key).id]

    def merge_config(self, key: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        try:
            return merge_call_config(self.get_config_spec(key), overrides)
        except NodeConfigError as exc:
            raise NodeRegistryError(str(exc)) from exc

    def registration_info(self) -> tuple[NodeRegistrationInfo, ...]:
        return tuple(self._registration_info[key] for key in self.available())




@dataclass(frozen=True, init=False)
class NodeRegistryQueries:
    """A snapshot of read-only declaration queries exposed to rule handlers."""

    def __init__(self, registry):
        from types import MappingProxyType
        from dataclasses import replace
        from vibeflow.core.rules.models import readonly
        object.__setattr__(self,'_descriptors',MappingProxyType({key:registry.descriptor(key) for key in registry.available()}))
        object.__setattr__(self,'_sources',MappingProxyType({key:registry.source_info(key) for key in registry.available()}))
        object.__setattr__(self,'_configs',MappingProxyType({key:replace(registry.get_config_spec(key),
            schema=readonly(registry.get_config_spec(key).schema),defaults=readonly(registry.get_config_spec(key).defaults)) for key in registry.available()}))
        object.__setattr__(self,'_effects',MappingProxyType({key:registry.effect_scope(key) for key in registry.available()}))
        object.__setattr__(self,'_rulesets',MappingProxyType({key:registry.rulesets(key) for key in registry.available()}))
        object.__setattr__(self,'source_context_snapshot',getattr(registry,"source_context_snapshot",None))
        object.__setattr__(self, "call_effect_scopes", MappingProxyType(dict(registry.call_effect_scopes)))
        object.__setattr__(self, "call_capability_policies", readonly(registry.call_capability_policies))

    def descriptor(self,key):
        return self._descriptors[key]

    def available(self):
        return tuple(sorted(self._descriptors))

    def get_config_spec(self,key):
        return self._configs[key]

    def merge_config(self,key,overrides):
        from vibeflow.core.rules.models import readonly
        try:
            return readonly(merge_call_config(self.get_config_spec(key),overrides))
        except NodeConfigError as exc:
            raise NodeRegistryError(str(exc)) from exc

    def effect_scope(self,key):
        return self._effects[key]

    def rulesets(self,key):
        return self._rulesets[key]

    def source_info(self,key):
        return self._sources[key]

    def registration_info(self):
        return tuple(self._sources[key] for key in self.available())
