"""python Rule declarations, assembled through the public contribution model."""
from vibeflow.targets.python.rules.node.definitions import source_rule_resources, implementation_resources
from vibeflow.targets.python.rules.project import project_quality_resources, project_quality_handlers, project_quality_rule_defaults
from vibeflow.targets.python.rules.graph import workflow_topic_resources, workflow_topic_handlers, workflow_plan_resources


def builtin_rule_resources():
    from vibeflow.targets.python.rulesets import builtin_rulesets
    project_rules, _ = project_quality_resources()
    return (*source_rule_resources(), *implementation_resources(), *project_rules,
        *workflow_topic_resources(), *workflow_plan_resources()), builtin_rulesets()


def builtin_declaration_origins():
    import inspect
    from vibeflow.core.descriptors.contributions import ResourceOrigin, resource_kind
    from vibeflow.targets.python.rulesets import standard_rulesets, project_quality_ruleset
    origins = {}
    project_rules, _ = project_quality_resources()
    for factory, resources in ((source_rule_resources, source_rule_resources()),
            (implementation_resources, implementation_resources()), (project_quality_resources, project_rules),
            (workflow_topic_resources, workflow_topic_resources()), (workflow_plan_resources, workflow_plan_resources()),
            (standard_rulesets, standard_rulesets()), (project_quality_ruleset, (project_quality_ruleset(),))):
        origin = ResourceOrigin("vibeflow.core", str(inspect.getsourcefile(factory)),
            inspect.getsourcelines(factory)[1], symbol=factory.__qualname__)
        for descriptor in resources:
            origins[(resource_kind(descriptor), descriptor.id)] = origin
    return origins
