"""Native Python bindings contributed by the standard plugin."""

def python_rule_bindings():
    from functools import wraps
    from vibeflow.targets.python.quality.rules.effects import no_side_effects
    from vibeflow.targets.python.quality.rules.import_side_effects import import_side_effects
    from vibeflow.targets.python.quality.rules.maintainability import maintainability, source_implementation_handlers
    from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
    from vibeflow.targets.python.quality.rules.node_interface import node_interface
    from vibeflow.targets.python.quality.rules.workflow import workflow
    from vibeflow.builtin import project_quality_handlers, workflow_topic_handlers
    from vibeflow.targets.python.quality.rules.definition_review import DefinitionReviewCache
    definition_cache = DefinitionReviewCache()
    analysis = PythonSourceAnalysis()
    from vibeflow.targets.python.quality.policy_parameters import source_policy_consumer
    source_implementations = {key:source_policy_consumer(value) for key,value in source_implementation_handlers(analysis).items()}
    return {
        **source_implementations, **project_quality_handlers(), **workflow_topic_handlers(),
        "vibeflow.workflow": wraps(workflow, assigned=(), updated=())(lambda context, inputs, params: workflow(context, inputs, params, definition_cache=definition_cache)),
        "vibeflow.no_side_effects": source_policy_consumer(no_side_effects, sections=("imports",), effect_defaults=True),
        "vibeflow.import_side_effects": source_policy_consumer(import_side_effects, sections=("imports",)),
        "vibeflow.node_interface": node_interface,
        "vibeflow.maintainability": source_policy_consumer(lambda context, inputs, params: maintainability(context, inputs, params, analysis=analysis)),
    }


def builtin_plugin():
    from vibeflow.builtin import builtin_rule_resources, builtin_declaration_origins
    from vibeflow.builtin.plugin import make_builtin_plugin
    rules, rulesets = builtin_rule_resources()
    return make_builtin_plugin(rules, rulesets, python_rule_bindings(), declaration_origins=builtin_declaration_origins())
