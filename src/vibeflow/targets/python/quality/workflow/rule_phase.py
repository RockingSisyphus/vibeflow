"""Execute selected workflow rules with facts available in the current phase."""
from __future__ import annotations

from dataclasses import dataclass, replace

from vibeflow.core.findings import HealthFinding
from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.core.rules import RuleContext, RuleGraphError, compile_ruleset, execute_rule_plan
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.targets.python.quality.project_context import project_rule_facts
from vibeflow.targets.python.quality.rule_adapter import rule_resources, graph_error_finding
from vibeflow.targets.python.quality.rules import python_rule_handlers


@dataclass(frozen=True)
class WorkflowInvocation:
    owner: str
    graph: object
    call_path: tuple[str, ...] = ()
    call: object | None = None
    declaration_only: bool = False


def workflow_invocations(graph):
    """Visit actual calls, retaining repeated Nodeset and Loop invocations."""
    found = [WorkflowInvocation("pipeline", graph)]

    def walk(current, inherited, prefix=(), active=()):
        definitions = {**inherited, **current.nodesets}
        for node in current.nodes:
            if node.status == STATUS_PLANNED:
                continue
            key = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            if key in definitions and key not in active:
                nested, path = definitions[key].graph, (*prefix, node.id)
                found.append(WorkflowInvocation("nodeset:" + key, nested, path, node))
                walk(nested, definitions, path, (*active, key))

    walk(graph, {})
    visited = {id(item.graph) for item in found}
    definitions = list(graph.nodesets.values())
    while definitions:
        definition = definitions.pop()
        if id(definition.graph) in visited or definition.status == STATUS_PLANNED:
            continue
        visited.add(id(definition.graph))
        found.append(WorkflowInvocation("nodeset:" + definition.type_key, definition.graph, declaration_only=True))
        definitions.extend(definition.graph.nodesets.values())
    return tuple(found)


def execute_workflow_rules(graph, state, *, registry=None, source_context=None,
    phase="static", purity_policy=None, quality_policy=None, nodeset_max_depth=4,
    global_config=None, compiled=None, compilation_findings=(), source_report=None):
    """Import has declaration/source facts; compiled facts exist only afterwards."""
    from vibeflow.targets.python.project.compiler import GraphCompiler, GraphCompileError
    from vibeflow.targets.python.project.registry import NodeRegistryQueries
    from vibeflow.targets.python.quality.workflow.validation import _append_findings
    from types import SimpleNamespace

    resources = registry if registry is not None else SimpleNamespace(rule_catalogs=())
    try:
        rules, rulesets = rule_resources(resources, purity_policy=purity_policy, quality_policy=quality_policy)
    except RuleGraphError as exc:
        _append_findings(state, (graph_error_finding(registry,exc,object_type="workflow",object_id="pipeline",fallback_path=graph.source_path),))
        return
    for rule_id in ("vibeflow.workflow", "vibeflow.graph.nodesets"):
        descriptor = rules.get(rule_id)
        if descriptor is not None:
            rules[rule_id] = replace(descriptor, params_defaults={**descriptor.params_defaults, "nodeset_max_depth": nodeset_max_depth})
    handlers, project_fact_cache = python_rule_handlers(), {}
    registry_queries = None
    invocations = workflow_invocations(graph)
    for invocation in invocations:
        owner, current, path = invocation.owner, invocation.graph, invocation.call_path
        association = {"owner":owner, "phase":phase,
            **({"kind":"nodeset_definition"} if invocation.declaration_only else {"call_path":path})}
        current_compiled = compiled
        if compiled is not None and current is not graph:
            try:
                current_compiled = GraphCompiler().compile(current, registry=registry, owner=owner)
            except GraphCompileError as exc:
                _append_findings(state, (HealthFinding(rule_id=exc.rule_id, severity="error", object_type="nodeset", object_id=owner,
                    failure_layer="topology", message=str(exc), details=dict(exc.details or {})),))
                continue
        for selected in current.rulesets:
            try:
                plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
                if not plan.invocations:
                    continue
                if registry is not None and registry_queries is None:
                    registry_queries = NodeRegistryQueries(registry)
                custom = getattr(registry, "rule_handler_loader", None)
                if callable(custom):
                    handlers.update(custom(plan))
                contributions = contribution_facts(registry.loaded_plugins.catalogs) if hasattr(registry, "loaded_plugins") else {}
                facts = {**contributions, **project_rule_facts(plan, source_context, project_fact_cache), "graph": current,
                    "source_load_states": getattr(registry, "source_load_states", {}),
                    "registry": registry_queries, "source_context": source_context,
                    "node_catalog": tuple(registry.descriptor(key) for key in registry.available()) if registry is not None else (),
                    "rule_invocations": {item.id: item.rule for item in plan.invocations},
                    "global_config": global_config, "purity_policy": purity_policy, "owner": owner,
                    "node_types": {spec.id: spec.type_used for spec in current.nodes},
                    "runtime_flow_kinds": {spec.id: registry.descriptor(spec.type_used).flow_kind for spec in current.nodes
                        if registry is not None and spec.type_used in registry.available()},
                    "node_similarities": {spec.id: spec.similar_to.to_dict() for spec in current.nodes if spec.similar_to.node},
                    }
                if not invocation.declaration_only:
                    facts["call"] = invocation.call
                if current_compiled is not None:
                    facts.update(compiled=current_compiled, compilation_findings=compilation_findings)
                if source_report is not None:
                    metrics = {spec.id: source_report.node_metrics[spec.type_used] for spec in current.nodes if spec.type_used in source_report.node_metrics}
                    facts.update(node_metrics=metrics, fingerprints={key: str(value["run_pure_fingerprint"])
                        for key, value in metrics.items() if value.get("run_pure_fingerprint")})
                subject = {"kind": "nodeset_definition" if invocation.declaration_only else "workflow", "id": owner, "owner": owner}
                if not invocation.declaration_only:
                    subject.update(call_id="/".join(path), call_path=path)
                result = execute_rule_plan(plan, RuleContext(facts=facts,
                    subject=subject,
                    scope={"workflow": owner, "workflows": tuple(item.owner for item in invocations),
                        "files": tuple(item.path for item in source_context.files) if source_context is not None else ()},
                    phase=phase, target="python"), handlers=handlers)
                state.rule_executions.append(result)
                _append_findings(state, (replace(item, details={
                    **({} if item.details.get("definition_review") else association),
                    **item.details, "rule_contexts":[association]}) for item in result.findings))
                for invocation_id, value in result.results.items():
                    if value.state != "completed" and not any(item.severity == "error" for item in value.findings):
                        _append_findings(state, (HealthFinding(rule_id="RULE.EXECUTION.UNAVAILABLE", severity="error", object_type="workflow", object_id=owner,
                            message=f"rule '{invocation_id}' did not complete ({value.state})", failure_layer="rule",
                            definition_id=next(item.rule.id for item in plan.invocations if item.id == invocation_id),
                            details={"state": value.state, **association}),))
                    review = value.records.get("workflow_review")
                    if value.state == "completed" and review is not None:
                        mainline = review.value.get("mainline", {})
                        if owner == "pipeline":
                            state.mainline.update(mainline)
                        elif owner in mainline:
                            state.mainline[owner] = mainline[owner]
            except RuleGraphError as exc:
                item = graph_error_finding(registry, exc, object_type="workflow", object_id=owner, fallback_path=current.source_path)
                _append_findings(state, (replace(item, details={**item.details,**association}),))
            except Exception as exc:
                if not getattr(exc,"findings",()):
                    raise
                _append_findings(state, exc.findings)


__all__ = ["WorkflowInvocation", "workflow_invocations", "execute_workflow_rules"]
