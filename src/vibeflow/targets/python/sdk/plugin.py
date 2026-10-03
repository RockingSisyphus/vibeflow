"""Fixed Python plugin definitions and per-workflow contributions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.core.descriptors.contributions import ContributionBuilder, ResourceOrigin, PLUGIN_ABI
from vibeflow.core.descriptors.models import SourceLocator, _freeze_mapping
from vibeflow.targets.python.sdk.resources import _declare, _location, definition


@dataclass(frozen=True)
class Plugin:
    id: str
    resources: tuple = ()
    config_schema: Mapping[str, Any] = field(default_factory=dict)
    config_defaults: Mapping[str, Any] = field(default_factory=dict)
    compiler: Any = None
    runtime: Any = None
    priority: int = 100
    rulesets: tuple[str, ...] = ()
    display_name: str = ""
    description: str = ""
    version: str = ""
    abi: str = field(default=PLUGIN_ABI, init=False)
    source: str = field(default="", init=False)

    def __post_init__(self):
        resources = tuple(definition(value) for value in self.resources)
        for kind in ("compiler", "runtime"):
            callback = getattr(self, kind)
            if callback is not None:
                if not callable(callback) and not isinstance(callback, SourceLocator):
                    raise ValueError(f"plugin.{kind} must be a lifecycle factory")
                resources += (_declare("plugin", {"id": f"{self.id}.{kind}", "type": kind,
                    "targets": ["python"], "priority": self.priority, "rulesets": self.rulesets,
                    "display_name": self.display_name or self.id, "description": self.description,
                    "version": self.version,
                    "config": {"schema": self.config_schema, "defaults": self.config_defaults}},
                    None if isinstance(callback, SourceLocator) else callback,
                    source=callback if isinstance(callback, SourceLocator) else None),)
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "rulesets", tuple(self.rulesets))
        object.__setattr__(self, "source", _location()[0])
        object.__setattr__(self, "config_schema", _freeze_mapping(self.config_schema, field_name="plugin.config_schema"))
        object.__setattr__(self, "config_defaults", _freeze_mapping(self.config_defaults, field_name="plugin.config_defaults"))
        self.contributions()

    def contributions(self, config=None):
        builder = ContributionBuilder(self.id, source=self.source)
        for resource in self.resources:
            builder.add(resource.descriptor, origin=ResourceOrigin(self.id, resource.path or self.source,
                        resource.line, symbol=resource.symbol))
        return builder.finish(config=config)

    def bindings(self):
        return {(resource.descriptor.to_dict()["kind"], resource.descriptor.id): resource.implementation
                for resource in self.resources if resource.implementation is not None}
