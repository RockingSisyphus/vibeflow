"""Architecture facts of a checked JavaScript graph; shared by audit and build."""
from pathlib import Path
from typing import Mapping
from vibeflow.core import CompiledGraph
from vibeflow.core.flow import GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.descriptors import DescriptorCatalogs
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.inspection import build_architecture_report
from vibeflow.core.rules.selection import selection_data
from vibeflow.tooling.presentation.node_presentation import resolve_presentation

def _effect_scope_label(
    compiled: CompiledGraph,
    node_id: str,
    flow_kind: str,
) -> str:
    return compiled.effect_scopes.get(
        node_id,
        "unconstrained",
    )


def build_architecture_facts(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph,
    compiled_nodesets: Mapping[str, CompiledGraph],
    catalogs: DescriptorCatalogs,
    used_node_types: frozenset[str],
    active_base_lib_ids: frozenset[str],
    plugin_records: tuple[Mapping[str, object], ...],
    host_records: tuple[Mapping[str, object], ...],
    root_id: str,
    source_path: str,
    findings: tuple = (),
) -> dict[str, object]:
    from vibeflow.tooling.application.javascript.presentation_status import node_health_classes
    health_classes = node_health_classes(graph, findings)
    return {
        "project_target": "javascript",
        "workflow": _javascript_graph_document(
            graph,
            compiled,
            source={"root_id": root_id, "path": source_path},
            graph_lock_scope="root",
            catalogs=catalogs,
            health_classes=health_classes,
        ),
        "nodesets": {
            key: {
                "type_key": value.type_key,
                "source": _javascript_source_reference(value),
                "display_name": value.display_name,
                "description": value.description,
                "status": value.status,
                "expand": value.expand,
                "flow_kind": value.flow_kind,
                "effect_scope": "unavailable" if value.status == STATUS_PLANNED else "unconstrained",
                "rulesets": selection_data(value.graph.rulesets),
                "reachable_from_workflow": key in _reachable_javascript_nodesets(graph),
                "requires": requirements_to_dicts(value.requires),
                "provides": providers_to_dicts(value.provides),
                "global_config": dict(value.global_config),
                "body": (
                    _javascript_graph_document(
                        value.graph,
                        compiled_nodesets[key],
                        source=_javascript_source_reference(value),
                        graph_lock_scope="block",
                        catalogs=catalogs,
                        health_classes=health_classes,
                    )
                    if value.graph.nodes
                    else None
                ),
            }
            for key, value in sorted(graph.nodesets.items())
        },
        "node_types": {
            descriptor.type_key: {**descriptor.to_dict(),
                "effective_presentation": resolve_presentation(descriptor).to_dict(),
            }
            for descriptor in catalogs.nodes
        },
        "resources": {
            "data_schemas": catalogs.schemas.to_dict(),
            "base_lib": {
                key: value
                for key, value in catalogs.base_libs.to_dict().items()
                if key in active_base_lib_ids
            },
            "capabilities": {
                key: value
                for key, value in catalogs.capabilities.to_dict().items()
                if key in _active_capability_ids(
                    catalogs,
                    used_node_types=used_node_types,
                    host_records=host_records,
                )
            },
            "host_extensions": list(host_records),
            "plugins": list(plugin_records),
        },
    }


def _active_capability_ids(
    catalogs: DescriptorCatalogs,
    *,
    used_node_types: frozenset[str],
    host_records: tuple[Mapping[str, object], ...],
) -> frozenset[str]:
    active = {
        requirement.id
        for type_key in used_node_types
        for descriptor in (catalogs.nodes.get(type_key),)
        if descriptor is not None
        for requirement in descriptor.capabilities
    }
    for record in host_records:
        for provided in record.get("provides", ()):
            if isinstance(provided, Mapping):
                capability_id = str(provided.get("id", ""))
            else:
                capability_id = str(provided)
            if capability_id:
                active.add(capability_id)
    return frozenset(active)


def _javascript_graph_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    source: Mapping[str, str],
    graph_lock_scope: str,
    catalogs: DescriptorCatalogs,
    health_classes: Mapping[tuple[int, str], str] | None = None,
) -> dict[str, object]:
    report = build_architecture_report(graph, compiled=compiled)
    return {
        "source": dict(source),
        "rulesets": selection_data(graph.rulesets),
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "max_steps": graph.max_steps,
        "entry_mode": graph.entry_mode,
        "execution_lock": (
            {"key": graph.execution_lock.key, "scope": graph_lock_scope}
            if graph.execution_lock is not None
            else None
        ),
        "contains_global_state": bool(
            getattr(compiled, "contains_global_state", False)
        ),
        "summary": report.get("summary", {}),
        "entry_nodes": report.get("entry_nodes", []),
        "terminal_nodes": report.get("terminal_nodes", []),
        "god_nodes": report.get("god_nodes", []),
        "nodes": [
            _javascript_node_document(
                graph,
                compiled,
                node,
                source=source,
                graph_lock_scope=graph_lock_scope,
                catalogs=catalogs,
                health_classes=health_classes,
            )
            for node in graph.nodes
        ],
        "edges": [
            _javascript_edge_document(graph, compiled, edge)
            for edge in compiled.effective_edges
        ],
    }


def _javascript_node_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    node: object,
    *,
    source: Mapping[str, str],
    graph_lock_scope: str,
    catalogs: DescriptorCatalogs,
    health_classes: Mapping[tuple[int, str], str] | None = None,
) -> dict[str, object]:
    node_id = str(getattr(node, "id", ""))
    type_used = str(getattr(node, "type_used", ""))
    is_loop = type_used in LOOP_NODE_TYPES
    target = getattr(getattr(node, "loop", None), "body", "") if is_loop else type_used
    nodeset = graph.nodesets.get(target)
    invokes = None
    if nodeset is not None:
        invokes = {
            "kind": "loop_body" if is_loop else "nodeset",
            "target": target,
            "target_status": nodeset.status,
        }
    flow_kind = compiled.flow_kinds.get(node_id, str(getattr(node, "flow_kind", "")))
    lock = getattr(node, "execution_lock", None)
    effective_lock = None
    if lock is not None:
        effective_lock = {
            "key": lock.key,
            "scope": "block" if invokes else "node",
            "inherited": False,
        }
    elif graph.execution_lock is not None:
        effective_lock = {
            "key": graph.execution_lock.key,
            "scope": graph_lock_scope,
            "inherited": True,
        }
    status = str(getattr(node, "status", "implemented"))
    contract_source = (
        "planned_config"
        if status == STATUS_PLANNED
        else "system_config"
        if type_used == IO_NODE_TYPE or is_loop
        else "nodeset"
        if nodeset is not None
        else "node_type"
    )
    descriptor = catalogs.nodes.get(type_used)
    native_class = "externalDependency" if descriptor is not None and descriptor.external and nodeset is None else "loopNode" if is_loop else "nodesetNode" if nodeset is not None else "documentNode" if flow_kind == "document" else "defaultNode"
    planned = status == STATUS_PLANNED or nodeset is not None and nodeset.status == STATUS_PLANNED
    presentation = resolve_presentation(descriptor, native_class=native_class, status_class="plannedNode" if planned else (health_classes or {}).get((id(graph), node_id), ""), call_style=getattr(node, "style", None), flow_kind=flow_kind, node=node, compiled=compiled)
    return {
        "id": node_id,
        "type_used": type_used,
        "source": dict(source),
        "role": getattr(node, "metadata").to_dict(),
        "presentation": presentation.to_dict(),
        "rulesets": selection_data(nodeset.graph.rulesets) if nodeset is not None else selection_data(node.rulesets if node.rulesets is not None else descriptor.rulesets) if descriptor else None,
        "selected_rulesets": selection_data(nodeset.graph.rulesets) if nodeset is not None else selection_data(node.rulesets if node.rulesets is not None else descriptor.rulesets) if descriptor else [],
        "tags": list(descriptor.tags) if descriptor else [],
        "metadata": dict(descriptor.metadata) if descriptor else {},
        "contract_source": contract_source,
        "flow_kind": flow_kind,
        "effect_scope": "unavailable" if planned else _effect_scope_label(compiled, node_id, flow_kind),

        "execution_lock": (
            {"key": lock.key, "scope": "block" if invokes else "node"}
            if lock is not None
            else None
        ),
        "effective_execution_lock": effective_lock,
        "contains_global_state": flow_kind == FLOW_KIND_GLOBAL_STATE,
        "status": status,
        "planned_behavior": (
            getattr(node, "planned_behavior").to_dict()
            if str(getattr(node, "status", "")) == STATUS_PLANNED
            else None
        ),
        "requires": requirements_to_dicts(getattr(node, "requires")),
        "provides": providers_to_dicts(getattr(node, "provides")),
        "join_policy": str(getattr(node, "join_policy", "")),
        "loop": getattr(node, "loop").to_dict() or None,
        "io": getattr(node, "io").to_dict() or None,
        "invokes": invokes,
        "config": {
            "call": dict(getattr(node, "params")),
            "node_configs": dict(getattr(node, "node_config_overrides")),
            "allow_config_override": bool(getattr(node, "allow_config_override")),
        },
    }


def _javascript_edge_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    edge: object,
) -> dict[str, object]:
    pair = (str(getattr(edge, "source", "")), str(getattr(edge, "target", "")))
    roles = [
        name
        for name, values in (
            ("mainline", compiled.mainline_edges),
            ("data_bypass", compiled.data_bypass_edges),
            ("schedule", compiled.schedule_edges),
            ("transfer", compiled.transfer_edges),
        )
        if edge in values
    ]
    return {
        "from": pair[0],
        "to": pair[1],
        "when": str(getattr(edge, "when", "")),
        "roles": roles,
    }


def _javascript_source_reference(value: object) -> dict[str, str]:
    root_id = str(getattr(value, "root_id", ""))
    root_path = Path(str(getattr(value, "root_path", "") or ".")).resolve()
    source_path = Path(str(getattr(value, "source_path", "") or ".")).resolve()
    try:
        path = source_path.relative_to(root_path).as_posix()
    except ValueError:
        path = source_path.name
    return {"root_id": root_id, "path": path}


def _reachable_javascript_nodesets(graph: GraphConfig) -> frozenset[str]:
    reachable: set[str] = set()

    def visit(body: GraphConfig) -> None:
        for node in body.nodes:
            target = (
                node.loop.body
                if node.type_used in LOOP_NODE_TYPES
                else node.type_used
            )
            nodeset = body.nodesets.get(target)
            if nodeset is None or target in reachable:
                continue
            reachable.add(target)
            visit(nodeset.graph)

    visit(graph)
    return frozenset(reachable)

