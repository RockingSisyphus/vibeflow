"""javascript Workflow analysis and review Rule definitions."""
from vibeflow.core.rules import RuleDescriptor
from vibeflow.targets.shared.rule_support.workflow import ANALYSIS, analysis, summary, review, nodesets, topic


def workflow_plan_resources():
    rules = [RuleDescriptor("vibeflow.workflow.analysis", outputs={"graphs": ANALYSIS})]
    for name in ("flow", "join", "nodesets", "duplicates", "planned", "review"):
        outputs = {"events": "vibeflow.planned_events.v1"} if name == "planned" else ({"review": "vibeflow.workflow_review.v1"} if name == "review" else {})
        schema = {"nodeset_max_depth": {"type": "integer"}, "nodeset_warn_width": {"type": "integer"}} if name == "nodesets" else {}
        defaults = {"nodeset_max_depth": 4, "nodeset_warn_width": 10} if name == "nodesets" else {}
        rules.append(RuleDescriptor("vibeflow.workflow." + name, inputs={"analysis": ANALYSIS}, outputs=outputs,
            params_schema=schema, params_defaults=defaults))
    rules.append(
        RuleDescriptor("vibeflow.workflow", description="Aggregate explicit workflow checks.",
            inputs={"events": "vibeflow.planned_events.v1", "review": "vibeflow.workflow_review.v1"},
            outputs={"planned_events": "vibeflow.planned_events.v1", "workflow_review": "vibeflow.workflow_review.v1"})
    )
    return tuple(rules)


def workflow_plan_handlers():
    return {"vibeflow.workflow.analysis": analysis, "vibeflow.workflow": summary,
        "vibeflow.workflow.review": review,
        **{"vibeflow.workflow." + name: topic(name) for name in ("flow", "join", "duplicates", "planned")},
        "vibeflow.workflow.nodesets": nodesets}
