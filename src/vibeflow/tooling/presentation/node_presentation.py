"""One presentation cascade for both Targets and architecture documents."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from vibeflow.tooling.application.mermaid_shapes import mermaid_shape_for_flow_kind
from vibeflow.tooling.presentation.style import SYSTEM_STYLE_COLORS


@dataclass(frozen=True)
class EffectivePresentation:
    values: Mapping[str, str]
    sources: Mapping[str, str]

    @property
    def shape(self) -> str:
        return self.values["shape"]

    def mermaid_style(self) -> str:
        names = {"fill": "fill", "stroke": "stroke", "text": "color"}
        return ",".join(f"{names[key]}:{self.values[key]}" for key in names if key in self.values)

    def to_dict(self) -> dict[str, object]:
        return {"values": dict(self.values), "sources": dict(self.sources)}


def resolve_presentation(
    descriptor: object | None,
    *,
    native_class: str = "",
    status_class: str = "",
    call_style: object | None = None,
    flow_kind: str = "",
    resource_kind: str = "node",
) -> EffectivePresentation:
    """Native → Node → status → call, with per-field provenance."""
    identity = flow_kind or _get(descriptor, "flow_kind", "process")
    native_class = "taskManagerNode" if identity == "task_manager" else native_class
    native_class = native_class or ("externalDependency" if _get(descriptor, "external", False)
                                    else "documentNode" if identity == "document" else "defaultNode")
    native = SYSTEM_STYLE_COLORS.get(native_class, SYSTEM_STYLE_COLORS["defaultNode"])
    values = {"fill": native.fill, "stroke": native.stroke, "text": native.text,
              "shape": "trap-b" if native_class == "loopNode" else mermaid_shape_for_flow_kind(identity)}
    sources = dict.fromkeys(values, "native")

    def apply(presentation: object, origin: str) -> None:
        if hasattr(presentation, "to_dict"):
            presentation = presentation.to_dict()
        if isinstance(presentation, Mapping):
            for key, value in presentation.items():
                if value:
                    values[str(key)] = str(value)
                    sources[str(key)] = origin

    if resource_kind != "node":
        values["shape"] = "fr-rect" if resource_kind == "base_lib" else "hex"
    apply(_get(descriptor, "presentation", {}), resource_kind)
    if status_class in SYSTEM_STYLE_COLORS:
        status = SYSTEM_STYLE_COLORS[status_class]
        apply({"fill": status.fill, "stroke": status.stroke, "text": status.text}, "status")
    apply(call_style, "call")
    # The Mermaid vocabulary uses 'diam', while public descriptors say diamond.
    if values["shape"] == "diamond":
        values["shape"] = "diam"
    return EffectivePresentation(MappingProxyType(values), MappingProxyType(sources))


def registry_descriptor(registry: object | None, type_key: str) -> object | None:
    method = getattr(registry, "descriptor", None)
    if callable(method):
        try:
            return method(type_key)
        except (KeyError, ValueError):
            return None
    return None


def _get(value: object, key: str, default: object) -> object:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)
