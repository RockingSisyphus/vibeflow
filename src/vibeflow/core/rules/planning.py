"""Enumerate graph calls and assign unambiguous rule coverage."""
from dataclasses import dataclass, replace

from vibeflow.core.flow import LOOP_DEFINITION_IDS
from vibeflow.core.rules.selection import resolve_graph_selection
from vibeflow.core.config.scope import normalize_config_scope


from vibeflow.core.graph_calls import GraphCallSubject as GraphRuleSubject, graph_call_subjects


def graph_rule_subjects(graph, *, global_config=None, node_config_overrides=None):
    found = list(graph_call_subjects(graph, global_config=global_config,
        node_config_overrides=node_config_overrides, include_planned=True))
    visited = {id(item.graph) for item in found}
    definitions = list(graph.nodeset_types.values())
    while definitions:
        definition = definitions.pop()
        if id(definition.graph) in visited:
            continue
        visited.add(id(definition.graph))
        found.append(GraphRuleSubject("nodeset:" + definition.type_key, definition.graph, declaration_only=True,
            definition=definition, global_config=normalize_config_scope(definition.global_config),
            available_nodeset_types={**graph.nodeset_types, **definition.graph.nodeset_types}))
        definitions.extend(definition.graph.nodeset_types.values())
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

    Full background definitions live in global_graph. Traversing graph.nodeset_types
    cannot accidentally recurse into a graph assigned to another task.
    """
    subject = subject or task.subject
    graph = subject.graph
    # Keep first-reference order so Rule findings and event records are stable across processes.
    keys = dict.fromkeys(node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id for node in graph.nodes)
    definitions = {}
    for key in keys:
        definition = subject.available_nodeset_types.get(key)
        if definition is not None:
            boundary = replace(definition.graph, nodes=(), edges=(), nodeset_types={})
            definitions[key] = replace(definition, graph=boundary)
    return replace(graph, nodeset_types=definitions)


def selection_report(graph, catalogs):
    """Explain defaults, inheritance and explicit empty choices without execution."""
    from vibeflow.core.rules.selection import resolve_node_selection
    result = []
    for subject,choice in graph_rule_selections(graph, {item.id:item for item in catalogs.rulesets}):
        result.append({"kind":"graph", "owner":subject.owner, "call_path":list(subject.call_path),
            "declaration_only":subject.declaration_only, "selection":choice.to_dict()})
        for node in subject.graph.nodes:
            descriptor = catalogs.nodes.get(node.definition_id)
            if descriptor is not None:
                result.append({"kind":"node", "owner":subject.owner, "type_key":node.definition_id,
                    "call_path":list((*subject.call_path,node.id)), "declaration_only":subject.declaration_only,
                    "selection":resolve_node_selection(descriptor,node).to_dict()})
    return result
