"""Rules over ordinary workflow facts; no source or language access."""

from dataclasses import dataclass, field
from inspect import unwrap

from vibeflow.core.findings import Finding
from vibeflow.core.rules import RuleRecord, RuleResult


@dataclass
class _Findings:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _flow(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.flow import _flowchart_health_facts
    from vibeflow.targets.shared.quality_support.workflow_rules.flow_data import append_data_contract_warnings
    state = _Findings()
    _flowchart_health_facts(context.require("graph"), context.require("compiled"), state, owner=context.facts.get("owner", "pipeline"))
    append_data_contract_warnings(context.require("graph"), context.require("compiled"), state,
                                  owner=context.facts.get("owner", "pipeline"),
                                  runtime_flow_kinds=context.facts.get("runtime_flow_kinds"))
    return RuleResult(findings=tuple((*state.errors, *state.warnings)))


def _join(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
    state = _Findings()
    append_join_policy_health(context.require("graph"), context.require("compiled"), state, owner=context.facts.get("owner", "pipeline"))
    return RuleResult(findings=tuple((*state.errors, *state.warnings)))


def _nodesets(context, inputs, params):
    from vibeflow.targets.shared.quality_support.nodesets import _nodeset_quality_facts
    return RuleResult(findings=_nodeset_quality_facts(context.require("graph"), max_depth=params["nodeset_max_depth"], warn_width=params["nodeset_warn_width"]))


def _duplicates(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.duplicates import _duplicate_logic_facts
    return RuleResult(findings=_duplicate_logic_facts(context.require("fingerprints"), context.require("node_metrics"),
        node_types=context.facts.get("node_types"), node_similarities=context.facts.get("node_similarities")))


def _planned(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.planned import current_graph_planned_events
    events = current_graph_planned_events(context.require("graph"), owner=context.facts.get("owner", "pipeline"), definition=context.facts.get("definition"))
    return RuleResult({"events": RuleRecord("vibeflow.planned_events.v1", events)},
                      tuple(item for item in events if isinstance(item, Finding)))
