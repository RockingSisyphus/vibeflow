"""Execute declared rule selections against Python Target source facts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Mapping

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules import RuleContext, RuleGraphError, compile_ruleset, execute_rule_plan, rule_graph_error_finding
from vibeflow.core.rules.builtin import builtin_rule_resources
from vibeflow.targets.python.quality.rules import python_rule_handlers


@dataclass(frozen=True)
class PythonRuleReport:
    findings: tuple[Finding, ...] = ()
    executions: tuple[object, ...] = ()
    node_metrics: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    effect_scopes: Mapping[str, str] = field(default_factory=dict)
    call_effect_scopes: Mapping[tuple[str,str],str] = field(default_factory=dict)
    call_effect_policies: Mapping[tuple[str,str],tuple[Mapping[str,object],...]] = field(default_factory=dict)
    call_node_metrics: Mapping[tuple[str,str],Mapping[str,object]] = field(default_factory=dict)


def rule_resources(registry, *, purity_policy=None, quality_policy=None):
    built_rules, built_sets = builtin_rule_resources()
    rules = {item.id: item for item in built_rules}
    rulesets = {item.id: item for item in built_sets}
    origins = {(kind, item.id): f"builtin:{item.id}" for kind, items in (("rule", built_rules), ("ruleset", built_sets)) for item in items}
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
    from vibeflow.core.rules.builtin.project_quality import project_quality_rule_defaults
    from vibeflow.targets.python.quality.project_context import source_quality_policy
    for rule_id,defaults in project_quality_rule_defaults(quality_policy or source_quality_policy(purity_policy)).items():
        if rule_id in rules:
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
        except RuleGraphError:
            return "unavailable"
        for invocation in plan.invocations:
            if invocation.rule.id == "vibeflow.no_side_effects":
                scopes.add(str(invocation.params["effect_scope"]))
    return next(iter(scopes)) if len(scopes) == 1 else "mixed" if scopes else "unconstrained"


def graph_error_finding(registry, error, *, object_type, object_id, fallback_path=""):
    source = str(error.details.get("source", ""))
    if source and not source.startswith("builtin:"):
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
    registry.configure_rule_defaults(purity_policy=purity_policy,quality_policy=quality_policy)
    try:
        rules, rulesets = rule_resources(registry,purity_policy=purity_policy,quality_policy=quality_policy)
    except RuleGraphError as exc:
        finding = graph_error_finding(registry,exc,object_type="rule",object_id=str(exc.details.get("resource_id","")))
        return PythonRuleReport(findings=(finding,),effect_scopes={node.type_key:"unavailable" for node in source_context.nodes})
    handlers = {**python_rule_handlers(), **dict(extra_handlers or {})}
    custom = getattr(registry, "rule_handler_loader", None)
    findings = []
    executions = []
    metrics = {}
    call_metrics = {}
    scopes = {}
    policy_scopes = {}
    call_policy_scopes = {}
    call_policies = {}
    call_scoped_types = set()
    unavailable_types = set()
    source_cache = {}
    project_fact_cache = {}
    from vibeflow.targets.python.quality.project_context import project_rule_facts
    if phase in {"static","run"}:
        registry.reset_effect_policies(node.type_key for node in source_context.nodes)
    from vibeflow.core.rules.models import plain
    source_facts = {"files":[(item.path,item.module,item.root_id,item.text) for item in source_context.files],
        "calls":[(item.owner,item.node_id,item.type_key,plain(item.params),item.source_path,item.local_id,item.call_path) for item in source_context.calls],
        "imports":[(item.path,item.specifier,item.module,item.resolved_path,item.symbol,item.alias,item.line,item.column) for item in source_context.imports],
        "nodes":[(item.descriptor.to_dict(),item.path,item.symbol,item.root_id,item.calls) for item in source_context.nodes]}
    snapshot = hashlib.sha256(json.dumps(source_facts,sort_keys=True).encode()).hexdigest()
    for node in source_context.nodes:
        identity = ("python",node.path,node.symbol,json.dumps(node.descriptor.to_dict(),sort_keys=True),snapshot)
        for selected_id in registry.rulesets(node.type_key):
            try:
                plan = compile_ruleset(selected_id, rules=rules, rulesets=rulesets, entrypoint=phase)
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
            from vibeflow.core.descriptors.contributions import contribution_facts
            contributions = contribution_facts(registry.loaded_plugins.catalogs) if hasattr(registry, "loaded_plugins") else {}
            facts = {**contributions, "source_load_states":getattr(registry, "source_load_states", {}),
                     **project_rule_facts(plan,source_context,project_fact_cache),"source_context":source_context,
                     "node_catalog":tuple(registry.descriptor(key) for key in registry.available()), **dict(extra_facts or {})}
            if purity_policy is not None:
                facts["purity_policy"] = purity_policy
            for owner, call_id in node.calls or (("source",node.type_key),):
                context = RuleContext(facts={**facts,"call":source_context.call(owner,call_id)},subject={"type_key":node.type_key,"kind":"node","descriptor":node.descriptor,
                    "source_identity":identity,"calls":node.calls,"owner":owner,"call_id":call_id},
                    scope={"files":tuple(item.path for item in source_context.files),"workflow":owner,
                        "workflows":tuple(sorted({call.owner for call in source_context.calls}))},phase=phase,target="python")
                result = execute_rule_plan(plan,context,handlers=handlers,source_cache=source_cache)
                executions.append(result)
                for item in result.findings:
                    definition = rules.get(getattr(item,"definition_id", ""))
                    association = node.calls if definition is not None and definition.scope == "source" else ((owner,call_id),)
                    location = str(item.source_location.get("path",node.path))
                    source = next((file for file in source_context.files if file.path == location),None)
                    findings.append(replace(item,details={**item.details,"node_type":node.type_key,
                        "calls":item.details.get("calls",[{"owner":scope,"node":call} for scope,call in association])},
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
                                    "ruleset_id":selected_id,"rule_call_id":invocation_id,"scope":invocation.rule.scope,
                                    "value":plain(record.value),"call_path":call.call_path if call is not None else ()})
        selected_scopes = policy_scopes.get(node.type_key,set())
        scopes[node.type_key] = "unavailable" if node.type_key in unavailable_types else "mixed" if node.type_key in call_scoped_types else next(iter(selected_scopes)) if len(selected_scopes) == 1 else "mixed" if selected_scopes else "unconstrained"
        if phase in {"static","run"}:
            registry.record_effect_policy(node.type_key,scopes[node.type_key])
    call_scopes = {key:next(iter(value)) if len(value) == 1 else "mixed" for key,value in call_policy_scopes.items()}
    from vibeflow.targets.python.project.resource_rules import review_reached_base_libs
    library_findings, library_executions = review_reached_base_libs(registry,source_context,rules=rules,rulesets=rulesets,
        handlers=handlers,phase=phase,purity_policy=purity_policy)
    findings.extend(library_findings)
    executions.extend(library_executions)
    return PythonRuleReport(tuple(findings),tuple(executions),metrics,scopes,call_scopes,{key:tuple(value) for key,value in call_policies.items()},call_metrics)

__all__ = ["PythonRuleReport","execute_python_node_rules","rule_resources","selected_effect_scope"]
