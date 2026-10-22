from __future__ import annotations

from vibeflow.core.rules.selection import selection_data

import inspect
from pathlib import Path
from typing import Mapping

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import GraphConfig, LOOP_DEFINITION_IDS, LoopSpec, NodeCallSpec, STATUS_PLANNED
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.tooling.presentation.node_presentation import registry_descriptor, resolve_presentation
from vibeflow.tooling.application.python.presentation.helpers import compile_for_render
from vibeflow.tooling.application.python.presentation.review_model import (
    edge_roles,
    edge_transfers,
    invocation_for_node,
    loop_field_schema,
    node_flow_kind,
    node_review_effect_scope,
    node_review_metadata,
    reachable_nodeset_types,
    rendered_resources_payload,
    resources_payload,
    source_reference,
)


def build_architecture_document(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph | None = None,
    registry: object | None = None,
    resources: object | None = None,
    prepared=None,
) -> dict[str, object]:
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation

    prepared = prepared or prepare_python_presentation(graph, compiled=compiled, registry=registry, resources=resources)
    return prepared.architecture()


def build_architecture_facts(prepared) -> dict[str, object]:
    graph, actual_compiled = prepared.graph, prepared.compiled
    registry, resources = prepared.registry, prepared.resources
    roots = _root_paths(graph)
    from vibeflow.tooling.architecture.workflow import ArchitectureInputs, build_workflow_architecture
    payload = build_workflow_architecture(ArchitectureInputs(
        graph=graph, compiled=actual_compiled, target="python",
        descriptor=lambda key: registry_descriptor(registry, key),
        compile_graph=prepared.graph_for,
        node_definitions=_node_definitions_document(graph, registry=registry, roots=roots),
        node_types=registry.prepared_resources.catalogs.node_types.to_dict() if getattr(registry, "prepared_resources", None) else {},
        resources=_resources_document(graph, resources, roots=roots),
        global_config=resources_payload(resources).get("global_config", {}),
        policies=getattr(registry, "call_capability_policies", {}),
        extras={"resource_use": resources.resource_use.to_dict() if getattr(resources, "resource_use", None) else None}))
    if getattr(registry, "prepared_resources", None) is not None and prepared.source_config_available:
        from vibeflow.tooling.architecture.resources import resource_architecture
        sources = prepared.source_context
        catalogs = registry.prepared_resources.catalogs
        payload["implementation_graph"] = resource_architecture(catalogs,project_root=graph.root_path,
            source_facts=prepared.implementation_sources,resource_use=getattr(resources, "resource_use", None),
            selected_nodes={item.definition_id for item in sources.nodes},
            findings=getattr(registry,"review_findings",()),
            roots={str(root_id):str(path) for path,root_id in registry.source_root_ids.items()})
    from vibeflow.core.rules.planning import selection_report
    payload["call_effect_scopes"] = [{"call_path":list(path), "effect_scope":scope} for path,scope in sorted(getattr(registry,"call_effect_scopes",{}).items())]
    catalogs = getattr(getattr(registry, "prepared_resources", None), "catalogs", None)
    if catalogs is not None:
        payload["rule_selections"] = selection_report(graph, catalogs)
    from vibeflow.tooling.presentation.portable_paths import portable_paths
    known_roots = {str(root_id):str(path) for path,root_id in getattr(registry,"source_root_ids",{}).items()}
    return portable_paths(payload, roots={**roots, **known_roots}, primary_root=graph.root_path)


def render_architecture_document(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph | None = None,
    registry: object | None = None,
    resources: object | None = None,
    prepared=None,
) -> str:
    payload = build_architecture_document(graph, compiled=compiled, registry=registry, resources=resources, prepared=prepared)
    return render_architecture_payload(payload)


from vibeflow.tooling.architecture.documents import render_architecture_payload


def _node_definitions_document(
    graph: GraphConfig,
    *,
    registry: object | None,
    roots: Mapping[str, str],
) -> dict[str, object]:
    occurrences = _node_definition_occurrences(graph)
    return {
        node_id: _node_definition_document(node_id, nodes, registry=registry, roots=roots)
        for node_id, nodes in sorted(occurrences.items())
    }


def _node_definition_occurrences(graph: GraphConfig) -> dict[str, list[tuple[GraphConfig, NodeCallSpec]]]:
    occurrences: dict[str, list[tuple[GraphConfig, NodeCallSpec]]] = {}
    bodies = [graph, *(nodeset.graph for _, nodeset in sorted(graph.nodeset_types.items()))]
    for body in bodies:
        for node in body.nodes:
            if node.definition_id not in LOOP_DEFINITION_IDS and invocation_for_node(body, node) is not None:
                continue
            occurrences.setdefault(node.definition_id, []).append((body, node))
    return occurrences


def _node_definition_document(
    node_id: str,
    occurrences: list[tuple[GraphConfig, NodeCallSpec]],
    *,
    registry: object | None,
    roots: Mapping[str, str],
) -> dict[str, object]:
    if node_id in LOOP_DEFINITION_IDS:
        return _loop_node_definition_document(node_id, roots=roots)
    has_implemented_occurrence = any(node.status != STATUS_PLANNED for _, node in occurrences)
    descriptor = registry_descriptor(registry, node_id)
    if descriptor is None:
        owner, node = occurrences[0]
        metadata = node_review_metadata(owner, node, registry)
        return {
            "id": node_id,
            "source": source_reference(owner.root_id, owner.root_path, owner.source_path),
            "info": {
                "display_name": metadata["display_name"],
                "description": metadata["description"],
                "flow_kind": node.flow_kind,
                "effect_scope": "unconstrained" if has_implemented_occurrence else "unavailable",
            },
            "contract": None,
            "config": None,
            "rulesets": [],
        }
    return {
        "id": node_id,
        "node_type": descriptor.node_type,
        "source": _declared_python_source(registry, node_id, descriptor, roots=roots),
        "declaration": next((source_reference(root_id, root_path, registry.source_info(node_id).path)
                             for root_id, root_path in sorted(roots.items())
                             if source_reference(root_id, root_path, registry.source_info(node_id).path).get("path")), {}),
        "info": {**_node_info_document(descriptor), "effect_scope": registry.effect_scope(node_id) if has_implemented_occurrence else "unavailable"},
        "contract": _node_contract_document(descriptor.contract),
        "rulesets": selection_data(registry.rulesets(node_id)),
        "declared_presentation":dict(getattr(descriptor, "declaration", descriptor).presentation),
        "declared_rulesets":selection_data(getattr(descriptor, "declaration", descriptor).rulesets),
        "presentation": resolve_presentation(descriptor).to_dict(),
        "config": _node_config_document(registry, node_id),
    }


def _loop_node_definition_document(node_id: str, *, roots: Mapping[str, str]) -> dict[str, object]:
    field_schema = loop_field_schema()
    return {
        "id": node_id,
        "source": {
            **_python_source(LoopSpec, roots=roots),
            "runtime": {
                "module": "vibeflow.targets.python.runtime.loop_mixin",
                "class": "RuntimeLoopMixin",
                "entrypoints": ["_run_loop_node", "_run_loop_block_node", "_run_while_loop"],
            },
        },
        "info": {
            "display_name": "While Loop",
            "description": "Repeats one nodeset body with optional termination, carried state, collected values, and exposed outputs; an unbounded loop is valid when max_iterations is null.",
            "version": "",
            "flow_kind": "predefined",
            "effect_scope": "unconstrained",
            "author": None,
            "tags": ["loop", "nodeset", "control_flow"],
            "external": False,
        },
        "contract": {
            "requires": [],
            "provides": [],
            "input_semantics": {
                "call_contract": ["Each invocation declares its complete requires list."],
                "carry": ["Each carry entry maps initial state, body input, and body update keys."],
            },
            "output_semantics": {
                "call_contract": ["Each invocation declares its complete provides list."],
                "collect": ["Collected body outputs use the declared mode and target key."],
                "outputs": ["Loop state or body outputs are exposed through explicit from/as mappings."],
            },
        },
        "config": {
            "defaults": {
                "max_iterations": LoopSpec().max_iterations,
                "stop_when.equals": True,
                "collect[].mode": "all",
            },
            "schema": {
                "node_field": "loop",
                "termination": "stop_after_or_stop_when_or_neither",
                "combined_stop": "OR",
                "fields": field_schema,
            },
        },
    }




def _node_info_document(info: object) -> dict[str, object]:
    return {
        "display_name": str(getattr(info, "display_name", "") or ""),
        "description": str(getattr(info, "description", "") or ""),
        "version": str(getattr(info, "version", "") or ""),
        "flow_kind": str(getattr(info, "flow_kind", "") or ""),
        "author": getattr(info, "author", None),
        "tags": list(getattr(info, "tags", ()) or ()),
        "external": bool(getattr(info, "external", False)),
    }


def _node_contract_document(contract: object) -> dict[str, object]:
    return {
        "requires": requirements_to_dicts(tuple(getattr(contract, "requires", ()) or ())),
        "provides": providers_to_dicts(tuple(getattr(contract, "provides", ()) or ())),
        "input_semantics": _snapshot(getattr(contract, "input_semantics", {}) or {}),
        "output_semantics": _snapshot(getattr(contract, "output_semantics", {}) or {}),
    }


def _node_config_document(registry: object, node_id: str) -> dict[str, object] | None:
    try:
        config_spec = registry.get_config_spec(node_id)
    except Exception:
        return None
    return _snapshot(config_spec.to_dict())


def _resources_document(
    graph: GraphConfig,
    resources: object | None,
    *,
    roots: Mapping[str, str],
) -> dict[str, object]:
    payload = rendered_resources_payload(resources, graph)
    base_lib = payload.get("base_lib", {})
    modules = base_lib.get("modules", ()) if isinstance(base_lib, Mapping) else ()
    plugins = payload.get("plugins", ())

    document = {
        "base_lib": [
            _resource_document(item, kind="base_lib", roots=roots)
            for item in sorted(modules, key=lambda item: (str(item.get("module", "")), str(item.get("id", ""))))
            if isinstance(item, Mapping)
        ],
        "plugins": [
            _resource_document(item, kind="plugin", roots=roots)
            for item in sorted(plugins, key=lambda item: (str(item.get("name", "")), str(item.get("module", ""))))
            if isinstance(item, Mapping)
        ],
    }


    return document


def _resource_document(item: Mapping[str, object], *, kind: str, roots: Mapping[str, str]) -> dict[str, object]:
    root_id = str(item.get("root_id", "") or "")
    root_path = str(item.get("root_path", "") or roots.get(root_id, ""))
    info = item.get("info", {})
    info_map = info if isinstance(info, Mapping) else {}
    common: dict[str, object] = {
        "id": str(item.get("id", "") or ""),
        "status": str(item.get("status", "implemented") or "implemented"),
        "display_name": _resource_value(item, info_map, "display_name"),
        "category": _resource_value(item, info_map, "category"),
        "description": _resource_value(item, info_map, "description"),
        "version": _resource_value(item, info_map, "version"),
        "rulesets": list(item.get("rulesets", ())),
        "source": source_reference(root_id, root_path, item.get("source_path", "")),
    }
    if kind == "base_lib":
        return {"module": str(item.get("module", "") or ""), **common}
    plugin_document: dict[str, object] = {
        "name": str(item.get("name", "") or ""),
        "type": str(item.get("type", info_map.get("type", "")) or ""),
        "targets": sorted(
            str(value)
            for value in item.get("targets", ())
            if isinstance(value, str)
        ),
        "dependencies": sorted(
            str(value)
            for value in item.get("dependencies", ())
            if isinstance(value, str)
        ),
        "config": _snapshot(item.get("config", {})),
        "config_keys": sorted(str(key) for key in item.get("config_keys", ()) if isinstance(key, str)),
        **common,
    }
    module = str(item.get("module", "") or "")
    class_name = str(item.get("class", "") or "")
    if module:
        plugin_document["module"] = module
    if class_name:
        plugin_document["class"] = class_name
    priority = item.get("priority")
    if isinstance(priority, int) and not isinstance(priority, bool):
        plugin_document["priority"] = priority
    return plugin_document


def _resource_value(item: Mapping[str, object], info: Mapping[str, object], field: str) -> str:
    return str(item.get(field, "") or info.get(field, "") or "")


def _config_declaration(value: object, *, source: Mapping[str, str]) -> dict[str, object]:
    return {"values": _snapshot(value), "source": dict(source)}


def _root_paths(graph: GraphConfig) -> dict[str, str]:
    roots: dict[str, str] = {}
    candidates = [(graph.root_id, graph.root_path), *((item.root_id, item.root_path) for item in graph.nodeset_types.values())]
    for root_id, root_path in candidates:
        if root_id and root_path:
            roots[str(root_id)] = str(root_path)
    return roots


def _python_source(node_cls: type, *, roots: Mapping[str, str]) -> dict[str, object]:
    payload: dict[str, object] = {
        "module": str(getattr(node_cls, "__module__", "") or ""),
        "class": str(getattr(node_cls, "__qualname__", getattr(node_cls, "__name__", "")) or ""),
    }
    try:
        path = inspect.getsourcefile(node_cls) or ""
        line = inspect.getsourcelines(node_cls)[1]
    except (OSError, TypeError):
        path = ""
        line = 0
    for root_id, root_path in sorted(roots.items()):
        source = source_reference(root_id, root_path, path)
        if source.get("path"):
            payload.update(source)
            break
    if line:
        payload["line"] = line
    return payload


def _declared_python_source(registry, node_id, descriptor, *, roots):
    location = getattr(registry, "source_locations", {}).get(node_id)
    if location is None:
        return {"implementations": [item.to_dict() for item in descriptor.implementations]}
    path, name, root_id, root = location
    context = getattr(registry, "source_context_snapshot", None)
    source = next((item for item in context.files if item.path == str(path)), None) if context else None
    symbol = context.symbol(str(path), name) if context else None
    module = source.module if source else ".".join(Path(path).relative_to(root).with_suffix("").parts).removesuffix(".__init__")
    payload = {"module": module, "class": name}
    for known_id, root_path in sorted(roots.items()):
        reference = source_reference(known_id, root_path, str(path))
        if reference.get("path"):
            payload.update(reference)
            break
    if symbol is not None:
        payload["line"] = symbol.line
    return payload


def _snapshot(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _snapshot(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_snapshot(item) for item in value]
    return value
