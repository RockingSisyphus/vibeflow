"""Execute declared rule selections against Python Target source facts."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Mapping

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleContext, RuleGraphError, compile_ruleset, execute_rule_plan, rule_graph_error_finding
from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan, native_rule_bindings, native_rule_origins
from vibeflow.core.rules.selection import resolve_node_selection
from vibeflow.targets.python.quality.node_context import local_sources, bind_native_analysis
from vibeflow.core.rules.fingerprint import record_inputs_fingerprint, value_fingerprint


@dataclass(frozen=True)
class PythonRuleReport:
    findings: tuple[Finding, ...] = ()
    executions: tuple[object, ...] = ()
    node_metrics: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    effect_scopes: Mapping[str, str] = field(default_factory=dict)
    call_effect_scopes: Mapping[tuple[str,str],str] = field(default_factory=dict)
    call_effect_policies: Mapping[tuple[str,str],tuple[Mapping[str,object],...]] = field(default_factory=dict)
    call_node_metrics: Mapping[tuple[str,str],Mapping[str,object]] = field(default_factory=dict)
    selections: tuple[Mapping[str,object], ...] = ()


def rule_resources(registry, *, purity_policy=None, quality_policy=None):
    defaults = registry.rule_defaults() if hasattr(registry, "rule_defaults") else {}
    purity_policy = purity_policy if purity_policy is not None else defaults.get("purity_policy")
    quality_policy = quality_policy if quality_policy is not None else defaults.get("quality_policy")
    from vibeflow.targets.python.project.check_session import current_python_check
    from vibeflow.targets.python.project.fact_views import catalog_key
    from vibeflow.targets.shared.facts import fact_key
    session = current_python_check(registry)
    if session is None:
        return _rule_resources(registry, purity_policy=purity_policy, quality_policy=quality_policy)
    key = catalog_key(registry), fact_key((purity_policy, quality_policy))
    if key not in session.rules:
        session.rules[key] = _rule_resources(registry, purity_policy=purity_policy, quality_policy=quality_policy)
    rules, rulesets = session.rules[key]
    return dict(rules), dict(rulesets)


def _rule_resources(registry, *, purity_policy=None, quality_policy=None):
    rules, rulesets, origins = {}, {}, {}
    for catalogs in registry.rule_catalogs or ():
        for kind, catalog, target in (("rule", catalogs.rules, rules), ("ruleset", catalogs.rulesets, rulesets)):
            for descriptor in catalog:
                source_for = getattr(catalog, "source_for", None)
                source = source_for(descriptor.id) if callable(source_for) else ""
                if descriptor.id in target and target[descriptor.id] != descriptor:
                    raise RuleGraphError("RULE.RESOURCE.CONFLICT", f"{kind} resource '{descriptor.id}' has conflicting definitions",
                        {"resource_id":descriptor.id,"resource_kind":kind,"source":source,
                         "previous_source":origins.get((kind,descriptor.id),"")})
                target[descriptor.id] = descriptor
                origins.setdefault((kind,descriptor.id),source)
    from vibeflow.builtin.project_quality import bound_project_quality_defaults
    from vibeflow.targets.python.quality.project_context import source_quality_policy
    for rule_id,defaults in bound_project_quality_defaults(native_rule_bindings(registry, rules),
        quality_policy or source_quality_policy(purity_policy), rules=rules, origins=native_rule_origins(registry)).items():
        rules[rule_id] = replace(rules[rule_id],params_defaults={**rules[rule_id].params_defaults,**defaults})
    return rules, rulesets


def selected_effect_scope(registry, type_key: str) -> str:
    """Describe explicit selected effect-rule parameters without granting IO."""
    try:
        rules, rulesets = rule_resources(registry)
    except RuleGraphError:
        return "unavailable"
    scopes = set()
    for selected in registry.rulesets(type_key):
        try:
            plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint="static")
            plan = complete_source_policy_plan(plan, registry.rule_defaults().get("purity_policy"), handlers=native_rule_bindings(registry, rules))
        except RuleGraphError:
            return "unavailable"
        for invocation in plan.invocations:
            if EFFECT_POLICY_TYPE in invocation.rule.outputs.values() and "effect_scope" in invocation.params:
                scopes.add(str(invocation.params["effect_scope"]))
    return next(iter(scopes)) if len(scopes) == 1 else "mixed" if scopes else "unconstrained"


def graph_error_finding(registry, error, *, object_type, object_id, fallback_path=""):
    source = str(error.details.get("source", ""))
    if source:
        resource = str(error.details.get("resource_id", ""))
        kind = str(error.details.get("resource_kind", "ruleset"))
        return HealthFinding(rule_id=error.code,severity="error",object_type=object_type,object_id=object_id,
            message=error.message,failure_layer="rule",source_location={"path":source,"line":1,"column":1},
            source_path=source,details=dict(error.details),rule_source=f"{kind}:{resource}",
            definition_id=resource if kind == "rule" else "")
    key = error.details.get("ruleset_id", "")
    catalog = next((item.rulesets for item in registry.rule_catalogs or ()
                    if callable(getattr(item.rulesets,"get",None)) and item.rulesets.get(key) is not None
                    and callable(getattr(item.rulesets,"source_for",None))), None) if registry is not None else None
    finding = rule_graph_error_finding(error, rulesets=catalog, object_type=object_type, object_id=object_id)
    if not finding.source_location.get("path") and fallback_path:
        finding = replace(finding, source_location={"path":fallback_path,"line":1,"column":1}, source_path=fallback_path)
    return finding


def execute_python_node_rules(registry, source_context, *, phase="static", purity_policy=None, quality_policy=None, extra_handlers=None, extra_facts=None):
    return _execute_python_node_rules(registry, source_context, phase=phase, purity_policy=purity_policy,
        quality_policy=quality_policy, extra_handlers=extra_handlers, extra_facts=extra_facts)


def review_python_node_binding(registry, source_context, type_key, *, purity_policy=None, quality_policy=None):
    """Review a pending binding using the command's complete source fact view."""
    from vibeflow.targets.python.project.check_session import current_python_check
    session = current_python_check(registry)
    cached = session.node_import_results.get(type_key) if session is not None else None
    from vibeflow.targets.python.project.fact_views import catalog_key
    if cached is not None and cached[0] == (session.snapshot(source_context), catalog_key(registry)):
        return cached[1]
    return _execute_python_node_rules(registry, source_context, phase="import", purity_policy=purity_policy,
        quality_policy=quality_policy, selected_types=(type_key,))


def _execute_python_node_rules(registry, source_context, *, phase="static", purity_policy=None,
    quality_policy=None, extra_handlers=None, extra_facts=None, selected_types=None):
    registry.configure_rule_defaults(purity_policy=purity_policy,quality_policy=quality_policy)
    try:
        rules, rulesets = rule_resources(registry,purity_policy=purity_policy,quality_policy=quality_policy)
    except RuleGraphError as exc:
        finding = graph_error_finding(registry,exc,object_type="rule",object_id=str(exc.details.get("resource_id","")))
        return PythonRuleReport(findings=(finding,),effect_scopes={node.type_key:"unavailable" for node in source_context.nodes})
    syntax = tuple(HealthFinding(rule_id="QUALITY.SYNTAX.PYTHON", severity="error", object_type="file",
        object_id=source.path, message=source.parse_error, source_location={"path":source.path,
            "line":source.parse_line, "column":source.parse_column}, failure_layer="implementation")
        for source in source_context.files if source.parse_error)
    if syntax:
        return PythonRuleReport(findings=syntax)
    handlers = dict(extra_handlers or {})
    custom = getattr(registry, "rule_handler_loader", None)
    findings = []
    seen_diagnostics = {}
    executions = []
    metrics = {}
    call_metrics = {}
    selections = []
    scopes = {}
    policy_scopes = {}
    call_policy_scopes = {}
    call_policies = {}
    call_scoped_types = set()
    unavailable_types = set()
    from vibeflow.targets.python.project.check_session import current_python_check, PythonCheckSession
    session = current_python_check(registry) or PythonCheckSession()
    view = session.view(registry, source_context, extra_facts=extra_facts)
    source_cache = session.source_cache(phase)
    project_fact_cache = session.project_facts_for(view)
    from vibeflow.targets.python.quality.project_context import project_rule_facts
    if phase in {"static","run"}:
        registry.reset_effect_policies(node.type_key for node in source_context.nodes)
    from vibeflow.core.rules.models import plain
    base_context = view.context(phase)
    for node in source_context.nodes:
        if selected_types is not None and node.type_key not in selected_types:
            continue
        local = None
        for owner, call_id in node.calls or (("source", node.type_key),):
            call = source_context.call(owner, call_id)
            selection = resolve_node_selection(node.descriptor, call)
            selections.append({"kind":"node", "type_key":node.type_key, "owner":owner, "call_path":call.call_path if call is not None else (), "selection":selection.to_dict()})
            call_policy_scopes.setdefault((owner, call_id), set())
            for selected_id in selection.references:
                try:
                    plan = session.plan(selected_id, rules, rulesets, phase)
                except RuleGraphError as exc:
                    findings.append(graph_error_finding(registry,exc,object_type="node",object_id=node.type_key,
                        fallback_path=registry.source_info(node.type_key).path))
                    unavailable_types.add(node.type_key)
                    continue
                if not plan.invocations:
                    continue
                if callable(custom):
                    try:
                        handlers.update(custom(plan))
                    except Exception as exc:
                        failure = getattr(exc,"findings",())
                        if not failure:
                            failure = (HealthFinding(rule_id="RULE.IMPLEMENTATION.LOAD",severity="error",object_type="node",
                                object_id=node.type_key,message=str(exc),failure_layer="rule",
                                source_location={"path":registry.source_info(node.type_key).path,"line":1,"column":1}),)
                        findings.extend(failure)
                        unavailable_types.add(node.type_key)
                        continue
                plan = complete_source_policy_plan(plan, purity_policy, handlers=handlers)
                implementation_identity = session.implementation_identity(plan,handlers)
                if plan.graph_scope == "effective_subtree":
                    findings.append(HealthFinding(rule_id="RULE.GRAPH_SCOPE.NODE", severity="error", object_type="node",
                        object_id=node.type_key, message="Node selections cannot use an effective_subtree Ruleset", failure_layer="rule"))
                    unavailable_types.add(node.type_key)
                    continue
                if local is None:
                    local = local_sources(source_context, node)
                updates = {"source_load_states":getattr(registry, "source_load_states", {}),
                    **project_rule_facts(plan,source_context,project_fact_cache,handlers=handlers)}
                prepared = session.view(registry,source_context,extra_facts={**(extra_facts or {}),
                    **{key:value for key,value in updates.items() if key not in (extra_facts or {})}})
                prepared = prepared.derive({"node_source_context":local},
                    key=("node_source_context",session.snapshot(local)))
                local_view = session.facts.store.capture({"source_context":local},
                    key=("node",session.snapshot(local)),scope={"files":tuple(item.path for item in local.files)})
                local_view = local_view.derive(project_rule_facts(plan,local,
                    session.project_facts_for(local_view),handlers=handlers))
                responsibility = (node.path,node.symbol,node.descriptor.to_dict(),implementation_identity)
                identity = (local_view.identity,responsibility)
                subject = {"type_key":node.type_key,"kind":"node","descriptor":node.descriptor,
                    "source_identity":identity,"owner":owner,"call_id":call_id,
                    **({"call_path":call.call_path} if call is not None else {})}
                private_context = prepared.context(phase,subject)
                context = local_view.context(phase,subject)
                if call is not None:
                    private_context = replace(private_context,facts={**private_context.facts,"call":call})
                    context = replace(context,facts={**context.facts,"call":call})
                native = native_rule_bindings(registry,rules)
                origins = native_rule_origins(registry)
                core_handlers = tuple(value for key,value in native.items() if callable(value)
                    and getattr(origins.get(("rules",key)),"plugin_id","") == "vibeflow.core")
                native = {key:value for key,value in native.items() if callable(value) and (
                    getattr(origins.get(("rules",key)),"plugin_id","") == "vibeflow.core" or
                    any(value is core for core in core_handlers) and
                    handlers.get(rules[key].handler or key,handlers.get(key)) is value)}
                context = replace(context,subject={**context.subject,"source_cache_identities":{
                    invocation.rule.id:(prepared.identity,responsibility) for invocation in plan.invocations
                    if callable(native.get(invocation.rule.id))}})
                public_handlers = bind_native_analysis(handlers, native, private_context)
                result = execute_rule_plan(plan,context,handlers=public_handlers,source_cache=source_cache)
                result = replace(result, selection=selection.to_dict(),
                    scope={"kind":"node", "call_path": call.call_path if call is not None else ()})
                executions.append(result)
                # Core suppresses duplicate top-level findings on cache hits.
                # A new adapter/binding still needs the actual cached diagnostics.
                diagnostics = tuple((invocation_id,item) for invocation_id,value in result.results.items() for item in value.findings)
                for invocation_id,item in diagnostics:
                    invocation = next(value for value in plan.invocations if value.id == invocation_id)
                    definition = invocation.rule
                    association = ((owner,call_id),)
                    inputs = {name:result.results[provider].records[output]
                              for name,(provider,output) in invocation.inputs.items()
                              if output in result.results[provider].records}
                    inputs_key = record_inputs_fingerprint(inputs)
                    effective_call = value_fingerprint((definition.id,invocation.params,inputs_key))
                    if definition.scope != "source" or inputs_key is None:
                        effective_call += value_fingerprint((selected_id,owner,call_id,invocation_id))
                    diagnostic_key = node.type_key, (association if definition.scope != "source" else ()), effective_call, value_fingerprint({field.name:getattr(item,field.name) for field in fields(item)})
                    if diagnostic_key in seen_diagnostics:
                        index = seen_diagnostics[diagnostic_key]
                        previous = findings[index]
                        calls = list(previous.details.get("calls", ()))
                        related = {"owner": owner, "node": call_id}
                        if related not in calls:
                            calls.append(related)
                        findings[index] = replace(previous, details={**previous.details, "calls": calls})
                        continue
                    seen_diagnostics[diagnostic_key] = len(findings)
                    location = str(item.source_location.get("path",node.path))
                    source = next((file for file in source_context.files if file.path == location),None)
                    findings.append(replace(item,details={**item.details,"node_type":node.type_key,
                        "calls":[{"owner":scope,"node":call} for scope,call in association]},
                        root_id=item.root_id or (source.root_id if source else node.root_id),source_path=item.source_path or location))
                for invocation_id,item in result.results.items():
                    if item.state != "completed" and not any(finding.severity == "error" for finding in item.findings):
                        findings.append(HealthFinding(rule_id="RULE.SOURCE.UNAVAILABLE",severity="error",object_type="node",object_id=node.type_key,
                            message=f"rule '{invocation_id}' did not complete ({item.state})",failure_layer="rule",
                            definition_id=next(value.rule.id for value in plan.invocations if value.id == invocation_id),
                            source_location={"path":node.path,"line":1},source_path=node.path,root_id=node.root_id,
                            details={"state":item.state,"calls":[{"owner":owner,"node":call_id}]}))
                    if item.state == "completed":
                        invocation = next(value for value in plan.invocations if value.id == invocation_id)
                        for record in item.records.values():
                            if record.type_id == "vibeflow.node_metrics.v1":
                                metrics[node.type_key] = record.value
                                call_metrics[(owner,call_id)] = record.value
                            if record.type_id == "vibeflow.effect_policy.v1":
                                scope = str(record.value.get("effect_scope","unconstrained"))
                                policy_scopes.setdefault(node.type_key,set()).add(scope)
                                call_policy_scopes.setdefault((owner,call_id),set()).add(scope)
                                if invocation.rule.scope == "call":
                                    call_scoped_types.add(node.type_key)
                                call = source_context.call(owner,call_id)
                                call_policies.setdefault((owner,call_id),[]).append({"definition_id":invocation.rule.id,
                                    "ruleset_id":selected_id if isinstance(selected_id, str) else "rule:"+selected_id.rule_id,"rule_call_id":invocation_id,"scope":invocation.rule.scope,
                                    "value":plain(record.value),"call_path":call.call_path if call is not None else ()})
        selected_scopes = policy_scopes.get(node.type_key,set())
        actual_scopes = {next(iter(value)) if len(value) == 1 else "mixed" if value else "unconstrained"
            for key,value in call_policy_scopes.items() if key in set(node.calls or (("source",node.type_key),))}
        if len(actual_scopes) > 1:
            selected_scopes = actual_scopes
        scopes[node.type_key] = "unavailable" if node.type_key in unavailable_types else "mixed" if node.type_key in call_scoped_types else next(iter(selected_scopes)) if len(selected_scopes) == 1 else "mixed" if selected_scopes else "unconstrained"
        if phase in {"static","run"}:
            registry.record_effect_policy(node.type_key,scopes[node.type_key])
    call_scopes = {key:next(iter(value)) if len(value) == 1 else "mixed" if value else "unconstrained" for key,value in call_policy_scopes.items()}
    if phase in {"static", "run"}:
        session.call_effect_scopes.update(call_scopes)
        session.call_metrics.update(call_metrics)
        registry.call_effect_scopes.update({call.call_path: call_scopes[(call.owner, call.node_id)]
            for call in source_context.calls if (call.owner, call.node_id) in call_scopes})
    from vibeflow.targets.python.project.resource_rules import review_reached_base_libs
    entries = ()
    if selected_types is not None:
        entries = tuple(item["path"] for item in base_context.facts.get("source_owners", ())
                        if item["kind"] == "node" and item["id"] in selected_types)
        if not entries:
            entries = tuple(node.path for node in source_context.nodes if node.type_key in selected_types)
    library_findings, library_executions = review_reached_base_libs(registry,source_context,rules=rules,rulesets=rulesets,
        handlers=handlers,phase=phase,purity_policy=purity_policy,session=session,entry_paths=entries)
    findings.extend(library_findings)
    executions.extend(library_executions)
    report = PythonRuleReport(tuple(findings),tuple(executions),metrics,scopes,call_scopes,{key:tuple(value) for key,value in call_policies.items()},call_metrics, tuple(selections))
    if phase == "import" and not any(item.severity == "error" for item in findings):
        for node in source_context.nodes:
            if selected_types is None or node.type_key in selected_types:
                related = tuple(item for item in findings if item.details.get("node_type", item.subject_id) == node.type_key)
                from vibeflow.targets.python.project.fact_views import catalog_key
                session.node_import_results[node.type_key] = ((session.snapshot(source_context), catalog_key(registry)), replace(report, findings=related))
    return report

__all__ = ["PythonRuleReport","execute_python_node_rules","rule_resources","selected_effect_scope"]
