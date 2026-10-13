"""Enumerate graph calls and assign unambiguous rule coverage."""
from dataclasses import dataclass, field, replace

from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.rules.selection import resolve_graph_selection
from vibeflow.core.config.scope import normalize_config_scope, merge_config_scopes, node_invocation_scope, nested_node_config_overrides


@dataclass(frozen=True)
class GraphRuleSubject:
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


def graph_rule_subjects(graph, *, global_config=None):
    found = [GraphRuleSubject("pipeline", graph, global_config=normalize_config_scope(global_config), available_nodesets=graph.nodesets)]

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
                found.append(GraphRuleSubject("task:" + slot, nested, path, node,
                    parent_path=prefix, global_config=config, available_nodesets=definitions))
                walk(nested, definitions, path, active, config, {})
            key = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            if key in definitions and key not in active:
                nested, path = definitions[key].graph, (*prefix, node.id)
                definition = definitions[key]
                values = {**node.params, **config.values, **overrides.get(node.id, {})}
                child_config = merge_config_scopes(normalize_config_scope(definition.global_config),
                    node_invocation_scope(values, allow_config_override=node.allow_config_override))
                child_overrides = nested_node_config_overrides(node, overrides)
                found.append(GraphRuleSubject("nodeset:" + key, nested, path, node, parent_path=prefix,
                    definition=definition, global_config=child_config, overrides=child_overrides,
                    available_nodesets={**definitions, **nested.nodesets}))
                walk(nested, definitions, path, (*active, key), child_config, child_overrides)

    walk(graph, {}, config=global_config)
    visited = {id(item.graph) for item in found}
    definitions = list(graph.nodesets.values())
    while definitions:
        definition = definitions.pop()
        if id(definition.graph) in visited:
            continue
        visited.add(id(definition.graph))
        found.append(GraphRuleSubject("nodeset:" + definition.type_key, definition.graph, declaration_only=True,
            definition=definition, global_config=normalize_config_scope(definition.global_config),
            available_nodesets={**graph.nodesets, **definition.graph.nodesets}))
        definitions.extend(definition.graph.nodesets.values())
    return tuple(found)


@dataclass(frozen=True)
class GraphRuleTask:
    subject: GraphRuleSubject
    selection: object
    reference: object
    graph_scope: str
    subjects: tuple[GraphRuleSubject, ...]
    boundaries: tuple[tuple[str, ...], ...]


def _graph_selections(graph, rulesets, global_config=None):
    subjects = graph_rule_subjects(graph, global_config=global_config)
    selections, regions = {}, {}
    by_subject = {}
    active = tuple(item for item in subjects if not item.declaration_only)
    for subject in subjects:
        parent = selections.get(subject.parent_path) if not subject.declaration_only else None
        selection = resolve_graph_selection(subject.graph, rulesets=rulesets, path=subject.call_path, parent=parent)
        by_subject[id(subject)] = selection
        if not subject.declaration_only:
            selections[subject.call_path] = selection
            regions[subject.call_path] = (subject.call_path if parent is None or subject.graph.rulesets is not None
                                         else regions[subject.parent_path])
    return subjects, by_subject, regions


def graph_rule_selections(graph, rulesets, *, global_config=None):
    subjects, selections, _ = _graph_selections(graph, rulesets, global_config)
    return tuple((subject, selections[id(subject)]) for subject in subjects)


def graph_rule_tasks(graph, rulesets, *, global_config=None):
    subjects, by_subject, regions = _graph_selections(graph, rulesets, global_config)
    active = tuple(item for item in subjects if not item.declaration_only)
    tasks = []
    for subject in subjects:
        selection = by_subject[id(subject)]
        for reference in selection.references:
            descriptor = rulesets.get(reference) if isinstance(reference, str) else None
            scope = (descriptor.graph_scope if descriptor is not None else None) or "current_graph"
            if scope == "effective_subtree" and not subject.declaration_only and regions[subject.call_path] != subject.call_path:
                continue
            covered = ((subject,) if scope == "current_graph" or subject.declaration_only else tuple(
                item for item in active if regions[item.call_path] == subject.call_path))
            boundaries = tuple(item.call_path for item in active if item.graph.rulesets is not None
                and item.call_path != subject.call_path and item.parent_path in {value.call_path for value in covered})
            tasks.append(GraphRuleTask(subject, selection, reference, scope, covered, boundaries))
    return tuple(tasks)


def scoped_graph(task, subject=None):
    """Return the responsible graph; child definitions are finite boundaries.

    Full background definitions live in global_graph. Traversing graph.nodesets
    cannot accidentally recurse into a graph assigned to another task.
    """
    subject = subject or task.subject
    graph = subject.graph
    # Keep first-reference order so Rule findings and event records are stable across processes.
    keys = dict.fromkeys(node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used for node in graph.nodes)
    definitions = {}
    for key in keys:
        definition = subject.available_nodesets.get(key)
        if definition is not None:
            boundary = replace(definition.graph, nodes=(), edges=(), nodesets={})
            definitions[key] = replace(definition, graph=boundary)
    return replace(graph, nodesets=definitions)


def selection_report(graph, catalogs):
    """Explain defaults, inheritance and explicit empty choices without execution."""
    from vibeflow.core.rules.selection import resolve_node_selection
    result = []
    for subject,choice in graph_rule_selections(graph, {item.id:item for item in catalogs.rulesets}):
        result.append({"kind":"graph", "owner":subject.owner, "call_path":list(subject.call_path),
            "declaration_only":subject.declaration_only, "selection":choice.to_dict()})
        for node in subject.graph.nodes:
            descriptor = catalogs.nodes.get(node.type_used)
            if descriptor is not None:
                result.append({"kind":"node", "owner":subject.owner, "type_key":node.type_used,
                    "call_path":list((*subject.call_path,node.id)), "declaration_only":subject.declaration_only,
                    "selection":resolve_node_selection(descriptor,node).to_dict()})
    return result
