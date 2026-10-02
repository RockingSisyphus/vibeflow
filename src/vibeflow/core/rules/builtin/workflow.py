"""Rules over ordinary workflow facts; no source or language access."""

from dataclasses import dataclass, field

from vibeflow.core.findings import Finding
from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleResult, RulesetDescriptor, compile_ruleset, execute_rule_plan


@dataclass
class _Findings:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _flow(context, inputs, params):
    from vibeflow.core.quality.workflow_rules.flow import _flowchart_health_facts
    state = _Findings()
    _flowchart_health_facts(context.require("graph"), context.require("compiled"), state, owner=context.facts.get("owner", "pipeline"))
    return RuleResult(findings=tuple((*state.errors, *state.warnings)))


def _join(context, inputs, params):
    from vibeflow.core.quality.workflow_rules.flow import _join_policy_facts
    state = _Findings()
    _join_policy_facts(context.require("graph"), context.require("compiled"), state, owner=context.facts.get("owner", "pipeline"))
    return RuleResult(findings=tuple((*state.errors, *state.warnings)))


def _nodesets(context, inputs, params):
    from vibeflow.core.quality.nodesets import _nodeset_quality_facts
    return RuleResult(findings=_nodeset_quality_facts(context.require("graph"), max_depth=params["nodeset_max_depth"], warn_width=params["nodeset_warn_width"]))


def _duplicates(context, inputs, params):
    from vibeflow.core.quality.workflow_rules.duplicates import _duplicate_logic_facts
    return RuleResult(findings=_duplicate_logic_facts(context.require("fingerprints"), context.require("node_metrics"),
        node_types=context.facts.get("node_types"), node_similarities=context.facts.get("node_similarities")))


def _planned(context, inputs, params):
    from vibeflow.core.quality.workflow_rules.planned import _planned_health_facts
    events = _planned_health_facts(context.require("graph"))
    return RuleResult({"events": RuleRecord("vibeflow.planned_events.v1", events)},
                      tuple(item for item in events if isinstance(item, Finding)))


def workflow_topic_resources():
    return (
        RuleDescriptor("vibeflow.graph.flow"), RuleDescriptor("vibeflow.graph.join"),
        RuleDescriptor("vibeflow.graph.nodesets", params_schema={"nodeset_max_depth": {"type": "integer"}, "nodeset_warn_width": {"type": "integer"}},
                       params_defaults={"nodeset_max_depth": 4, "nodeset_warn_width": 10}),
        RuleDescriptor("vibeflow.graph.duplicates"),
        RuleDescriptor("vibeflow.graph.planned", outputs={"events": "vibeflow.planned_events.v1"}),
    )


def workflow_topic_handlers():
    return {"vibeflow.graph.flow": _flow, "vibeflow.graph.join": _join, "vibeflow.graph.nodesets": _nodesets,
            "vibeflow.graph.duplicates": _duplicates, "vibeflow.graph.planned": _planned}


def evaluate_workflow_topic(topic, *, params=None, **facts):
    resources = workflow_topic_resources()
    rule_id = "vibeflow.graph." + topic
    descriptor = RulesetDescriptor(rule_id, (RuleCall("check", rule_id, params=params or {}),))
    result = execute_rule_plan(compile_ruleset(descriptor, rules={item.id: item for item in resources}),
                              RuleContext(facts=facts), handlers=workflow_topic_handlers())
    return result.results["check"]


def workflow_rule_checks(context, inputs, params):
    """Default workflow checker; replacements can choose another callable."""
    findings = []
    for checker in (_flow, _join, _nodesets):
        findings.extend(checker(context, inputs, params).findings)
    if "fingerprints" in context.facts and "node_metrics" in context.facts:
        findings.extend(_duplicates(context, inputs, params).findings)
    planned = _planned(context, inputs, params)
    findings.extend(planned.findings)
    return RuleResult({"planned_events": planned.records["events"]}, tuple(findings))


__all__ = ["evaluate_workflow_topic", "workflow_rule_checks", "workflow_topic_handlers", "workflow_topic_resources"]
