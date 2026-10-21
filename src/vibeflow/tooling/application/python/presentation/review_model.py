from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig, LOOP_DEFINITION_IDS, LoopSpec, NodeCallSpec, NodesetTypeSpec, STATUS_PLANNED

if TYPE_CHECKING:
    from vibeflow.targets.python.project.registry import NodeRegistry


EDGE_ROLE_ORDER = ("mainline", "data_bypass", "schedule", "transfer")


def loop_field_schema() -> dict[str, object]:
    return {
        "body": {"type": "string", "description": "Nodeset type_key executed once per iteration."},
        "max_iterations": {
            "type": ["integer", "null"],
            "minimum": 1,
            "default": LoopSpec().max_iterations,
        },
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
    nodeset: NodesetTypeSpec


def invocation_for_node(graph: GraphConfig, node: NodeCallSpec) -> ReviewInvocation | None:
    if node.definition_id in LOOP_DEFINITION_IDS and node.loop.body:
        nodeset = graph.nodeset_types.get(node.loop.body)
        return ReviewInvocation("loop_body", node.loop.body, nodeset) if nodeset is not None else None
    nodeset = graph.nodeset_types.get(node.definition_id)
    return ReviewInvocation("nodeset", node.definition_id, nodeset) if nodeset is not None else None


def nodeset_for_node(graph: GraphConfig, node: NodeCallSpec) -> NodesetTypeSpec | None:
    invocation = invocation_for_node(graph, node)
    return invocation.nodeset if invocation is not None else None


def node_flow_kind(node: NodeCallSpec, compiled: CompiledGraph) -> str:
    if node.status == STATUS_PLANNED:
        return node.flow_kind
    return compiled.flow_kinds.get(node.id, "")


def node_review_effect_scope(graph: GraphConfig, node: NodeCallSpec, registry: NodeRegistry | None, *, compiled: CompiledGraph | None = None) -> str:
    """Report selected rule constraints separately from native execution identity."""

    invocation = invocation_for_node(graph, node)
    if node.status == STATUS_PLANNED or invocation is not None and invocation.nodeset.status == STATUS_PLANNED:
        return "unavailable"
    if compiled is not None and node.id in compiled.effect_scopes:
        return compiled.effect_scopes[node.id]
    if node.definition_id in LOOP_DEFINITION_IDS or invocation is not None:
        return "unconstrained"
    if registry is not None and node.definition_id in registry.available():
        return registry.effect_scope(node.definition_id)
    return "unconstrained"


def registry_node_class(registry: NodeRegistry | None, type_key: str) -> type | None:
    if registry is None:
        return None
    return getattr(registry, "_registry", {}).get(type_key)


def node_review_metadata(graph: GraphConfig, node: NodeCallSpec, registry: NodeRegistry | None) -> dict[str, object]:
    return {
        "display_name": node.metadata.display_name,
        "description": node.metadata.description,
        "description_source": "call",
    }


def edge_roles(compiled: CompiledGraph, edge: object) -> tuple[str, ...]:
    role_edges = {
        "mainline": compiled.mainline_edges,
        "data_bypass": compiled.data_bypass_edges,
        "schedule": compiled.schedule_edges,
        "transfer": compiled.transfer_edges,
    }
    return tuple(role for role in EDGE_ROLE_ORDER if edge in role_edges[role])


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


def rendered_resources_payload(resources: object | None, graph: GraphConfig | None = None, registry=None) -> dict[str, object]:
    payload = resources_payload(resources)
    if not payload:
        return {}
    catalogs = getattr(getattr(registry, "prepared_resources", None), "catalogs", None)
    # PythonResources describes lifecycle bindings. The user's directory shows
    # the selected package once, including packages without lifecycle hooks.
    if catalogs is not None and hasattr(resources, "plugins"):
        payload = {**payload, "plugins": [
            {**dict(record.get("declaration", {})), **dict(record),
             "config_keys": sorted(record.get("config", {}))}
            for record in catalogs.plugin_records
        ]}
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

    if catalogs is not None:
        enriched = []
        for item in modules:
            descriptor = catalogs.base_libs.get(str(item.get("id", "")))
            enriched.append({**(descriptor.to_dict() if descriptor else {}), **item})
        if enriched:
            result["base_lib"] = {"modules": enriched}
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


def reachable_nodeset_types(graph: GraphConfig) -> frozenset[str]:
    reachable: set[str] = set()
    pending = [item.target for node in graph.nodes if (item := invocation_for_node(graph, node)) is not None]
    while pending:
        type_key = pending.pop()
        if type_key in reachable:
            continue
        reachable.add(type_key)
        nodeset = graph.nodeset_types.get(type_key)
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


def mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _rendered_resource_items(
    resources: tuple[Mapping[str, object], ...],
    *,
    root_ids: frozenset[str],
) -> tuple[Mapping[str, object], ...]:
    return tuple(resource for resource in resources if _resource_is_rendered(resource, root_ids=root_ids))


def _resource_is_rendered(resource: Mapping[str, object], *, root_ids: frozenset[str]) -> bool:
    root_id = str(resource.get("root_id", "")).strip()
    return not root_ids or not root_id or root_id in root_ids
