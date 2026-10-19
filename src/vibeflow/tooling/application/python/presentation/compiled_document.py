"""Serialize checked compilation facts without loading a graph renderer."""
from typing import Mapping

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import GraphConfig, NodeSpec, STATUS_PLANNED
from vibeflow.targets.python.runtime.helpers import has_planned, planned_items
from .helpers import node_flow_kind, nodeset_for_node
from .review_model import node_review_effect_scope, resources_payload


def compiled_graph_payload(graph: GraphConfig, compiled: CompiledGraph, *, resources: object | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "nodes": [
            {
                "id": node.id,
                "type_used": node.type_used,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "status": node.status,
                "planned_behavior": node.planned_behavior.to_dict(),
                "flow_kind": node_flow_kind(node, compiled),
                "effect_scope": node_review_effect_scope(graph, node, None, compiled=compiled),

                "execution_lock": (
                    node.execution_lock.to_dict()
                    if node.execution_lock is not None
                    else None
                ),
                "effective_execution_lock": _effective_execution_lock_payload(
                    graph,
                    node,
                    graph_lock_scope="root",
                ),
                "metadata": node.metadata.to_dict(),
                "style": node.style.to_dict(),
                "similar_to": node.similar_to.to_dict(),
                "root_id": graph.root_id,
                "root_path": graph.root_path,
                "source_path": graph.source_path,
            }
            for node in graph.nodes
        ],
        "explicit_edges": [list(edge.pair) for edge in compiled.explicit_edges],
        "data_edges": [list(edge.pair) for edge in compiled.data_edges],
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
        "mainline_edges": [list(edge.pair) for edge in compiled.mainline_edges],
        "data_bypass_edges": [list(edge.pair) for edge in compiled.data_bypass_edges],
        "schedule_edges": [list(edge.pair) for edge in compiled.schedule_edges],
        "transfer_edges": [list(edge.pair) for edge in compiled.transfer_edges],
        "providers": dict(compiled.providers),
        "consumers": {key: list(values) for key, values in compiled.consumers.items()},
        "nodesets": sorted(graph.nodesets),
        "nodeset_sources": [
            {
                "type_key": nodeset.type_key,
                "root_id": nodeset.root_id,
                "root_path": nodeset.root_path,
                "source_path": nodeset.source_path,
            }
            for nodeset in sorted(graph.nodesets.values(), key=lambda item: item.type_key)
        ],
        "planned": [dict(item) for item in planned_items(graph)],
        "production_ready": not has_planned(graph),
        "execution_lock": (
            graph.execution_lock.to_dict()
            if graph.execution_lock is not None
            else None
        ),
        "contains_global_state": compiled.contains_global_state,
    }
    if graph.root_id or graph.root_path or graph.source_path:
        payload["graph_source"] = {"root_id": graph.root_id, "root_path": graph.root_path, "source_path": graph.source_path}
    resource_payload = resources_payload(resources)
    if _resource_payload_has_planned(resource_payload):
        payload["production_ready"] = False
    if resource_payload:
        payload["resources"] = resource_payload
    return payload


def _resource_payload_has_planned(
    payload: Mapping[str, object],
) -> bool:
    groups: list[object] = [
        payload.get("plugins", ()),
        payload.get("host_extensions", ()),
    ]
    base_lib = payload.get("base_lib", {})
    if isinstance(base_lib, Mapping):
        groups.append(base_lib.get("modules", ()))
    return any(
        isinstance(item, Mapping)
        and str(item.get("status", "implemented")) == STATUS_PLANNED
        for group in groups
        if isinstance(group, (list, tuple))
        for item in group
    )


def _effective_execution_lock_payload(
    graph: GraphConfig,
    node: NodeSpec,
    *,
    graph_lock_scope: str,
) -> dict[str, object] | None:
    nodeset = nodeset_for_node(graph, node)
    if node.execution_lock is not None:
        return {
            "key": node.execution_lock.key,
            "scope": "block" if nodeset is not None else "node",
            "inherited": False,
        }
    if graph.execution_lock is not None:
        return {
            "key": graph.execution_lock.key,
            "scope": graph_lock_scope,
            "inherited": True,
        }
    return None

