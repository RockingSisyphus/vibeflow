from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from vibeflow.data_contract import DataProvider, DataRequirement


FLOW_KIND_TERMINAL = "terminal"
FLOW_KIND_PROCESS = "process"
FLOW_KIND_DECISION = "decision"
FLOW_KIND_IO = "io"
FLOW_KIND_PREDEFINED = "predefined"
FLOW_KIND_DATA_STORE = "data_store"
FLOW_KIND_DOCUMENT = "document"
FLOW_KIND_PREPARATION = "preparation"

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


@dataclass(frozen=True)
class NodeInfo:
    type_key: str
    display_name: str
    category: str
    description: str
    version: str
    flow_kind: str
    purity: str = "pure"
    author: str | None = None
    tags: tuple[str, ...] = ()
    external: bool = False


@dataclass(frozen=True)
class NodeContract:
    requires: tuple[DataRequirement, ...] = ()
    provides: tuple[DataProvider, ...] = ()
    input_semantics: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    output_semantics: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    params_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    examples: tuple[Mapping[str, Any], ...] = ()


class PureNode(Protocol):
    NODE_INFO: NodeInfo
    CONTRACT: NodeContract

    def run_pure(self, inputs: Mapping[str, Any], params: Mapping[str, Any]) -> Mapping[str, Any]:
        ...
