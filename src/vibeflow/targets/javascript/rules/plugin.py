"""Assemble the JavaScript standard Rule Plugin."""
from vibeflow.targets.shared.rule_support.capability_policy import handlers as capability_handlers
from vibeflow.targets.javascript.rules.node.handlers import javascript_source_bindings


def javascript_rule_bindings():
    from vibeflow.targets.javascript.rules.graph import workflow_topic_handlers, workflow_plan_handlers
    from vibeflow.targets.javascript.rules.source_quality import javascript_project_bindings
    return {**capability_handlers(), **javascript_source_bindings(), **workflow_topic_handlers(), **workflow_plan_handlers(),
        **javascript_project_bindings()}


def builtin_plugin():
    from vibeflow.targets.javascript.rules import builtin_rule_resources, builtin_declaration_origins
    from vibeflow.targets.shared.rule_support.plugin import make_builtin_plugin
    rules, rulesets = builtin_rule_resources()
    return make_builtin_plugin(rules, rulesets, javascript_rule_bindings(), declaration_origins=builtin_declaration_origins())
