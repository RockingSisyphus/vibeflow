from __future__ import annotations

from typing import TYPE_CHECKING

from .graph_config import GraphConfig, LOOP_NODE_TYPES, NodeSpec, NodesetSpec, STATUS_PLANNED

if TYPE_CHECKING:
    from .compiler import CompiledGraph
    from .registry import NodeRegistry


def nodeset_for_node(graph: GraphConfig, node: NodeSpec) -> NodesetSpec | None:
    if node.type_used in LOOP_NODE_TYPES and node.loop.body:
        return graph.nodesets.get(node.loop.body)
    return graph.nodesets.get(node.type_used)


def node_flow_kind(node: NodeSpec, compiled: CompiledGraph) -> str:
    if node.status == STATUS_PLANNED:
        return node.flow_kind
    return compiled.flow_kinds.get(node.id, "")


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
    from .compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry)


def shorten(value: object, *, limit: int = 120) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
