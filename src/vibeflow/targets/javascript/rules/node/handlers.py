"""Native JavaScript analysis bindings contributed by the standard plugin."""
from typing import Any, Mapping
from vibeflow.core.rules import RuleContext, RuleRecord, RuleResult
from vibeflow.targets.shared.rule_support.import_policy import normalized_import_policy


def _effect_parameters(params: Mapping[str, Any]) -> str:
    scope = params.get("effect_scope", "none")
    if scope not in {"none", "terminal", "python_io", "global_state", "trusted"}:
        raise ValueError(f"unsupported JavaScript effect_scope: {scope!r}")
    normalized_import_policy(params)
    return scope


def javascript_source_bindings() -> Mapping[str, Any]:
    from vibeflow.targets.javascript.build.analysis_service import source_check
    from vibeflow.targets.javascript.quality.diagnostics import rule_finding
    def effects(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        scope = _effect_parameters(params)
        findings = source_check(context, ("module_state", "host_io", "effect_imports"), "vibeflow.no_side_effects", params=params)
        allowed = {"none": [], "terminal": ["terminal"], "python_io": ["python_io"], "global_state": ["global_state"], "trusted": []}[scope]
        return RuleResult(records={"effect_policy": RuleRecord("vibeflow.effect_policy.v1", {"effect_scope": scope, "allowed_effects": allowed})}, findings=findings)
    def architecture(context, inputs, params):
        return RuleResult(findings=source_check(context, ("architecture",), "vibeflow.node_architecture"))
    def input_writes(context, inputs, params):
        return RuleResult(state="unavailable")
    def interface(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        return RuleResult()
    def asynchronous(context, inputs, params):
        return RuleResult(findings=source_check(context, ("completion",), "vibeflow.async_lifecycle"))
    def imports(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        _effect_parameters(params)
        return RuleResult(findings=source_check(context, ("purity", "imports"), "vibeflow.import_side_effects", params=params))
    def measured(context: RuleContext, params: Mapping[str, Any], *, topic="all"):
        from vibeflow.targets.javascript.build.analysis_service import measure_builtin_resource
        return measure_builtin_resource(context, params, topic=topic)
    def maintainability(context, inputs, params):
        result = measured(context, params)
        if isinstance(result, RuleResult):
            return result
        found, metrics = result
        return RuleResult(records={"metrics": RuleRecord("vibeflow.node_metrics.v1", metrics)}, findings=tuple(rule_finding(item.to_dict(), "vibeflow.maintainability", context) for item in found))
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
    return {"vibeflow.async_lifecycle": asynchronous, "vibeflow.no_side_effects": effects, "vibeflow.node_interface": interface,
            "vibeflow.node_architecture": architecture, "vibeflow.input_writes": input_writes,
            "vibeflow.import_side_effects": imports, "vibeflow.maintainability": maintainability,
            **{"vibeflow.implementation." + topic: implementation(topic) for topic in ("node", "base_lib", "dependency_chain")}}
