"""Read JavaScript Rule defaults without loading Node or Rule code."""

from vibeflow.builtin.project_quality import bound_project_quality_defaults
from vibeflow.builtin.workflow import bound_workflow_depth_defaults
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy
from vibeflow.targets.shared.bindings import native_binding


def source_rule_defaults(handlers, *, rules, origins, depth=4, policy=None):
    return {**bound_project_quality_defaults(handlers, policy or javascript_quality_policy(), rules=rules, origins=origins),
            **bound_workflow_depth_defaults(handlers, depth, rules=rules, origins=origins)}


def workflow_rule_defaults(catalogs, depth):
    return bound_workflow_depth_defaults(
        {item.id: native_binding(catalogs, "rule", item.id) for item in catalogs.rules}, depth,
        rules={item.id:item for item in catalogs.rules}, origins=catalogs.origins)
