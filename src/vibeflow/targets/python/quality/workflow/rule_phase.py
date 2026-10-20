"""Execute selected workflow rules with facts available in the current phase."""
from __future__ import annotations

from dataclasses import replace

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleGraphError, compile_ruleset, execute_rule_plan
from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan, native_rule_bindings, native_rule_origins, bound_python_workflow_defaults
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.targets.python.quality.project_context import project_rule_facts
from vibeflow.targets.python.quality.rule_adapter import rule_resources, graph_error_finding


from vibeflow.core.rules.planning import GraphRuleSubject as WorkflowInvocation, graph_rule_subjects, graph_rule_tasks, scoped_graph


def workflow_invocations(graph):
    return graph_rule_subjects(graph)


def execute_workflow_rules(graph, state, *, registry=None, source_context=None,
    phase="static", purity_policy=None, quality_policy=None, nodeset_max_depth=4,
    global_config=None, compiled=None, compilation_findings=(), source_report=None):
    """Import has declaration/source facts; compiled facts exist only afterwards."""
    from vibeflow.targets.python.project.compiler import GraphCompiler, GraphCompileError
    from vibeflow.targets.python.project.registry import NodeRegistryQueries
    from vibeflow.targets.python.quality.workflow.validation import _append_findings

    from vibeflow.targets.python.project.registry import NodeRegistry
    resources = registry if registry is not None else NodeRegistry()
    try:
        rules, rulesets = rule_resources(resources, purity_policy=purity_policy, quality_policy=quality_policy)
    except RuleGraphError as exc:
        _append_findings(state, (graph_error_finding(registry,exc,object_type="workflow",object_id="pipeline",fallback_path=graph.source_path),))
        return
    for rule_id, defaults in bound_python_workflow_defaults(native_rule_bindings(resources, rules),
        nodeset_max_depth, rules=rules, origins=native_rule_origins(resources)).items():
        descriptor = rules[rule_id]
        rules[rule_id] = replace(descriptor, params_defaults={**descriptor.params_defaults, **defaults})
    handlers, project_fact_cache = {}, {}
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.targets.shared.facts import FactStore
    from vibeflow.targets.python.quality.source_context import PythonSourceContext
    session = current_python_check(registry) if registry is not None else None
    store = session.facts.store if session is not None else FactStore("python",opaque_types=(PythonSourceContext,))
    graph_cache = session.source_cache(phase) if session is not None else {}
    registry_queries = None
    invocations = workflow_invocations(graph)
    from vibeflow.core.rules.planning import graph_rule_selections
    state.rule_selections.extend({"kind":"graph", "owner":item.owner, "call_path":item.call_path, "declaration_only":item.declaration_only, "phase":phase, "selection":choice.to_dict()}
        for item,choice in graph_rule_selections(graph, rulesets, global_config=global_config))
    tasks = graph_rule_tasks(graph, rulesets, global_config=global_config)
    compiled_cache = {(): compiled} if compiled is not None else {}
    def compiled_for(item):
        if compiled is None:
            return None
        key = (item.owner, item.call_path, item.declaration_only)
        if item.graph is graph:
            return compiled
        if key not in compiled_cache:
            try:
                compiled_cache[key] = GraphCompiler().compile(item.graph, registry=registry, owner=item.owner, call_path=item.call_path)
            except GraphCompileError as exc:
                compiled_cache[key] = None
                _append_findings(state, (HealthFinding(rule_id=exc.rule_id, severity="error",
                    object_type="nodeset", object_id=item.owner, failure_layer="topology",
                    message=str(exc), details=dict(exc.details or {})),))
        return compiled_cache[key]
    if compiled is not None:
        # Native declaration compilation is independent of selected Rule tasks.
        for item in invocations:
            compiled_for(item)
    def graph_facts(task, item):
        current = scoped_graph(task, item)
        measured = {spec.id: source_report.call_node_metrics[(item.owner, "/".join((*item.call_path, spec.id)))]
            for spec in current.nodes if source_report is not None
            and (item.owner, "/".join((*item.call_path, spec.id))) in source_report.call_node_metrics}
        return {"graph": current, "owner":item.owner, "call_path":item.call_path,
            "declaration_graph":item.graph, "definition":item.definition, "global_config":item.global_config,
            "overrides":item.overrides, "node_types":{spec.id:spec.type_used for spec in current.nodes},
            "runtime_flow_kinds":{spec.id:registry.descriptor(spec.type_used).flow_kind for spec in current.nodes
                if registry is not None and spec.type_used in registry.available()},
            "node_similarities":{spec.id:spec.similar_to.to_dict() for spec in current.nodes if spec.similar_to.node},
            "node_metrics":measured, "fingerprints":{key:str(value["run_pure_fingerprint"])
                for key,value in measured.items() if value.get("run_pure_fingerprint")},
            **({"compiled":compiled_for(item)} if compiled is not None else {})}
    for task in tasks:
        invocation = task.subject
        owner, current, path = invocation.owner, scoped_graph(task), invocation.call_path
        selected = task.reference
        association = {"owner":owner, "phase":phase,
            **({"kind":"nodeset_definition"} if invocation.declaration_only else {"call_path":path})}
        try:
            current_compiled = compiled_for(invocation)
        except GraphCompileError as exc:
            _append_findings(state, (HealthFinding(rule_id=exc.rule_id, severity="error", object_type="nodeset", object_id=owner,
                failure_layer="topology", message=str(exc), details=dict(exc.details or {})),))
            continue
        try:
            plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
            if not plan.invocations:
                continue
            if registry is not None and registry_queries is None:
                registry_queries = NodeRegistryQueries(registry)
            custom = getattr(resources, "rule_handler_loader", None)
            if callable(custom):
                handlers.update(custom(plan))
            plan = complete_source_policy_plan(plan, purity_policy, handlers=handlers)
            contributions = contribution_facts(registry.loaded_plugins.catalogs) if hasattr(registry, "loaded_plugins") else {}
            from vibeflow.targets.python.quality.node_context import graph_sources
            responsible_sources = graph_sources(source_context, task.subjects)
            facts = {**contributions, **project_rule_facts(plan, responsible_sources, project_fact_cache,handlers=handlers), "graph": current, "global_graph": graph,
                "graphs": tuple(graph_facts(task, item) for item in task.subjects),
                **graph_facts(task, invocation),
                "source_load_states": getattr(registry, "source_load_states", {}),
                "registry": registry_queries, "source_context": responsible_sources, "global_source_context":source_context,
                "node_catalog": tuple(registry.descriptor(key) for key in registry.available()) if registry is not None else (),
                "rule_invocations": {item.id: item.rule for item in plan.invocations},
                "global_config": global_config, "owner": owner,
                "node_types": {spec.id: spec.type_used for spec in current.nodes},
                "runtime_flow_kinds": {spec.id: registry.descriptor(spec.type_used).flow_kind for spec in current.nodes
                    if registry is not None and spec.type_used in registry.available()},
                "node_similarities": {spec.id: spec.similar_to.to_dict() for spec in current.nodes if spec.similar_to.node},
                }
            if not invocation.declaration_only:
                facts["call"] = invocation.call
            if current_compiled is not None:
                facts.update(compiled=current_compiled, compilation_findings=compilation_findings)
            subject = {"kind": "nodeset_definition" if invocation.declaration_only else "workflow", "id": owner, "owner": owner}
            if not invocation.declaration_only:
                subject.update(call_id="/".join(path), call_path=path)
            view = store.capture(facts)
            subject["source_identity"] = (view.identity,task.graph_scope,path,task.boundaries,
                session.implementation_identity(plan,handlers) if session is not None else tuple((key,id(value)) for key,value in handlers.items()))
            result = execute_rule_plan(plan, view.context(phase,
                subject=subject,
                scope={"workflow": owner, "workflows": tuple(item.owner for item in invocations),
                    "files": tuple(item.path for item in source_context.files) if source_context is not None else (),
                    "call_path":path, "graph_scope":task.graph_scope, "graph_paths":tuple(item.call_path for item in task.subjects),
                    "boundaries":task.boundaries},
                ), handlers=handlers, source_cache=graph_cache)
            result = replace(result, selection=task.selection.to_dict(), scope={"graph_scope":task.graph_scope,
                "graph_paths":tuple(item.call_path for item in task.subjects), "boundaries":task.boundaries})
            state.rule_executions.append(result)
            _append_findings(state, (replace(item, details={
                **association,
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
                    state.mainline.update(mainline)
        except RuleGraphError as exc:
            item = graph_error_finding(registry, exc, object_type="workflow", object_id=owner, fallback_path=current.source_path)
            _append_findings(state, (replace(item, details={**item.details,**association}),))
        except Exception as exc:
            if not getattr(exc,"findings",()):
                raise
            _append_findings(state, exc.findings)


__all__ = ["WorkflowInvocation", "workflow_invocations", "execute_workflow_rules"]
