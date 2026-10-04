"""Fixed Python plugin definitions and per-workflow contributions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from vibeflow.core.descriptors.contributions import ContributionBuilder, ResourceOrigin, PLUGIN_ABI
from vibeflow.core.descriptors.models import SourceLocator, _freeze_mapping
from vibeflow.targets.python.sdk.resources import _declare, _location, definition, _implementation_files


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
    implementation_files: tuple = ()
    declaration_rulesets: tuple[str, ...] = ()
    base_libs: tuple[str, ...] = ()
    presentation: Mapping[str, Any] = field(default_factory=dict)
    abi: str = field(default=PLUGIN_ABI, init=False)
    source: str = field(default="", init=False)

    def __post_init__(self):
        from vibeflow.core.descriptors.presentation import normalize_presentation
        from vibeflow.core.descriptors.models import _string_tuple
        declaration_path = _location()[0]
        object.__setattr__(self, "presentation", normalize_presentation(self.presentation, field_name="plugin.presentation"))
        object.__setattr__(self, "implementation_files", _implementation_files(self.implementation_files, declaration_path))
        object.__setattr__(self, "declaration_rulesets", _string_tuple(self.declaration_rulesets, field_name="plugin.declaration_rulesets"))
        object.__setattr__(self, "base_libs", _string_tuple(self.base_libs, field_name="plugin.base_libs"))
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
                    "presentation": self.presentation, "base_libs": self.base_libs,
                    "implementation_files": self.implementation_files,
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
        declaration = {"kind":"plugin_declaration", "id":self.id, "display_name":self.display_name or self.id,
            "description":self.description, "version":self.version, "rulesets":list(self.declaration_rulesets),
            "presentation":dict(self.presentation), "base_libs":list(self.base_libs),
            "implementations":[{"language":"python", "targets":["python"],
                "source":{"kind":"file", "ref":self.source, "export":"plugin"},
                "implementation_files":[item.to_dict() for item in self.implementation_files]}]}
        return replace(builder.finish(config=config), declaration=declaration)

    def bindings(self):
        return {(resource.descriptor.to_dict()["kind"], resource.descriptor.id): resource.implementation
                for resource in self.resources if resource.implementation is not None}

    @property
    def load_states(self):
        """Observe bootstrap imports without importing delayed implementations."""
        from pathlib import Path
        import sys
        loaded = {str(Path(filename).resolve()) for module in tuple(sys.modules.values())
                  if isinstance(filename := getattr(module, "__file__", None), str)}
        files = {self.source, *(part.ref for part in self.implementation_files)}
        for resource in self.resources:
            for implementation in getattr(resource.descriptor, "implementations", ()):
                if implementation.source.kind == "file":
                    files.add(implementation.source.ref)
                files.update(part.ref for part in getattr(implementation, "implementation_files", ()))
        return {path: "loaded" if str(Path(path).resolve()) in loaded else "not_loaded" for path in files}
