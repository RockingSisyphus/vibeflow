"""Python workflow review; selected through the same Rule graph as source checks."""
from dataclasses import replace
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.builtin.workflow import workflow_topic_handlers


def workflow(context, inputs, params, *, definition_cache=None):
    from vibeflow.targets.python.quality.workflow.validation import _HealthValidationState
    from vibeflow.targets.python.quality.workflow.node_config import node_configuration_findings
    from vibeflow.targets.python.quality.workflow.nodesets import nodeset_declaration_findings
    from vibeflow.targets.python.quality.rules.planned_implementation import python_stub_findings
    from vibeflow.core.quality.workflow_rules.planned import PlannedImplementationCheck
    from vibeflow.targets.python.quality.workflow.mainline import append_mainline_health
    graph, compiled = context.require("graph"), context.require("compiled")
    registry = context.facts.get("registry")
    state = _HealthValidationState()
    # Nested workflows select their own rules; caller rules may inspect call declarations.
    scoped = replace(graph, nodesets={key: value for key, value in graph.nodesets.items() if value.graph.rulesets})
    core_context = context
    topics = workflow_topic_handlers()
    local = [topics["vibeflow.graph." + name](core_context, inputs, params) for name in ("flow", "join")]
    if "fingerprints" in core_context.facts and "node_metrics" in core_context.facts:
        local.append(topics["vibeflow.graph.duplicates"](core_context, inputs, params))
    identity = definition_cache.identity(scoped, context, inputs, params) if definition_cache is not None else None
    definitions = definition_cache.get(identity) if identity is not None else None
    reused = definitions is not None
    if definitions is None:
        definition_context = replace(context, facts={**context.facts, "graph": scoped})
        nodesets = topics["vibeflow.graph.nodesets"](definition_context, inputs, params)
        planned = topics["vibeflow.graph.planned"](definition_context, inputs, params)
        for item in planned.records["events"].value:
            if isinstance(item, PlannedImplementationCheck):
                for finding in python_stub_findings(item):
                    (state.warnings if finding.severity == "warning" else state.errors).append(finding)
        if registry is not None:
            state.errors.extend(node_configuration_findings(graph, registry=registry, global_config=context.facts.get("global_config")))
            errors, warnings = nodeset_declaration_findings(graph, registry=registry, selected_only=True)
            state.errors.extend(errors)
            state.warnings.extend(warnings)
        definitions = RuleResult(records={"planned_events": planned.records["events"]}, findings=tuple(
            replace(item, details={**item.details, "definition_review": True})
            for item in (*nodesets.findings, *planned.findings, *state.errors, *state.warnings)))
        if identity is not None:
            definition_cache.store(identity, scoped, definitions)
        state = _HealthValidationState()
    if registry is not None:
        append_mainline_health(graph, compiled, state, registry=registry, owner=context.facts.get("owner","pipeline"), include_nested=False)
    for node in graph.nodes:
        if not node.id or node.id != node.id.lower() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in node.id):
            from vibeflow.core.findings import HealthFinding
            state.warnings.append(HealthFinding(rule_id="GRAPH.SMELL.CONFUSING_NODE_NAME", severity="warning", object_type="node", object_id=node.id,
                failure_layer="topology", message=f"node name should use lowercase snake_case: {node.id}"))
        for name in ("display_name", "description"):
            if not getattr(node.metadata, name, "").strip():
                from vibeflow.core.findings import HealthFinding
                state.warnings.append(HealthFinding(rule_id="GRAPH.SMELL.MISSING_NODE_" + name.upper(), severity="warning",
                    object_type="node", object_id=node.id, failure_layer="topology", message=f"config node '{node.id}' should declare {name} for readable SVG diagrams",
                    details={"field": name, "owner": context.facts.get("owner", "pipeline")}))
    from vibeflow.core.findings import HealthFinding
    advisory = tuple(HealthFinding(rule_id=item.rule_id,severity=str(item.details.get("severity","warning")),
        object_type="node",object_id=item.source,message=item.message,failure_layer="topology",
        details={**item.details,"source":item.source,"target":item.target})
        for item in context.facts.get("compilation_findings", ())) if context.facts.get("owner") == "pipeline" else ()
    return RuleResult(records={**definitions.records,"workflow_review":RuleRecord("vibeflow.workflow_review.v1",{
        "mainline":state.mainline,"definition_review_reused":reused})}, findings=tuple((
        *(item for result in local for item in result.findings), *definitions.findings, *advisory, *state.errors, *state.warnings)))
