"""Read JavaScript Rule defaults without loading Node or Rule code."""

from vibeflow.targets.javascript.rules.source_quality import bound_source_quality_defaults
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy


def source_rule_defaults(handlers, *, rules, origins, policy=None):
    return bound_source_quality_defaults(handlers, policy or javascript_quality_policy(), rules=rules, origins=origins)
