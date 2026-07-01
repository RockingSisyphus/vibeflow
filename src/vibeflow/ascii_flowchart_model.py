from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AsciiNode:
    name: str
    flow_kind: str
    label: tuple[str, ...]
    index: int
    layer: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class AsciiEdge:
    source: str
    target: str
    label: str = ""
    index: int = 0


@dataclass
class AsciiLayout:
    nodes: dict[str, AsciiNode]
    edges: list[AsciiEdge]
    back_edges: set[AsciiEdge]
    width: int
    height: int
