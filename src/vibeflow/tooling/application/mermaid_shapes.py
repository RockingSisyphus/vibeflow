"""Target-neutral Mermaid shape semantics for workflow flow kinds."""

from __future__ import annotations

from vibeflow.core.constants import (
    FLOW_KIND_DATA_STORE,
    FLOW_KIND_DECISION,
    FLOW_KIND_DOCUMENT,
    FLOW_KIND_GLOBAL_STATE,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    FLOW_KIND_PREPARATION,
    FLOW_KIND_PROCESS,
    FLOW_KIND_TERMINAL,
)


_SHAPE_BY_FLOW_KIND = {
    FLOW_KIND_TERMINAL: "stadium",
    FLOW_KIND_PROCESS: "rect",
    FLOW_KIND_DECISION: "diam",
    FLOW_KIND_IO: "lean-r",
    FLOW_KIND_PREDEFINED: "fr-rect",
    FLOW_KIND_DATA_STORE: "cyl",
    FLOW_KIND_DOCUMENT: "doc",
    FLOW_KIND_PREPARATION: "hex",
    FLOW_KIND_GLOBAL_STATE: "cloud",
}


def mermaid_shape_for_flow_kind(flow_kind: object) -> str:
    return _SHAPE_BY_FLOW_KIND.get(str(flow_kind), "rect")


__all__ = ["mermaid_shape_for_flow_kind"]
