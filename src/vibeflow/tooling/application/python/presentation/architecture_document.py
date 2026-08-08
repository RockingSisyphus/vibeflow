from __future__ import annotations

import inspect
import json
from typing import Mapping

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, LoopSpec, NodeSpec, STATUS_PLANNED
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.targets.python.project.node import EFFECT_SCOPE_NONE, EFFECT_SCOPE_TRUSTED, effective_effect_scope
from vibeflow.tooling.application.python.presentation.helpers import compile_for_render
from vibeflow.tooling.application.python.presentation.review_model import (
    edge_roles,
    edge_transfers,
    invocation_for_node,
    loop_field_schema,
    node_flow_kind,
    node_review_effect_scope,
    node_review_metadata,
    reachable_nodesets,
    registry_node_class,
    rendered_resources_payload,
    resources_payload,
    source_reference,
)
from vibeflow.tooling.project.document_kinds import (
    ARCHITECTURE_DOCUMENT_HEADER,
)


def build_architecture_document(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph | None = None,
    registry: object | None = None,
    resources: object | None = None,
) -> dict[str, object]:
    if registry is not None:
        from vibeflow.targets.python.project.compiler import GraphCompiler

        compilation = GraphCompiler().compile_with_findings(
            graph,
            registry=registry,
        )
        graph = compilation.workflow.graph
        actual_compiled = compilation.compiled_graph
    else:
        actual_compiled = compile_for_render(graph, compiled, registry)
    roots = _root_paths(graph)
    return {
        "project_target": "python",
        "workflow": _workflow_document(graph, actual_compiled, registry=registry, resources=resources),
        "nodesets": _nodesets_document(graph, registry=registry),
        "node_types": _node_types_document(graph, registry=registry, roots=roots),
        "resources": _resources_document(graph, resources, roots=roots),
    }


def render_architecture_document(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph | None = None,
    registry: object | None = None,
    resources: object | None = None,
) -> str:
    payload = build_architecture_document(graph, compiled=compiled, registry=registry, resources=resources)
    return render_architecture_payload(payload)


def render_architecture_payload(payload: Mapping[str, object]) -> str:
    return ARCHITECTURE_DOCUMENT_HEADER + json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _workflow_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: object | None,
    resources: object | None,
) -> dict[str, object]:
    source = source_reference(graph.root_id, graph.root_path, graph.source_path)
    global_config = resources_payload(resources).get("global_config", {})
    return {
        "source": source,
        "global_config": _config_declaration(global_config, source=source),
        **_graph_body_document(
            graph,
            compiled,
            registry=registry,
            graph_lock_scope="root",
        ),
    }


def _nodesets_document(graph: GraphConfig, *, registry: object | None) -> dict[str, object]:
    reachable = reachable_nodesets(graph)
    documents: dict[str, object] = {}
    for type_key, nodeset in sorted(graph.nodesets.items()):
        source = source_reference(nodeset.root_id, nodeset.root_path, nodeset.source_path)
        body = None
        if nodeset.graph.nodes:
            compiled = compile_for_render(nodeset.graph, None, registry)
            body = _graph_body_document(
                nodeset.graph,
                compiled,
                registry=registry,
                graph_lock_scope="block",
            )
        documents[type_key] = {
            "type_key": nodeset.type_key,
            "source": source,
            "display_name": nodeset.display_name,
            "description": nodeset.description,
            "status": nodeset.status,
            "planned_behavior": nodeset.planned_behavior.to_dict() if nodeset.status == STATUS_PLANNED else None,
            "flow_kind": nodeset.flow_kind,
            "effect_scope": EFFECT_SCOPE_NONE,
            "reachable_from_workflow": type_key in reachable,
            "requires": requirements_to_dicts(nodeset.requires),
            "provides": providers_to_dicts(nodeset.provides),
            "global_config": _config_declaration(nodeset.global_config, source=source),
            "body": body,
        }
    return documents


def _graph_body_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: object | None,
    graph_lock_scope: str,
) -> dict[str, object]:
    contains_global_state = _graph_contains_global_state(
        graph,
        compiled,
        registry=registry,
    )
    return {
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "max_steps": graph.max_steps,
        "entry_mode": graph.entry_mode,
        "execution_lock": (
            _execution_lock_payload(
                graph.execution_lock,
                scope=graph_lock_scope,
            )
            if graph.execution_lock is not None
            else None
        ),
        "contains_global_state": contains_global_state,
        "nodes": [
            _node_document(
                graph,
                compiled,
                node,
                registry=registry,
                graph_lock_scope=graph_lock_scope,
            )
            for node in graph.nodes
        ],
        "edges": [_edge_document(graph, compiled, edge) for edge in compiled.effective_edges],
    }


def _node_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    node: NodeSpec,
    *,
    registry: object | None,
    graph_lock_scope: str,
) -> dict[str, object]:
    source = source_reference(graph.root_id, graph.root_path, graph.source_path)
    invocation = invocation_for_node(graph, node)
    target = invocation.nodeset if invocation is not None else None
    planned = node.status == STATUS_PLANNED or getattr(target, "status", "") == STATUS_PLANNED
    async_config = None
    if node.async_mode:
        async_config = {"mode": node.async_mode, "result_key": node.result_key or None}
    invokes = None
    if invocation is not None:
        invokes = {
            "kind": invocation.kind,
            "target": invocation.target,
            "target_status": invocation.nodeset.status,
        }
    contains_global_state = (
        node.status != STATUS_PLANNED
        and node_flow_kind(node, compiled) == FLOW_KIND_GLOBAL_STATE
    )
    if (
        not planned
        and invocation is not None
        and invocation.nodeset.status != STATUS_PLANNED
    ):
        try:
            child_compiled = compile_for_render(
                invocation.nodeset.graph,
                None,
                registry,
            )
        except Exception:
            child_compiled = None
        if child_compiled is not None:
            contains_global_state = _graph_contains_global_state(
                invocation.nodeset.graph,
                child_compiled,
                registry=registry,
                visiting=(invocation.target,),
            )
    return {
        "id": node.id,
        "type_used": node.type_used,
        "source": source,
        "role": node_review_metadata(graph, node, registry),
        "flow_kind": node_flow_kind(node, compiled),
        "effect_scope": compiled.effect_scopes.get(
            node.id,
            node_review_effect_scope(graph, node, registry),
        ),
        "runtime_dispatch": _runtime_dispatch_label(node, compiled),
        "execution_lock": (
            _execution_lock_payload(
                node.execution_lock,
                scope="block" if invocation is not None else "node",
            )
            if node.execution_lock is not None
            else None
        ),
        "effective_execution_lock": _effective_execution_lock(
            graph,
            node,
            invocation=invocation,
            graph_lock_scope=graph_lock_scope,
        ),
        "contains_global_state": contains_global_state,
        "status": node.status,
        "planned_behavior": effective_planned_behavior(node, target).to_dict() if planned else None,
        "requires": requirements_to_dicts(node.requires),
        "provides": providers_to_dicts(node.provides),
        "contract_source": _contract_source(graph, node),
        "join_policy": node.join_policy,
        "async": async_config,
        "loop": node.loop.to_dict() or None,
        "io": node.io.to_dict() or None,
        "invokes": invokes,
        "config": {
            "call": _config_declaration(node.params, source=source),
            "node_configs": _config_declaration(node.node_config_overrides, source=source),
            "allow_config_override": node.allow_config_override,
        },
    }


def _contract_source(graph: GraphConfig, node: NodeSpec) -> str:
    if node.status == STATUS_PLANNED:
        return "planned_config"
    if node.type_used == IO_NODE_TYPE or node.type_used in LOOP_NODE_TYPES:
        return "system_config"
    if invocation_for_node(graph, node) is not None:
        return "nodeset"
    return "node_type"


def _execution_lock_payload(lock: object, *, scope: str) -> dict[str, str]:
    return {"key": str(getattr(lock, "key", "")), "scope": scope}


def _effective_execution_lock(
    graph: GraphConfig,
    node: NodeSpec,
    *,
    invocation: object | None,
    graph_lock_scope: str,
) -> dict[str, object] | None:
    if node.execution_lock is not None:
        return {
            **_execution_lock_payload(
                node.execution_lock,
                scope="block" if invocation is not None else "node",
            ),
            "inherited": False,
        }
    if graph.execution_lock is not None:
        return {
            **_execution_lock_payload(
                graph.execution_lock,
                scope=graph_lock_scope,
            ),
            "inherited": True,
        }
    return None


def _runtime_dispatch_label(
    node: NodeSpec,
    compiled: CompiledGraph,
) -> str:
    if node.status == STATUS_PLANNED:
        return "unknown"
    value = getattr(compiled, "runtime_dispatches", {}).get(node.id)
    if value is True:
        return "detected"
    if value is False:
        return "none"
    return "unknown"


def _graph_contains_global_state(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: object | None,
    visiting: tuple[str, ...] = (),
) -> bool:
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node_flow_kind(node, compiled) == FLOW_KIND_GLOBAL_STATE:
            return True
        invocation = invocation_for_node(graph, node)
        if invocation is None or invocation.nodeset.status == STATUS_PLANNED:
            continue
        if invocation.target in visiting:
            continue
        try:
            child_compiled = compile_for_render(
                invocation.nodeset.graph,
                None,
                registry,
            )
        except Exception:
            continue
        if _graph_contains_global_state(
            invocation.nodeset.graph,
            child_compiled,
            registry=registry,
            visiting=(*visiting, invocation.target),
        ):
            return True
    return False


def _edge_document(graph: GraphConfig, compiled: CompiledGraph, edge: object) -> dict[str, object]:
    return {
        "from": str(getattr(edge, "source", "")),
        "to": str(getattr(edge, "target", "")),
        "when": str(getattr(edge, "when", "")),
        "roles": list(edge_roles(compiled, edge)),
        "transfers": [_snapshot(item) for item in edge_transfers(graph, edge)],
    }


def _node_types_document(
    graph: GraphConfig,
    *,
    registry: object | None,
    roots: Mapping[str, str],
) -> dict[str, object]:
    occurrences = _node_type_occurrences(graph)
    return {
        type_key: _node_type_document(type_key, nodes, registry=registry, roots=roots)
        for type_key, nodes in sorted(occurrences.items())
    }


def _node_type_occurrences(graph: GraphConfig) -> dict[str, list[tuple[GraphConfig, NodeSpec]]]:
    occurrences: dict[str, list[tuple[GraphConfig, NodeSpec]]] = {}
    bodies = [graph, *(nodeset.graph for _, nodeset in sorted(graph.nodesets.items()))]
    for body in bodies:
        for node in body.nodes:
            if node.type_used not in LOOP_NODE_TYPES and invocation_for_node(body, node) is not None:
                continue
            occurrences.setdefault(node.type_used, []).append((body, node))
    return occurrences


def _node_type_document(
    type_key: str,
    occurrences: list[tuple[GraphConfig, NodeSpec]],
    *,
    registry: object | None,
    roots: Mapping[str, str],
) -> dict[str, object]:
    if type_key in LOOP_NODE_TYPES:
        return _loop_node_type_document(type_key, roots=roots)
    if type_key == IO_NODE_TYPE:
        return _io_node_type_document(type_key)
    has_implemented_occurrence = any(node.status != STATUS_PLANNED for _, node in occurrences)
    node_cls = registry_node_class(registry, type_key) if has_implemented_occurrence else None
    if node_cls is None:
        owner, node = occurrences[0]
        metadata = node_review_metadata(owner, node, registry)
        return {
            "type_key": type_key,
            "source": source_reference(owner.root_id, owner.root_path, owner.source_path),
            "info": {
                "display_name": metadata["display_name"],
                "description": metadata["description"],
                "flow_kind": node.flow_kind,
                "effect_scope": EFFECT_SCOPE_NONE,
            },
            "contract": None,
            "config": None,
        }
    return {
        "type_key": type_key,
        "source": _python_source(node_cls, roots=roots),
        "info": _node_info_document(getattr(node_cls, "NODE_INFO", None)),
        "contract": _node_contract_document(getattr(node_cls, "CONTRACT", None)),
        "config": _node_config_document(registry, type_key),
    }


def _loop_node_type_document(type_key: str, *, roots: Mapping[str, str]) -> dict[str, object]:
    field_schema = loop_field_schema()
    return {
        "type_key": type_key,
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
            "category": "control_flow",
            "description": "Repeats one nodeset body with optional termination, carried state, collected values, and exposed outputs; an unbounded loop is valid when max_iterations is null.",
            "version": "",
            "flow_kind": "predefined",
            "effect_scope": EFFECT_SCOPE_NONE,
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


def _io_node_type_document(type_key: str) -> dict[str, object]:
    return {
        "type_key": type_key,
        "source": {
            "kind": "kernel",
            "runtime": {
                "python": (
                    "vibeflow.targets.python.runtime.node_mixin."
                    "RuntimeNodeMixin._run_io_node"
                ),
                "javascript": "VibeFlow AOT static io emitter",
            },
        },
        "info": {
            "display_name": "VibeFlow Port IO",
            "category": "io",
            "description": (
                "Receives from or sends to a host-provided vibeflow.port "
                "Capability."
            ),
            "flow_kind": "io",
            "effect_scope": "terminal",
            "external": False,
        },
        "contract": {
            "receive": {
                "requires": 0,
                "provides": 1,
                "completion": "suspend",
            },
            "send": {
                "requires": "one exactly_one",
                "provides": 0,
                "completion": "immediate",
            },
        },
        "config": {
            "schema": {
                "node_field": "io",
                "operations": ["receive", "send"],
                "capability": "vibeflow.port",
            }
        },
    }


def _node_info_document(info: object) -> dict[str, object]:
    return {
        "display_name": str(getattr(info, "display_name", "") or ""),
        "category": str(getattr(info, "category", "") or ""),
        "description": str(getattr(info, "description", "") or ""),
        "version": str(getattr(info, "version", "") or ""),
        "flow_kind": str(getattr(info, "flow_kind", "") or ""),
        "effect_scope": effective_effect_scope(info),
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


def _node_config_document(registry: object, type_key: str) -> dict[str, object] | None:
    try:
        config_spec = registry.get_config_spec(type_key)
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
    host_extensions = payload.get("host_extensions", ())
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
    rendered_host_extensions = [
            _resource_document(item, kind="host_extension", roots=roots)
            for item in sorted(
                host_extensions,
                key=lambda item: str(item.get("id", "")),
            )
            if isinstance(item, Mapping)
    ]
    if rendered_host_extensions:
        document["host_extensions"] = rendered_host_extensions
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
        "source": source_reference(root_id, root_path, item.get("source_path", "")),
    }
    if kind == "base_lib":
        return {"module": str(item.get("module", "") or ""), **common}
    if kind == "host_extension":
        return {
            "effect_scope": EFFECT_SCOPE_TRUSTED,
            "targets": sorted(
                str(value)
                for value in item.get("targets", ())
                if isinstance(value, str)
            ),
            "provides": sorted(
                str(value)
                for value in item.get("provides", ())
                if isinstance(value, str)
            ),
            "dependencies": sorted(
                str(value)
                for value in item.get("dependencies", ())
                if isinstance(value, str)
            ),
            "config_keys": sorted(
                str(key)
                for key in item.get("config_keys", ())
                if isinstance(key, str)
            ),
            **common,
        }
    plugin_document: dict[str, object] = {
        "name": str(item.get("name", "") or ""),
        "type": str(item.get("type", info_map.get("type", "")) or ""),
        "effect_scope": EFFECT_SCOPE_TRUSTED,
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
    candidates = [(graph.root_id, graph.root_path), *((item.root_id, item.root_path) for item in graph.nodesets.values())]
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


def _snapshot(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _snapshot(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_snapshot(item) for item in value]
    return value
