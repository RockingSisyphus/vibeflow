from __future__ import annotations

from .compiler import CompiledGraph
from .data_contract import providers_to_dicts, requirements_to_dicts
from .graph_config import EdgeSpec, GraphConfig


def build_architecture_report(graph: GraphConfig, *, compiled: CompiledGraph | None = None) -> dict[str, object]:
    edges = compiled.effective_edges if compiled is not None else graph.edges
    adjacency = _adjacency(graph, edges)
    incoming = _incoming(graph, edges)
    nodes = [node.id for node in graph.nodes]
    affected = {node: _reachable(node, adjacency) for node in nodes}
    degrees = {node: len(adjacency.get(node, ())) + len(incoming.get(node, ())) for node in nodes}
    threshold = max(4, len(nodes) // 2)

    return {
        "summary": {
            "nodes": len(nodes),
            "nodesets": len(graph.nodesets),
            "explicit_edges": len(graph.edges),
            "data_edges": len(compiled.data_edges) if compiled is not None else 0,
            "reported_edges": len(edges),
        },
        "entry_nodes": [node for node in nodes if not incoming.get(node)],
        "terminal_nodes": [node for node in nodes if not adjacency.get(node)],
        "god_nodes": [
            {"node": node, "degree": degree}
            for node, degree in sorted(degrees.items(), key=lambda item: (-item[1], item[0]))
            if degree >= threshold
        ],
        "nodes": [
            {
                "id": node.id,
                "type_used": node.type_used,
                "flow_kind": node.flow_kind,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "incoming": sorted(incoming.get(node.id, ())),
                "outgoing": sorted(adjacency.get(node.id, ())),
                "affected": affected[node.id],
            }
            for node in graph.nodes
        ],
    }


def _adjacency(graph: GraphConfig, edges: tuple[EdgeSpec, ...]) -> dict[str, set[str]]:
    out = {node.id: set() for node in graph.nodes}
    for edge in edges:
        out.setdefault(edge.source, set()).add(edge.target)
    return out


def _incoming(graph: GraphConfig, edges: tuple[EdgeSpec, ...]) -> dict[str, set[str]]:
    incoming = {node.id: set() for node in graph.nodes}
    for edge in edges:
        incoming.setdefault(edge.target, set()).add(edge.source)
    return incoming


def _reachable(start: str, adjacency: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    stack = list(adjacency.get(start, ()))
    while stack:
        node = stack.pop()
        if node in seen or node == start:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return sorted(seen)
