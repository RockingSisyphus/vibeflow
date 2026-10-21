"""Python-specific leaf review in the explicit Workflow dependency plan."""
from dataclasses import replace

from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.targets.shared.rule_support.workflow import graph_contexts, review_graph


def workflow_review(context, inputs, params):
    from vibeflow.targets.python.quality.workflow.validation import _HealthValidationState
    from vibeflow.targets.python.rules.graph.node_config import current_node_configuration_findings
    from vibeflow.targets.python.rules.graph.nodeset_types import current_nodeset_declaration_findings
    from vibeflow.targets.python.rules.graph.planned_implementation import python_stub_findings
    from vibeflow.targets.shared.quality_support.workflow_rules.planned import current_graph_planned_events, PlannedImplementationCheck
    from vibeflow.targets.python.rules.graph.mainline import append_mainline_health
    state, findings = _HealthValidationState(), []
    registry = context.facts.get("registry")
    for local in graph_contexts(context, inputs):
        graph = local.require("graph")
        current = list(review_graph(local))
        if registry is not None:
            current.extend(current_node_configuration_findings(local.facts.get("declaration_graph", graph),
                registry=registry, owner=local.facts["owner"], global_config=local.facts.get("global_config"),
                overrides=local.facts.get("overrides", {})))
            current.extend(current_nodeset_declaration_findings(local.facts.get("declaration_graph", graph),
                definition=local.facts.get("definition"), registry=registry, owner=local.facts["owner"]))
            if local.facts.get("compiled") is not None:
                before = len(state.errors), len(state.warnings)
                append_mainline_health(graph, local.require("compiled"), state, registry=registry,
                    owner=local.facts["owner"], include_nested=False)
                current.extend((*state.errors[before[0]:], *state.warnings[before[1]:]))
        for event in current_graph_planned_events(graph, owner=local.facts["owner"], definition=local.facts.get("definition")):
            if isinstance(event, PlannedImplementationCheck):
                current.extend(python_stub_findings(event))
        findings.extend(replace(item, details={**item.details, "owner": local.facts["owner"],
            "call_path": local.facts.get("call_path", ())}) for item in current)
    return RuleResult({"review": RuleRecord("vibeflow.workflow_review.v1", {"mainline": state.mainline})}, tuple(findings))
