from __future__ import annotations

from typing import TYPE_CHECKING

from vibeflow.graph_config import GraphConfig, NodeSpec, STATUS_PLANNED
from vibeflow.rendering.review_model import node_flow_kind, nodeset_for_node

if TYPE_CHECKING:
    from vibeflow.compiler import CompiledGraph
    from vibeflow.registry import NodeRegistry


def node_is_external(node: NodeSpec, registry) -> bool:
    if registry is None or node.status == STATUS_PLANNED:
        return False
    try:
        node_cls = registry.get(node.type_used)
    except Exception:
        return False
    return bool(getattr(getattr(node_cls, "NODE_INFO", None), "external", False))


def compile_for_render(graph: GraphConfig, compiled: CompiledGraph | None, registry: NodeRegistry | None) -> CompiledGraph:
    if compiled is not None:
        return compiled
    from vibeflow.compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry)


def shorten(value: object, *, limit: int = 120) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
