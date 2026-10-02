"""Built-in rule resources; implementation callables are supplied by Targets."""

from vibeflow.core.rules.builtin.effects import builtin_effect_resources
from vibeflow.core.rules.builtin.implementation import implementation_handlers, implementation_resources
from vibeflow.core.rules.builtin.project_quality import project_quality_handlers, project_quality_resources, project_quality_rule_defaults
from vibeflow.core.rules.builtin.workflow import workflow_rule_checks, workflow_topic_handlers, workflow_topic_resources


def builtin_rule_resources():
    """All public builtin resources, registered once by the composition root."""
    rules, rulesets = builtin_effect_resources()
    project_rules, project_set = project_quality_resources()
    return (*rules, *implementation_resources(), *project_rules, *workflow_topic_resources()), (*rulesets, project_set)


__all__ = ["builtin_effect_resources", "builtin_rule_resources", "implementation_handlers", "implementation_resources", "project_quality_handlers", "project_quality_resources", "project_quality_rule_defaults", "workflow_rule_checks", "workflow_topic_handlers", "workflow_topic_resources"]
