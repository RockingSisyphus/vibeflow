"""python current-graph Rule definitions and bindings."""
from vibeflow.core.rules import RuleDescriptor
from vibeflow.targets.shared.rule_support.graph import _flow, _join, _nodesets, _duplicates, _planned


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
