"""In-memory Python plugin protocols and registry semantics.

This module is the Python Target boundary for plugin objects.  It deliberately
does not discover configuration files, alter ``sys.path`` or import project
modules; those operations remain in the outer loading layer.
"""

from __future__ import annotations
from vibeflow.core.rules.selection import selection_refs, selection_data


from contextlib import contextmanager
from dataclasses import dataclass
from typing import Mapping, Protocol

from vibeflow.core.findings import HealthFinding
from vibeflow.core.descriptors import PluginDescriptor as ResourceDescriptor


class CompilerPlugin(Protocol):
    name: str
    priority: int


class RuntimePlugin(Protocol):
    name: str
    priority: int


@dataclass(frozen=True)
class PluginDescriptor:
    name: str
    plugin_type: str
    priority: int
    scope: str
    source: str
    class_name: str = "Plugin"
    declaration: ResourceDescriptor | None = None
    config_keys: tuple[str, ...] = ()
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""
    rulesets: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = {
            "name": self.name,
            "type": self.plugin_type,
            "priority": self.priority,
            "scope": self.scope,
            "source": self.source,
            "rulesets": selection_data(self.rulesets),
        }
        if self.root_id:
            payload["root_id"] = self.root_id
        if self.root_path:
            payload["root_path"] = self.root_path
        if self.source_path:
            payload["source_path"] = self.source_path
        return payload


class PluginRegistry:
    """Register already-created Python plugins in deterministic hook order."""

    def __init__(self) -> None:
        self._plugins: dict[str, list[object]] = {
            "compiler": [],
            "runtime": [],
        }
        self._descriptors: dict[int, PluginDescriptor] = {}

    def register(
        self,
        plugin: object,
        *,
        plugin_type: str = "runtime",
        name: str | None = None,
        priority: int | None = None,
        scope: str = "project",
        source: str = "manual",
        class_name: str = "Plugin",
        declaration: ResourceDescriptor | None = None,
        config_keys: tuple[str, ...] = (),
        root_id: str = "",
        root_path: str = "",
        source_path: str = "",
        conflict: str = "error",
        rulesets: tuple[str, ...] = (),
    ) -> None:
        normalized_type = _normalize_type(plugin_type)
        plugin_name = str(
            name or getattr(plugin, "name", plugin.__class__.__name__)
        ).strip()
        if not plugin_name:
            raise ValueError("plugin name cannot be empty")
        plugin_priority = int(
            priority if priority is not None else getattr(plugin, "priority", 100)
        )
        if conflict not in {"error", "replace"}:
            raise ValueError("plugin conflict must be error or replace")
        existing = [
            item
            for item in self._plugins[normalized_type]
            if _plugin_name(item) == plugin_name
        ]
        if existing and conflict == "error":
            raise ValueError(f"duplicate {normalized_type} plugin: {plugin_name}")
        if existing and conflict == "replace":
            self._plugins[normalized_type] = [
                item
                for item in self._plugins[normalized_type]
                if _plugin_name(item) != plugin_name
            ]
        setattr(plugin, "name", plugin_name)
        setattr(plugin, "priority", plugin_priority)
        setattr(plugin, "scope", scope)
        self._plugins[normalized_type].append(plugin)
        self._plugins[normalized_type].sort(
            key=lambda item: (
                int(getattr(item, "priority", 100)),
                _plugin_name(item),
            )
        )
        self._descriptors[id(plugin)] = PluginDescriptor(
            plugin_name,
            normalized_type,
            plugin_priority,
            scope,
            source,
            class_name,
            declaration,
            tuple(config_keys),
            root_id,
            root_path,
            source_path,
            tuple(rulesets),
        )

    def compiler_plugins(self) -> tuple[object, ...]:
        return tuple(self._plugins["compiler"])

    def runtime_plugins(self) -> tuple[object, ...]:
        return tuple(self._plugins["runtime"])

    def descriptors(self) -> tuple[PluginDescriptor, ...]:
        ordered: list[PluginDescriptor] = []
        for plugin_type in ("compiler", "runtime"):
            for plugin in self._plugins[plugin_type]:
                ordered.append(self._descriptors[id(plugin)])
        return tuple(ordered)

    def to_dict(self) -> dict[str, object]:
        return {
            "plugins": [descriptor.to_dict() for descriptor in self.descriptors()]
        }



def dispose_instances(instances, *, primary=None):
    """Release every owned instance, preserving an existing execution failure."""
    errors = []
    for instance in reversed(tuple(instances)):
        dispose = getattr(instance, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except BaseException as error:
                errors.append(error)
    if primary is not None:
        for error in errors:
            primary.add_note(f"plugin disposal failed: {error}")
        if errors:
            primary.cleanup_errors = [*getattr(primary, "cleanup_errors", ()), *errors]
    elif errors:
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup("plugin disposal failed", errors)


def create_lifecycle_plugin(registry, descriptor, factory, context, **metadata):
    """Create and adopt one native instance, releasing it if adoption fails."""
    import inspect
    instance = factory(context)
    if inspect.isawaitable(instance):
        if inspect.iscoroutine(instance):
            instance.close()
        raise ValueError("Python lifecycle factories must return an instance synchronously")
    if instance is None:
        raise ValueError("lifecycle factory must return an instance")
    try:
        registry.register(instance,plugin_type=descriptor.plugin_type,name=descriptor.id,
            priority=descriptor.priority,declaration=descriptor,**metadata)
    except BaseException as error:
        dispose_instances((instance,),primary=error)
        raise
    return instance


def release_plugins(plugin_registry, *, plugin_type, primary=None):
    instances = plugin_registry.runtime_plugins() if plugin_type == "runtime" else plugin_registry.compiler_plugins()
    dispose_instances(instances, primary=primary)


def release_runtime_plugins(plugin_registry, *, primary=None):
    release_plugins(plugin_registry, plugin_type="runtime", primary=primary)


@contextmanager
def plugin_lifetime(plugin_registry, *, plugin_type="runtime"):
    """Release owned plugins without replacing an execution failure."""
    primary = None
    try:
        yield plugin_registry
    except BaseException as error:
        primary = error
        raise
    finally:
        release_plugins(plugin_registry, plugin_type=plugin_type, primary=primary)


def plugin_error(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    details: Mapping[str, object] | None = None,
) -> HealthFinding:
    fields: dict[str, object] = {
        "rule_id": rule_id,
        "severity": "error",
        "object_type": "plugin",
        "object_id": object_id,
        "failure_layer": "plugin",
        "message": message,
        "suggested_fix_type": "fix_plugin",
        "details": dict(details or {}),
    }
    return HealthFinding(**fields)


def _plugin_name(plugin: object) -> str:
    return str(getattr(plugin, "name", plugin.__class__.__name__))


def _normalize_type(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized == "boundary":
        raise ValueError("boundary plugins are removed; use runtime plugins")
    if normalized not in {"compiler", "runtime"}:
        raise ValueError(f"unknown plugin type: {value}")
    return normalized

__all__ = [
    "CompilerPlugin",
    "PluginDescriptor",
    "PluginRegistry",
    "RuntimePlugin",
    "plugin_error",
]
