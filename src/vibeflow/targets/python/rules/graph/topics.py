"""python current-graph Rule definitions and bindings."""
from vibeflow.core.rules import RuleDescriptor
from vibeflow.targets.shared.rule_support.graph import _flow, _join, _nodesets, _duplicates, _planned


def workflow_topic_resources():
    return (
        RuleDescriptor("vibeflow.graph.flow", level="graph"), RuleDescriptor("vibeflow.graph.join", level="graph"),
        RuleDescriptor("vibeflow.graph.nodeset_types", params_schema={"nodeset_max_depth": {"type": "integer", "minimum": 1}, "nodeset_warn_width": {"type": "integer"}},
                       params_defaults={"nodeset_max_depth": 4, "nodeset_warn_width": 10}, level="graph"),
        RuleDescriptor("vibeflow.graph.duplicates", level="graph"),
        RuleDescriptor("vibeflow.graph.planned", outputs={"events": "vibeflow.planned_events.v1"}, level="graph"),
    )


def workflow_topic_handlers():
    return {"vibeflow.graph.flow": _flow, "vibeflow.graph.join": _join, "vibeflow.graph.nodeset_types": _nodesets,
            "vibeflow.graph.duplicates": _duplicates, "vibeflow.graph.planned": _planned}
