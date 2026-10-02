"""Rules over portable implementation metrics, without source inspection."""

from dataclasses import asdict

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.core.rules.models import plain


def _result(context, items):
    return RuleResult({"diagnostics": RuleRecord("vibeflow.implementation_diagnostics.v1", [asdict(item) for item in items])},
        tuple(HealthFinding(rule_id=item.rule_id, severity=item.severity, object_type="implementation",
                            object_id=str(context.subject.get("id", "")), message=item.message,
                            suggested_fix_type=item.suggested_fix_type, details=item.details) for item in items))


def _node(context, inputs, params):
    from vibeflow.core.quality.implementation import _node_implementation_facts
    return _result(context, _node_implementation_facts(context.require("metrics"), context.require("limits")))


def _base_lib(context, inputs, params):
    from vibeflow.core.quality.implementation import _base_lib_implementation_facts
    return _result(context, _base_lib_implementation_facts(context.require("metrics"), context.require("limits")))


def _chain(context, inputs, params):
    from vibeflow.core.quality.implementation import _base_lib_dependency_facts
    item = _base_lib_dependency_facts(context.require("chain"), context.require("limits"))
    return _result(context, () if item is None else (item,))


def implementation_resources():
    return tuple(RuleDescriptor("vibeflow.implementation." + name,
                               outputs={"diagnostics": "vibeflow.implementation_diagnostics.v1"})
                 for name in ("node", "base_lib", "dependency_chain"))


def implementation_handlers():
    return {"vibeflow.implementation.node": _node, "vibeflow.implementation.base_lib": _base_lib,
            "vibeflow.implementation.dependency_chain": _chain}


def evaluate_implementation_rule(name, **facts):
    from vibeflow.core.quality.implementation import ImplementationFinding
    resources = implementation_resources()
    rule_id = "vibeflow.implementation." + name
    descriptor = RulesetDescriptor(rule_id, (RuleCall("check", rule_id),))
    plan = compile_ruleset(descriptor, rules={item.id: item for item in resources})
    result = execute_rule_plan(plan, RuleContext(facts=facts), handlers=implementation_handlers())
    value = result.results["check"]
    if value.state != "completed":
        raise ValueError(value.findings[0].message)
    return tuple(ImplementationFinding(**plain(item)) for item in value.records["diagnostics"].value)


__all__ = ["evaluate_implementation_rule", "implementation_handlers", "implementation_resources"]
