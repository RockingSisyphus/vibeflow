from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class NodeInfo:
    type_key: str
    display_name: str
    category: str
    description: str
    version: str
    purity: str = "pure"
    author: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeContract:
    requires: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
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
