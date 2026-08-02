"""Language-neutral constants shared by Core models and compilers."""

from __future__ import annotations


FLOW_KIND_TERMINAL = "terminal"
FLOW_KIND_PROCESS = "process"
FLOW_KIND_DECISION = "decision"
FLOW_KIND_IO = "io"
FLOW_KIND_PREDEFINED = "predefined"
FLOW_KIND_DATA_STORE = "data_store"
FLOW_KIND_DOCUMENT = "document"
FLOW_KIND_PREPARATION = "preparation"

EFFECT_SCOPE_NONE = "none"
EFFECT_SCOPE_TRUSTED = "trusted"

FLOW_KINDS = frozenset(
    {
        FLOW_KIND_TERMINAL,
        FLOW_KIND_PROCESS,
        FLOW_KIND_DECISION,
        FLOW_KIND_IO,
        FLOW_KIND_PREDEFINED,
        FLOW_KIND_DATA_STORE,
        FLOW_KIND_DOCUMENT,
        FLOW_KIND_PREPARATION,
    }
)


__all__ = [
    "EFFECT_SCOPE_NONE",
    "EFFECT_SCOPE_TRUSTED",
    "FLOW_KINDS",
    "FLOW_KIND_DATA_STORE",
    "FLOW_KIND_DECISION",
    "FLOW_KIND_DOCUMENT",
    "FLOW_KIND_IO",
    "FLOW_KIND_PREDEFINED",
    "FLOW_KIND_PREPARATION",
    "FLOW_KIND_PROCESS",
    "FLOW_KIND_TERMINAL",
]
