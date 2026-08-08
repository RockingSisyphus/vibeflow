from __future__ import annotations

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    FLOW_KIND_GLOBAL_STATE,
)
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import (
    LOOP_NODE_TYPES,
    EdgeSpec,
    GraphConfig,
    NodeSpec,
    NodesetSpec,
    STATUS_PLANNED,
)


def build_architecture_report(graph: GraphConfig, *, compiled: CompiledGraph | None = None) -> dict[str, object]:
    edges = compiled.effective_edges if compiled is not None else graph.edges
    adjacency = _adjacency(graph, edges)
    incoming = _incoming(graph, edges)
    nodes = [node.id for node in graph.nodes]
    affected = {node: _reachable(node, adjacency) for node in nodes}
    degrees = {node: len(adjacency.get(node, ())) + len(incoming.get(node, ())) for node in nodes}
    threshold = max(4, len(nodes) // 2)
    declared_global_state = _declared_global_state_by_node(graph)
    contains_global_state = (
        compiled.contains_global_state
        if compiled is not None
        else any(declared_global_state.values())
    )
    return {
        "summary": {
            "nodes": len(nodes),
            "nodesets": len(graph.nodesets),
            "explicit_edges": len(graph.edges),
            "data_edges": len(compiled.data_edges) if compiled is not None else 0,
            "reported_edges": len(edges),
            "contains_global_state": contains_global_state,
        },
        "execution_lock": (
            _execution_lock_payload(graph.execution_lock, scope="root")
            if graph.execution_lock is not None
            else None
        ),
        "contains_global_state": contains_global_state,
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
                "flow_kind": _effective_flow_kind(node, compiled),
                "effect_scope": _effective_effect_scope(node, compiled),
                "runtime_dispatch": _runtime_dispatch_label(node, compiled),
                "execution_lock": (
                    _execution_lock_payload(
                        node.execution_lock,
                        scope=_node_lock_scope(node, graph),
                    )
                    if node.execution_lock is not None
                    else None
                ),
                "effective_execution_lock": _effective_execution_lock(
                    graph,
                    node,
                ),
                "contains_global_state": (
                    node.status != STATUS_PLANNED
                    and (
                        _effective_flow_kind(node, compiled)
                        == FLOW_KIND_GLOBAL_STATE
                        or declared_global_state.get(node.id, False)
                    )
                ),
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "incoming": sorted(incoming.get(node.id, ())),
                "outgoing": sorted(adjacency.get(node.id, ())),
                "affected": affected[node.id],
            }
            for node in graph.nodes
        ],
    }


def _execution_lock_payload(lock: object, *, scope: str) -> dict[str, str]:
    return {"key": str(getattr(lock, "key", "")), "scope": scope}


def _effective_execution_lock(
    graph: GraphConfig,
    node: NodeSpec,
) -> dict[str, object] | None:
    if node.execution_lock is not None:
        return {
            **_execution_lock_payload(
                node.execution_lock,
                scope=_node_lock_scope(node, graph),
            ),
            "inherited": False,
        }
    if graph.execution_lock is not None:
        return {
            **_execution_lock_payload(graph.execution_lock, scope="root"),
            "inherited": True,
        }
    return None


def _node_lock_scope(node: NodeSpec, graph: GraphConfig) -> str:
    return (
        "block"
        if _declared_nodeset_target(node, graph.nodesets)
        else "node"
    )


def _runtime_dispatch_label(
    node: NodeSpec,
    compiled: CompiledGraph | None,
) -> str:
    if node.status == STATUS_PLANNED or compiled is None:
        return "unknown"
    value = getattr(compiled, "runtime_dispatches", {}).get(node.id)
    if value is True:
        return "detected"
    if value is False:
        return "none"
    return "unknown"


def _effective_flow_kind(node: object, compiled: CompiledGraph | None) -> str:
    node_id = str(getattr(node, "id", ""))
    if compiled is not None:
        return compiled.flow_kinds.get(
            node_id,
            str(getattr(node, "flow_kind", "")),
        )
    return str(getattr(node, "flow_kind", ""))


def _effective_effect_scope(
    node: object,
    compiled: CompiledGraph | None,
) -> str:
    node_id = str(getattr(node, "id", ""))
    if compiled is not None and node_id in compiled.effect_scopes:
        return compiled.effect_scopes[node_id]
    return (
        EFFECT_SCOPE_GLOBAL_STATE
        if _effective_flow_kind(node, compiled) == FLOW_KIND_GLOBAL_STATE
        else EFFECT_SCOPE_NONE
    )


def _declared_global_state_by_node(graph: GraphConfig) -> dict[str, bool]:
    return {
        node.id: _node_declares_global_state(
            node,
            graph=graph,
            nodeset_registry=graph.nodesets,
            active_nodesets=frozenset(),
        )
        for node in graph.nodes
    }


def _node_declares_global_state(
    node: NodeSpec,
    *,
    graph: GraphConfig,
    nodeset_registry: dict[str, NodesetSpec],
    active_nodesets: frozenset[str],
) -> bool:
    if node.status == STATUS_PLANNED:
        return False
    if node.flow_kind == FLOW_KIND_GLOBAL_STATE:
        return True
    local_registry = dict(nodeset_registry)
    local_registry.update(graph.nodesets)
    target = _declared_nodeset_target(node, local_registry)
    if not target or target in active_nodesets:
        return False
    nodeset = local_registry.get(target)
    if nodeset is None or nodeset.status == STATUS_PLANNED:
        return False
    return any(
        _node_declares_global_state(
            child,
            graph=nodeset.graph,
            nodeset_registry=local_registry,
            active_nodesets=active_nodesets | {target},
        )
        for child in nodeset.graph.nodes
    )


def _declared_nodeset_target(
    node: NodeSpec,
    nodeset_registry: dict[str, NodesetSpec],
) -> str:
    if node.type_used in nodeset_registry:
        return node.type_used
    if node.type_used in LOOP_NODE_TYPES:
        return node.loop.body
    return ""


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
