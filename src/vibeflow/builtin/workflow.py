"""Rules over ordinary workflow facts; no source or language access."""

from dataclasses import dataclass, field
from inspect import unwrap

from vibeflow.core.findings import Finding
from vibeflow.core.rules import RuleDescriptor, RuleRecord, RuleResult


@dataclass
class _Findings:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _flow(context, inputs, params):
    from vibeflow.core.quality.workflow_rules.flow import _flowchart_health_facts
    from vibeflow.core.quality.workflow_rules.flow_data import append_data_contract_warnings
    state = _Findings()
    _flowchart_health_facts(context.require("graph"), context.require("compiled"), state, owner=context.facts.get("owner", "pipeline"))
    append_data_contract_warnings(context.require("graph"), context.require("compiled"), state,
                                  owner=context.facts.get("owner", "pipeline"),
                                  runtime_flow_kinds=context.facts.get("runtime_flow_kinds"))
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


def workflow_rule_checks(context, inputs, params):
    """Default workflow checker; replacements can choose another callable."""
    findings = []
    for checker in (_flow, _join, _nodesets):
        findings.extend(checker(context, inputs, params).findings)
    if "fingerprints" in context.facts and "node_metrics" in context.facts:
        findings.extend(_duplicates(context, inputs, params).findings)
    planned = _planned(context, inputs, params)
    findings.extend(planned.findings)
    return RuleResult({"planned_events": planned.records["events"],
                       "workflow_review": RuleRecord("vibeflow.workflow_review.v1", {"mainline": {}})}, tuple(findings))


__all__ = ["workflow_rule_checks", "workflow_topic_handlers", "workflow_topic_resources"]


def default_workflow_rulesets():
    """Standard workflow selection applied only at the composition boundary."""
    return ("vibeflow.workflow",)


def bound_workflow_depth_defaults(handlers, depth, *, rules, origins):
    """Apply project depth configuration to the actual standard consumers."""
    from vibeflow.builtin.effects import builtin_effect_resources
    from vibeflow.builtin.plugin import configured_rule_defaults
    consumers = ((_nodesets, workflow_topic_resources), (workflow_rule_checks, builtin_effect_resources))
    result = {}
    for resource_id, handler in handlers.items():
        check = unwrap(handler) if handler is not None else None
        for native, factory in consumers:
            if check is native and resource_id in rules:
                configured = configured_rule_defaults(rules[resource_id],
                    {"nodeset_max_depth": depth}, origins.get(("rules", resource_id)), factory=factory)
                if configured:
                    result[resource_id] = configured
                break
    return result
