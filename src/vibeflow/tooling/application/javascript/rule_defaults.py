"""Read JavaScript Rule defaults without loading Node or Rule code."""

from vibeflow.core.rules.builtin import project_quality_rule_defaults
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy


def source_rule_defaults():
    return project_quality_rule_defaults(javascript_quality_policy())
