"""Fixed resources supplied by the automatically loaded standard plugin."""

from vibeflow.builtin.effects import builtin_effect_resources
from vibeflow.builtin.implementation import implementation_handlers, implementation_resources
from vibeflow.builtin.project_quality import project_quality_handlers, project_quality_resources, project_quality_rule_defaults
from vibeflow.builtin.workflow import workflow_rule_checks, workflow_topic_handlers, workflow_topic_resources


def builtin_rule_resources():
    """All public builtin resources, registered once by the composition root."""
    rules, rulesets = builtin_effect_resources()
    project_rules, project_set = project_quality_resources()
    return (*rules, *implementation_resources(), *project_rules, *workflow_topic_resources()), (*rulesets, project_set)


def builtin_declaration_origins():
    """Locate fixed declarations at their defining factories, independently of bindings."""
    import inspect
    from vibeflow.core.descriptors.contributions import ResourceOrigin, resource_kind
    origins = {}
    effect_rules, effect_sets = builtin_effect_resources()
    project_rules, project_set = project_quality_resources()
    for factory, declarations in (
        (builtin_effect_resources, (*effect_rules, *effect_sets)),
        (implementation_resources, implementation_resources()),
        (project_quality_resources, (*project_rules, project_set)),
        (workflow_topic_resources, workflow_topic_resources()),
    ):
        origin = ResourceOrigin("vibeflow.core", str(inspect.getsourcefile(factory)),
            inspect.getsourcelines(factory)[1], symbol=factory.__qualname__)
        for descriptor in declarations:
            origins[(resource_kind(descriptor), descriptor.id)] = origin
    return origins


__all__ = ["builtin_effect_resources", "builtin_rule_resources", "implementation_handlers", "implementation_resources", "project_quality_handlers", "project_quality_resources", "project_quality_rule_defaults", "workflow_rule_checks", "workflow_topic_handlers", "workflow_topic_resources"]
