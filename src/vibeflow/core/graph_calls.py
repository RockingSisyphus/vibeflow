"""Canonical call identities and configuration scopes, independent of Targets and Rules."""
from dataclasses import dataclass, field

from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.core.config.scope import normalize_config_scope, merge_config_scopes, node_invocation_scope, nested_node_config_overrides


@dataclass(frozen=True)
class GraphCallSubject:
    owner: str
    graph: object
    call_path: tuple[str, ...] = ()
    call: object | None = None
    declaration_only: bool = False
    parent_path: tuple[str, ...] | None = None
    definition: object | None = None
    global_config: object | None = None
    overrides: object = field(default_factory=dict)
    available_nodesets: object = field(default_factory=dict)


def graph_call_subjects(graph, *, global_config=None, node_config_overrides=None, include_planned=False):
    found = [GraphCallSubject("pipeline", graph, global_config=normalize_config_scope(global_config),
        overrides=node_config_overrides or {}, available_nodesets=graph.nodesets)]

    def walk(current, inherited, prefix=(), active=(), config=None, overrides=None):
        definitions = {**inherited, **current.nodesets}
        config = normalize_config_scope(config)
        overrides = overrides or {}
        for node in current.nodes:
            if node.status == STATUS_PLANNED:
                continue
            from vibeflow.core.tasks import task_graph
            for slot, target in node.task_targets.items():
                nested = task_graph(current, target)
                path = (*prefix, node.id, "tasks", slot)
                found.append(GraphCallSubject("task:" + slot, nested, path, node,
                    parent_path=prefix, global_config=config, available_nodesets=definitions))
                walk(nested, definitions, path, active, config, {})
            key = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            if key in definitions and key not in active:
                nested, path = definitions[key].graph, (*prefix, node.id)
                definition = definitions[key]
                if not include_planned and (definition.status == STATUS_PLANNED or effective_planned_behavior(node, definition).kind == "python_stub"):
                    continue
                values = {**node.params, **config.values, **overrides.get(node.id, {})}
                child_config = merge_config_scopes(normalize_config_scope(definition.global_config),
                    node_invocation_scope(values, allow_config_override=node.allow_config_override))
                child_overrides = nested_node_config_overrides(node, overrides)
                found.append(GraphCallSubject("nodeset:" + key, nested, path, node, parent_path=prefix,
                    definition=definition, global_config=child_config, overrides=child_overrides,
                    available_nodesets={**definitions, **nested.nodesets}))
                walk(nested, definitions, path, (*active, key), child_config, child_overrides)

    walk(graph, {}, config=global_config, overrides=node_config_overrides)
    return tuple(found)
