"""Native locations and selections beside the authoritative SDK descriptor."""
from dataclasses import dataclass, field
from typing import Mapping
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class PythonResourceBinding:
    descriptor: object | None
    implementation: object | None = None
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""
    config: Mapping[str, object] = field(default_factory=dict)
    status: str = "implemented"
    selection: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
        object.__setattr__(self, "selection", MappingProxyType(dict(self.selection)))
        if self.descriptor is None and self.status != "planned":
            raise ValueError("implemented resources require an SDK descriptor")

    def __getattr__(self, name):
        descriptor = object.__getattribute__(self, "descriptor")
        if descriptor is not None and hasattr(descriptor, name):
            return getattr(descriptor, name)
        selection = object.__getattribute__(self, "selection")
        if name in selection:
            return selection[name]
        if name in {"display_name", "description", "version", "category"}:
            return ""
        if name in {"rulesets", "targets", "base_libs"}:
            return ()
        raise AttributeError(name)

    @property
    def name(self):
        return self.id

    @property
    def module(self):
        if self.implementation is None:
            return ""
        source = self.implementation.source
        if source.kind == "module":
            return source.ref
        path = Path(source.ref)
        root = Path(self.root_path)
        return ".".join(path.relative_to(root).with_suffix("").parts) if path.is_absolute() and path.is_relative_to(root) else source.ref

    @property
    def class_name(self):
        return self.implementation.source.export or "" if self.implementation else ""

    @property
    def config_keys(self):
        return tuple(sorted(self.config))

    def to_dict(self):
        payload = self.descriptor.to_dict() if self.descriptor is not None else dict(self.selection)
        payload = {**payload, "status": self.status, "root_id": self.root_id,
                   "root_path": self.root_path, "source_path": self.source_path}
        if self.implementation is not None:
            payload["module"] = self.module
            payload["class"] = self.class_name
        if "style" in self.selection:
            payload["style"] = dict(self.selection["style"])
        if self.config:
            payload["config"] = dict(self.config)
        payload["config_keys"] = list(self.config_keys)
        return payload
