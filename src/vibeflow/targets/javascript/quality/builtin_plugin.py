"""Native JavaScript analysis bindings contributed by the standard plugin."""
from dataclasses import replace
from functools import wraps
from typing import Any, Mapping
from vibeflow.core.rules import RuleContext, RuleRecord, RuleResult
from vibeflow.core.rules.models import RuleCall
from vibeflow.builtin.workflow import workflow_topic_handlers
from vibeflow.builtin.workflow_plan import workflow_plan_handlers
from vibeflow.builtin.project_quality import project_quality_handlers
from vibeflow.builtin.import_policy import normalized_import_policy


def _effect_parameters(params: Mapping[str, Any]) -> str:
    scope = params.get("effect_scope", "none")
    if scope not in {"none", "terminal", "python_io", "global_state", "trusted"}:
        raise ValueError(f"unsupported JavaScript effect_scope: {scope!r}")
    normalized_import_policy(params)
    return scope


def javascript_rule_bindings() -> Mapping[str, Any]:
    from vibeflow.targets.javascript.build.rule_session import _source_check, _finding
    def project_handler(checker):
        @wraps(checker, assigned=(), updated=())
        def check(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
            if not context.facts.get("evaluate_sources", True):
                return RuleResult(state="unavailable")
            if "project_facts" not in context.facts and "analysis_cache" in context.facts:
                context = replace(context, facts={**context.facts,
                    "project_facts": context.facts["analysis_cache"].project_facts(context.facts)})
            return checker(context, inputs, params)
        return check
    def effects(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        scope = _effect_parameters(params)
        findings = _source_check(context, ("module_state", "host_io", "effect_imports"), "vibeflow.no_side_effects", params=params)
        allowed = {"none": [], "terminal": ["terminal"], "python_io": ["python_io"], "global_state": ["global_state"], "trusted": []}[scope]
        return RuleResult(records={"effect_policy": RuleRecord("vibeflow.effect_policy.v1", {"effect_scope": scope, "allowed_effects": allowed})}, findings=findings)
    def architecture(context, inputs, params):
        return RuleResult(findings=_source_check(context, ("architecture",), "vibeflow.node_architecture"))
    def input_writes(context, inputs, params):
        return RuleResult(state="unavailable")
    def interface(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        return RuleResult(findings=_source_check(context, ("completion",), "vibeflow.node_interface"))
    def imports(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        _effect_parameters(params)
        return RuleResult(findings=_source_check(context, ("purity", "imports"), "vibeflow.import_side_effects", params=params))
    def measured(context: RuleContext, params: Mapping[str, Any], *, topic="all"):
        from vibeflow.targets.javascript.build.rule_session import measure_builtin_resource
        return measure_builtin_resource(context, params, topic=topic)
    def maintainability(context, inputs, params):
        result = measured(context, params)
        if isinstance(result, RuleResult):
            return result
        found, metrics = result
        return RuleResult(records={"metrics": RuleRecord("vibeflow.node_metrics.v1", metrics)}, findings=tuple(_finding(item.to_dict(), "vibeflow.maintainability", context) for item in found))
    def implementation(topic):
        def check(context, inputs, params):
            result = measured(context, params, topic=topic)
            if isinstance(result, RuleResult):
                return result
            found, _ = result
            records = [{"rule_id":item.rule_id,"severity":item.severity,"message":item.message,
                "suggested_fix_type":item.suggested_fix_type,"details":dict(item.details)} for item in found]
            return RuleResult({"diagnostics": RuleRecord("vibeflow.implementation_diagnostics.v1", records)}, tuple(found))
        return check
    return {"vibeflow.no_side_effects": effects, "vibeflow.node_interface": interface,
            "vibeflow.node_architecture": architecture, "vibeflow.input_writes": input_writes,
            "vibeflow.import_side_effects": imports, "vibeflow.maintainability": maintainability,
            **{"vibeflow.implementation." + topic: implementation(topic) for topic in ("node", "base_lib", "dependency_chain")},
            **workflow_plan_handlers(), **workflow_topic_handlers(),
            **{key: project_handler(checker) for key, checker in project_quality_handlers().items()}}



def builtin_plugin():
    from vibeflow.builtin import builtin_rule_resources, builtin_declaration_origins
    from vibeflow.builtin.plugin import make_builtin_plugin
    rules, rulesets = builtin_rule_resources()
    # The finite input rule describes Python syntax, so JavaScript's default
    # selections omit it. An explicit selection still reports unavailable.
    rulesets = tuple(replace(item,
        calls=tuple(call for call in item.calls if call.rule_id != "vibeflow.input_writes"),
        entrypoints={phase: tuple(name for name in names if name != "inputs")
                     for phase, names in item.entrypoints.items()}) for item in rulesets)
    # Module ownership is an independent selected architecture policy for
    # native JS libraries, plugins and host extensions as well as Nodes.
    rulesets = tuple(replace(item,
        calls=(*item.calls, RuleCall("architecture", rule_id="vibeflow.node_architecture")),
        entrypoints={phase: (*names, "architecture") if phase in {"static", "run"} else names
                     for phase, names in item.entrypoints.items()})
        if item.id in {"vibeflow.base_lib", "vibeflow.plugin", "vibeflow.host_extension"}
        else item for item in rulesets)
    # Check selected ownership before import purity can stop project binding.
    # Reuse the architecture Rule and the same native fact session.
    rulesets = tuple(replace(item,
        entrypoints={phase: (*names, "architecture")
                     if phase == "import" and "architecture" not in names else names
                     for phase, names in item.entrypoints.items()})
        if any(call.id == "architecture" for call in item.calls) else item
        for item in rulesets)
    return make_builtin_plugin(rules, rulesets, javascript_rule_bindings(), declaration_origins=builtin_declaration_origins())
