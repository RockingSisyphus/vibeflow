"""Rules over ordinary workflow facts; no source or language access."""

from dataclasses import dataclass, field, replace

from vibeflow.core.findings import Finding
from vibeflow.core.rules import RuleRecord, RuleResult


@dataclass
class _Findings:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _entry_graphs(context):
    graph, compiled = context.require("graph"), context.require("compiled")
    if not graph.entries:
        yield graph, compiled, None
    else:
        from vibeflow.core.workflows.entries import project_entry
        for name in graph.entries:
            selected, routes = project_entry(graph, compiled, name)
            yield selected, routes, name


def _entry_findings(findings, entry):
    return tuple(replace(item, details={**item.details, "entry": entry}) if entry is not None else item
                 for item in findings)


def _flow(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.flow import _flowchart_health_facts
    from vibeflow.targets.shared.quality_support.workflow_rules.flow_data import append_data_contract_warnings
    findings = []
    graph, compiled = context.require("graph"), context.require("compiled")
    state = _Findings()
    _flowchart_health_facts(graph, compiled, state, owner=context.facts.get("owner", "pipeline"),
        entry_starts={item.start for item in graph.entries.values()} if graph.entries else None)
    findings.extend((*state.errors, *state.warnings))
    for graph, compiled, entry in _entry_graphs(context):
        state = _Findings()
        append_data_contract_warnings(graph, compiled, state,
                                  owner=context.facts.get("owner", "pipeline"),
                                  runtime_flow_kinds=context.facts.get("runtime_flow_kinds"))
        findings.extend(_entry_findings((*state.errors, *state.warnings), entry))
    return RuleResult(findings=tuple(findings))


def _join(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.joins import append_join_policy_health
    findings = []
    for graph, compiled, entry in _entry_graphs(context):
        state = _Findings()
        append_join_policy_health(graph, compiled, state, owner=context.facts.get("owner", "pipeline"))
        findings.extend(_entry_findings((*state.errors, *state.warnings), entry))
    return RuleResult(findings=tuple(findings))


def _nodesets(context, inputs, params):
    from vibeflow.targets.shared.quality_support.nodeset_types import _nodeset_quality_facts
    return RuleResult(findings=_nodeset_quality_facts(context.require("graph"), max_depth=params["nodeset_max_depth"], warn_width=params["nodeset_warn_width"]))


def _duplicates(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.duplicates import _duplicate_logic_facts
    return RuleResult(findings=_duplicate_logic_facts(context.require("fingerprints"), context.require("node_metrics"),
        call_definitions=context.facts.get("call_definitions"), node_similarities=context.facts.get("node_similarities")))


def _planned(context, inputs, params):
    from vibeflow.targets.shared.quality_support.workflow_rules.planned import current_graph_planned_events
    events = current_graph_planned_events(context.require("graph"), owner=context.facts.get("owner", "pipeline"), definition=context.facts.get("definition"))
    return RuleResult({"events": RuleRecord("vibeflow.planned_events.v1", events)},
                      tuple(item for item in events if isinstance(item, Finding)))
