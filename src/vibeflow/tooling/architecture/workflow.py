"""One architecture projection for both checked Target representations."""
from dataclasses import dataclass, field
from collections.abc import Callable, Mapping
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.flow import LOOP_DEFINITION_IDS, STATUS_PLANNED
from vibeflow.core.inspection import build_architecture_report
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.core.rules.models import plain
from vibeflow.core.rules.selection import selection_data
from vibeflow.core.workflows.references import node_workflow_actions, workflow_node_params
from vibeflow.core.graph_calls import graph_call_subjects
from vibeflow.tooling.presentation.node_presentation import resolve_presentation
from .entries import entry_facts, policy_facts


@dataclass(frozen=True)
class ArchitectureInputs:
    graph: object
    compiled: object
    target: str
    descriptor: Callable
    compile_graph: Callable
    node_definitions: Mapping
    node_types: Mapping
    resources: Mapping
    global_config: Mapping = field(default_factory=dict)
    policies: Mapping = field(default_factory=dict)
    health_classes: Mapping = field(default_factory=dict)
    extras: Mapping = field(default_factory=dict)
    effective_params: Mapping = field(default_factory=dict)


def configuration(values, source):
    return {"values": plain(values), "source": dict(source)}


def source_reference(graph):
    from pathlib import Path
    path = Path(graph.source_path) if graph.source_path else None
    if path is not None and path.is_absolute() and graph.root_path:
        path = path.relative_to(graph.root_path)
    return {"root_id": graph.root_id, "path": path.as_posix() if path else ""}


def graph_document(graph, compiled, *, descriptor, compile_graph=None, health_classes=None,
                   graph_lock_scope="root", source=None):
    source = dict(source) if source is not None else source_reference(graph)
    records = []
    for node in graph.nodes:
        definition = descriptor(node.definition_id)
        target = node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id
        nodeset = graph.nodeset_types.get(target)
        planned = node.status == STATUS_PLANNED or getattr(nodeset, "status", "") == STATUS_PLANNED
        flow_kind = compiled.flow_kinds.get(node.id, node.flow_kind)
        selected = nodeset.graph.rulesets if nodeset else node.rulesets if node.rulesets is not None else getattr(definition, "rulesets", None)
        invocation = ({"kind": "loop_body" if node.definition_id in LOOP_DEFINITION_IDS else "nodeset",
                       "target": target, "target_status": nodeset.status} if nodeset else None)
        native = ("loopNode" if node.definition_id in LOOP_DEFINITION_IDS else "nodesetNode") if nodeset else ""
        contains_global = not planned and flow_kind == "global_state"
        if nodeset and not planned and compile_graph:
            contains_global |= compile_graph(nodeset.graph)[1].contains_global_state
        lock = node.execution_lock or graph.execution_lock
        scope = ("block" if nodeset else "node") if node.execution_lock else graph_lock_scope
        records.append({
            "id": node.id, "definition_id": node.definition_id, "source": source,
            "role": {**node.metadata.to_dict(), "description_source": "call"},
            "flow_kind": flow_kind, "rulesets": selection_data(selected), "selected_rulesets": selection_data(selected),
            "tags": list(getattr(definition, "tags", ())), "metadata": plain(getattr(definition, "metadata", {})),
            "presentation": resolve_presentation(definition, native_class=native,
                status_class="plannedNode" if planned else (health_classes or {}).get((id(graph), node.id), ""),
                call_style=node.style, flow_kind=flow_kind, node=node, compiled=compiled).to_dict(),
            "effect_scope": "unavailable" if planned else compiled.effect_scopes.get(node.id, "unconstrained"),
            "execution_lock": {"key": node.execution_lock.key, "scope": scope} if node.execution_lock else None,
            "effective_execution_lock": {"key": lock.key, "scope": scope, "inherited": node.execution_lock is None} if lock else None,
            "contains_global_state": bool(contains_global), "status": node.status,
            "planned_behavior": effective_planned_behavior(node, nodeset).to_dict() if planned else None,
            "requires": requirements_to_dicts(node.requires), "provides": providers_to_dicts(node.provides),
            "contract_source": "planned_config" if node.status == STATUS_PLANNED else "system_config" if node.definition_id in LOOP_DEFINITION_IDS else "nodeset" if nodeset else "node_definition",
            "join_policy": node.join_policy, "loop": node.loop.to_dict() or None, "invokes": invocation,
            "config": {"call": configuration(node.params, source), "node_configs": configuration(node.node_config_overrides, source), "allow_config_override": node.allow_config_override},
        })
    nodes = {node.id: node for node in graph.nodes}
    edges = []
    for edge in compiled.effective_edges:
        requirements = {item.type: item for item in nodes[edge.target].requires}
        edges.append({"from": edge.source, "to": edge.target, "when": edge.when,
            "roles": [name for name in ("mainline", "data_bypass", "schedule", "transfer") if edge in getattr(compiled, name + "_edges")],
            "transfers": [{"provider": item.to_dict(), "requirement": requirements[item.type].to_dict()}
                          for item in nodes[edge.source].provides if item.type in requirements]})
    report = build_architecture_report(graph, compiled=compiled)
    return {**entry_facts(graph, compiled), "source": source, "rulesets": selection_data(graph.rulesets),
        "inputs": providers_to_dicts(graph.inputs), "outputs": requirements_to_dicts(graph.outputs),
        "max_steps": graph.max_steps, "entry_mode": graph.entry_mode,
        "execution_lock": {"key": graph.execution_lock.key, "scope": graph_lock_scope} if graph.execution_lock else None,
        "contains_global_state": bool(compiled.contains_global_state or any(row["contains_global_state"] for row in records)),
        **{key: report[key] for key in ("summary", "entry_nodes", "terminal_nodes", "god_nodes")},
        "nodes": records, "edges": edges}


def build_workflow_architecture(inputs):
    graph = inputs.graph
    def body(current, compiled, scope):
        return graph_document(current, compiled, descriptor=inputs.descriptor,
            compile_graph=inputs.compile_graph, health_classes=inputs.health_classes, graph_lock_scope=scope)
    workflow = body(graph, inputs.compiled, "root")
    workflow["global_config"] = configuration(inputs.global_config, workflow["source"])
    definitions = {}
    # Reachability is a presentation annotation, not a second scheduler.
    reachable = set()
    def visit(current):
        for node in current.nodes:
            key = node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id
            if key in graph.nodeset_types and key not in reachable:
                reachable.add(key); visit(graph.nodeset_types[key].graph)
    visit(graph)
    for key, definition in sorted(graph.nodeset_types.items()):
        source = source_reference(definition)
        child = None
        if definition.graph.nodes:
            current, compiled = inputs.compile_graph(definition.graph)
            child = body(current, compiled, "block")
        definitions[key] = {"type_key": key, "source": source,
            "display_name": definition.display_name, "description": definition.description,
            "status": definition.status, "planned_behavior": definition.planned_behavior.to_dict() if definition.status == STATUS_PLANNED else None,
            "expand": definition.expand, "flow_kind": definition.flow_kind,
            "effect_scope": "unavailable" if definition.status == STATUS_PLANNED else "unconstrained",
            "rulesets": selection_data(definition.graph.rulesets), "reachable_from_workflow": key in reachable,
            "requires": requirements_to_dicts(definition.requires), "provides": providers_to_dicts(definition.provides),
            "global_config": configuration(definition.global_config, source), "body": child}
    policies = {path: plain(policy) for path, policy in inputs.policies.items()}
    effective_params = {(*subject.call_path, node.id): workflow_node_params(node, inputs.descriptor(node.definition_id), subject)
        for subject in graph_call_subjects(graph, global_config=inputs.global_config, include_planned=True, include_planned_calls=True) for node in subject.graph.nodes}
    effective_params.update(inputs.effective_params)
    def annotate(body, prefix=(), active=(), inherited_planned=False):
        for row in body["nodes"]:
            path = (*prefix, row["id"])
            policy = policies.setdefault(path, {"actions": []})
            declared = inputs.descriptor(row["definition_id"])
            actions = policy.get("actions", ())
            planned = inherited_planned or row["status"] == STATUS_PLANNED or (row.get("invokes") or {}).get("target_status") == STATUS_PLANNED
            if planned and not actions:
                # Planned calls have no executed Rule records. Their declared
                # operations still describe review intent without executing Rules.
                actions = [{"capability":req.id,"operation":operation,"planned":True}
                    for req in getattr(declared, "capabilities", ()) if req.id == "vibeflow.workflow" for operation in req.operations]
            actions = node_workflow_actions(actions, effective_params.get(path, row["config"]["call"]["values"]), root=graph.root_id)
            policy["actions"] = actions
            # Call-path-specific operations also remain in call_policies for reused Nodesets.
            if not prefix: row["operations"] = actions
            target = (row.get("invokes") or {}).get("target")
            if target in definitions and target not in active and definitions[target]["body"]:
                annotate(definitions[target]["body"], path, (*active, target), planned)
    annotate(workflow)
    return {"project_target": inputs.target, "workflow": workflow, "nodeset_types": definitions,
        "node_definitions": plain(inputs.node_definitions), "node_types": plain(inputs.node_types),
        "resources": plain(inputs.resources), "call_policies": policy_facts(policies), **plain(inputs.extras)}
