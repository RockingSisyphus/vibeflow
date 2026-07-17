from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from vibeflow.graph_config import GraphConfig, LOOP_NODE_TYPES, LoopSpec, NodeSpec, NodesetSpec, STATUS_IMPLEMENTED, STATUS_PLANNED
from vibeflow.node import EFFECT_SCOPE_NONE, effective_effect_scope

if TYPE_CHECKING:
    from vibeflow.compiler import CompiledGraph
    from vibeflow.registry import NodeRegistry


EDGE_ROLE_ORDER = ("mainline", "data_bypass", "async", "schedule", "transfer")


def loop_field_schema() -> dict[str, object]:
    return {
        "body": {"type": "string", "description": "Nodeset type_key executed once per iteration."},
        "max_iterations": {"type": "integer", "minimum": 1, "default": LoopSpec().max_iterations},
        "stop_after": {"type": "integer", "minimum": 1},
        "stop_when": {
            "type": "object",
            "required": ["from"],
            "properties": {
                "from": {"type": "string"},
                "equals": {"type": "boolean", "default": True},
            },
        },
        "carry": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "as", "update"],
                "properties": {
                    "from": {"type": "string"},
                    "as": {"type": "string"},
                    "update": {"type": "string"},
                },
            },
        },
        "collect": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "as"],
                "properties": {
                    "from": {"type": "string"},
                    "as": {"type": "string"},
                    "mode": {"const": "all", "default": "all"},
                },
            },
        },
        "outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "as"],
                "properties": {
                    "from": {"type": "string"},
                    "as": {"type": "string"},
                },
            },
        },
    }


@dataclass(frozen=True)
class ReviewInvocation:
    kind: str
    target: str
    nodeset: NodesetSpec


def invocation_for_node(graph: GraphConfig, node: NodeSpec) -> ReviewInvocation | None:
    if node.type_used in LOOP_NODE_TYPES and node.loop.body:
        nodeset = graph.nodesets.get(node.loop.body)
        return ReviewInvocation("loop_body", node.loop.body, nodeset) if nodeset is not None else None
    nodeset = graph.nodesets.get(node.type_used)
    return ReviewInvocation("nodeset", node.type_used, nodeset) if nodeset is not None else None


def nodeset_for_node(graph: GraphConfig, node: NodeSpec) -> NodesetSpec | None:
    invocation = invocation_for_node(graph, node)
    return invocation.nodeset if invocation is not None else None


def node_flow_kind(node: NodeSpec, compiled: CompiledGraph) -> str:
    if node.status == STATUS_PLANNED:
        return node.flow_kind
    return compiled.flow_kinds.get(node.id, "")


def node_review_effect_scope(graph: GraphConfig, node: NodeSpec, registry: NodeRegistry | None) -> str:
    """Return a review-safe scope; planned and composite calls never gain effects."""

    if node.status == STATUS_PLANNED or node.type_used in LOOP_NODE_TYPES or invocation_for_node(graph, node) is not None:
        return EFFECT_SCOPE_NONE
    node_cls = registry_node_class(registry, node.type_used)
    return effective_effect_scope(getattr(node_cls, "NODE_INFO", None)) if node_cls is not None else EFFECT_SCOPE_NONE


def registry_node_class(registry: NodeRegistry | None, type_key: str) -> type | None:
    if registry is None:
        return None
    try:
        return registry.get(type_key)
    except Exception:
        return None


def node_review_metadata(graph: GraphConfig, node: NodeSpec, registry: NodeRegistry | None) -> dict[str, object]:
    invocation = invocation_for_node(graph, node)
    node_cls = registry_node_class(registry, node.type_used) if invocation is None else None
    info = getattr(node_cls, "NODE_INFO", None) if node_cls is not None else None
    nodeset = invocation.nodeset if invocation is not None else None
    display_name = (
        node.metadata.display_name
        or str(getattr(nodeset, "display_name", "") or "")
        or str(getattr(info, "display_name", "") or "")
        or node.id
    )
    description = (
        node.metadata.description
        or str(getattr(nodeset, "description", "") or "")
        or str(getattr(info, "description", "") or "")
    )
    return {
        "display_name": display_name,
        "description": description,
        "description_source": _description_source(node, nodeset=nodeset, info=info),
    }


def edge_roles(compiled: CompiledGraph, edge: object) -> tuple[str, ...]:
    pair = (str(getattr(edge, "source", "")), str(getattr(edge, "target", "")))
    role_pairs = {
        "mainline": _edge_pairs(compiled.mainline_edges),
        "data_bypass": _edge_pairs(compiled.data_bypass_edges),
        "async": _edge_pairs(compiled.async_edges),
        "schedule": _edge_pairs(compiled.schedule_edges),
        "transfer": _edge_pairs(compiled.transfer_edges),
    }
    return tuple(role for role in EDGE_ROLE_ORDER if pair in role_pairs[role])


def edge_transfers(graph: GraphConfig, edge: object) -> tuple[dict[str, object], ...]:
    source_id = str(getattr(edge, "source", ""))
    target_id = str(getattr(edge, "target", ""))
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get(source_id)
    target = nodes.get(target_id)
    if source is None or target is None:
        return ()
    requirements = {requirement.type: requirement for requirement in target.requires}
    return tuple(
        {
            "provider": provider.to_dict(),
            "requirement": requirements[provider.type].to_dict(),
        }
        for provider in source.provides
        if provider.type in requirements
    )


def resources_payload(resources: object | None) -> Mapping[str, object]:
    if resources is None:
        return {}
    if hasattr(resources, "to_dict") and callable(getattr(resources, "to_dict")):
        payload = resources.to_dict()
    else:
        payload = resources
    return payload if isinstance(payload, Mapping) else {}


def rendered_resources_payload(resources: object | None, graph: GraphConfig | None = None) -> dict[str, object]:
    payload = resources_payload(resources)
    if not payload:
        return {}
    root_ids = graph_root_ids(graph)
    plugins = _rendered_resource_items(mapping_items(payload.get("plugins", ())), root_ids=root_ids)
    base_lib_payload = payload.get("base_lib", {})
    modules = _rendered_resource_items(
        mapping_items(base_lib_payload.get("modules", ()) if isinstance(base_lib_payload, Mapping) else ()),
        root_ids=root_ids,
    )
    result: dict[str, object] = {}
    if modules:
        result["base_lib"] = {"modules": list(modules)}
    if plugins:
        result["plugins"] = list(plugins)
    return result


def graph_root_ids(graph: GraphConfig | None) -> frozenset[str]:
    if graph is None:
        return frozenset()
    root_ids: set[str] = set()
    visited_nodesets: set[str] = set()

    def collect(current: GraphConfig) -> None:
        root_id = str(current.root_id or "").strip()
        if root_id:
            root_ids.add(root_id)
        for node in current.nodes:
            invocation = invocation_for_node(current, node)
            if invocation is None:
                continue
            nodeset = invocation.nodeset
            nodeset_root_id = str(nodeset.root_id or "").strip()
            if nodeset_root_id:
                root_ids.add(nodeset_root_id)
            if nodeset.type_key in visited_nodesets:
                continue
            visited_nodesets.add(nodeset.type_key)
            collect(nodeset.graph)

    collect(graph)
    return frozenset(root_ids)


def reachable_nodesets(graph: GraphConfig) -> frozenset[str]:
    reachable: set[str] = set()
    pending = [item.target for node in graph.nodes if (item := invocation_for_node(graph, node)) is not None]
    while pending:
        type_key = pending.pop()
        if type_key in reachable:
            continue
        reachable.add(type_key)
        nodeset = graph.nodesets.get(type_key)
        if nodeset is None:
            continue
        pending.extend(
            item.target
            for node in nodeset.graph.nodes
            if (item := invocation_for_node(nodeset.graph, node)) is not None
        )
    return frozenset(reachable)


def display_source_path(source_path: str, root_path: str) -> str:
    if not source_path:
        return ""
    if not root_path:
        return Path(source_path).as_posix() if not Path(source_path).is_absolute() else ""
    try:
        return Path(source_path).resolve().relative_to(Path(root_path).resolve()).as_posix()
    except (OSError, ValueError):
        return ""


def source_reference(root_id: object = "", root_path: object = "", source_path: object = "") -> dict[str, str]:
    root_id_text = str(root_id or "").strip()
    root_path_text = str(root_path or "").strip()
    source_path_text = str(source_path or "").strip()
    payload: dict[str, str] = {}
    if root_id_text:
        payload["root_id"] = root_id_text
    relative = display_source_path(source_path_text, root_path_text)
    if relative:
        payload["path"] = relative
    return payload


def _description_source(node: NodeSpec, *, nodeset: NodesetSpec | None, info: object | None) -> str:
    if node.metadata.description:
        return "call"
    if nodeset is not None and nodeset.description:
        return "nodeset"
    if info is not None and str(getattr(info, "description", "") or ""):
        return "node_type"
    return ""


def _edge_pairs(edges: object) -> frozenset[tuple[str, str]]:
    return frozenset((str(item.source), str(item.target)) for item in edges)


def mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _rendered_resource_items(
    resources: tuple[Mapping[str, object], ...],
    *,
    root_ids: frozenset[str],
) -> tuple[Mapping[str, object], ...]:
    return tuple(resource for resource in resources if _resource_is_rendered(resource, root_ids=root_ids))


def _resource_is_rendered(resource: Mapping[str, object], *, root_ids: frozenset[str]) -> bool:
    status = str(resource.get("status", STATUS_IMPLEMENTED)).strip() or STATUS_IMPLEMENTED
    if status != STATUS_IMPLEMENTED:
        return False
    root_id = str(resource.get("root_id", "")).strip()
    return not root_ids or not root_id or root_id in root_ids
