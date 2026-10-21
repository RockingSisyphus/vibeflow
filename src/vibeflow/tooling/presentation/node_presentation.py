"""One presentation cascade for both Targets and architecture documents."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from vibeflow.tooling.presentation.shape_semantics import shape_for_flow_kind
from vibeflow.tooling.presentation.style import SYSTEM_STYLE_COLORS


@dataclass(frozen=True)
class EffectivePresentation:
    values: Mapping[str, str]
    sources: Mapping[str, str]

    @property
    def shape(self) -> str:
        return self.values["shape"]

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
    node: object | None = None,
    compiled: object | None = None,
) -> EffectivePresentation:
    """Native → Node → status → call, with per-field provenance."""
    identity = flow_kind or _get(descriptor, "flow_kind", "process")
    native_class = native_class or ("externalDependency" if _get(descriptor, "external", False)
                                    else "documentNode" if identity == "document" else "defaultNode")
    native = SYSTEM_STYLE_COLORS.get(native_class, SYSTEM_STYLE_COLORS["defaultNode"])
    values = {"fill": native.fill, "stroke": native.stroke, "text": native.text,
              "shape": "trap-b" if native_class == "loopNode" else shape_for_flow_kind(identity)}
    if identity == "process" and native_class not in {"loopNode", "nodesetNode"} and _parallel_call(node, compiled):
        values["shape"] = "dbl-circ"
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
    if resource_kind == "node":
        sources.update(_get(descriptor, "presentation_sources", {}))
    if status_class in SYSTEM_STYLE_COLORS:
        status = SYSTEM_STYLE_COLORS[status_class]
        apply({"fill": status.fill, "stroke": status.stroke, "text": status.text}, "status")
    apply(call_style, "call")
    return EffectivePresentation(MappingProxyType(values), MappingProxyType(sources))


def _parallel_call(node: object | None, compiled: object | None) -> bool:
    """A visual role derived solely from ordinary resolved scheduling edges."""
    if node is None or compiled is None:
        return False
    name = _get(node, "id", "")
    edges = _get(compiled, "resolved_schedule_edges", ())
    outgoing = {edge.target for edge in edges if edge.source == name}
    incoming = {edge.source for edge in edges if edge.target == name}
    return len(outgoing) > 1 or (_get(node, "join_policy", "") == "all" and len(incoming) > 1)


def registry_descriptor(registry: object | None, definition_id: str) -> object | None:
    method = getattr(registry, "descriptor", None)
    if callable(method):
        try:
            return method(definition_id)
        except (KeyError, ValueError):
            return None
    return None


def _get(value: object, key: str, default: object) -> object:
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)
