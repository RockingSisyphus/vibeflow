"""Apply standard-plugin selections to missing workflow declaration fields."""
from collections.abc import Mapping

from vibeflow.builtin.workflow import default_workflow_rulesets


def with_workflow_rule_defaults(config):
    """Copy known graph scopes; explicit selections and invalid values are retained."""
    selected = dict(config)
    selected.setdefault("rulesets", default_workflow_rulesets())
    values = selected.get("nodesets")
    if isinstance(values, list):
        selected["nodesets"] = [with_workflow_rule_defaults(value) if isinstance(value, Mapping)
                               else value for value in values]
    pipeline = selected.get("pipeline")
    if isinstance(pipeline, Mapping) and isinstance(pipeline.get("nodesets"), list):
        pipeline = dict(pipeline)
        pipeline["nodesets"] = [with_workflow_rule_defaults(value) if isinstance(value, Mapping)
                               else value for value in pipeline["nodesets"]]
        selected["pipeline"] = pipeline
    return selected
