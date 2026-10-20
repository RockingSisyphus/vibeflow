"""Native Python bindings contributed by the standard plugin."""
from vibeflow.targets.python.rules.capabilities import handlers as capability_handlers

def python_rule_bindings():
    from vibeflow.targets.python.rules.node.effects import no_side_effects
    from vibeflow.targets.python.rules.node.import_side_effects import import_side_effects
    from vibeflow.targets.python.rules.node.maintainability import maintainability, source_implementation_handlers
    from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
    from vibeflow.targets.python.rules.node.node_interface import node_interface
    from vibeflow.targets.python.rules.node.async_lifecycle import async_lifecycle
    from vibeflow.targets.python.rules.node.node_architecture import node_architecture
    from vibeflow.targets.python.rules.node.input_writes import input_writes
    from vibeflow.targets.python.rules.graph.review import workflow_review
    from vibeflow.targets.python.rules import project_quality_handlers, workflow_topic_handlers
    from vibeflow.targets.python.rules.graph.workflow import workflow_plan_handlers
    analysis = PythonSourceAnalysis()
    from vibeflow.targets.python.quality.policy_parameters import source_policy_consumer
    source_implementations = {key:source_policy_consumer(value) for key,value in source_implementation_handlers(analysis).items()}
    return {
        **capability_handlers(), **source_implementations, **project_quality_handlers(), **workflow_topic_handlers(), **workflow_plan_handlers(),
        "vibeflow.workflow.review": workflow_review,
        "vibeflow.no_side_effects": source_policy_consumer(no_side_effects, sections=("imports",), effect_defaults=True),
        "vibeflow.import_side_effects": source_policy_consumer(import_side_effects, sections=("imports",)),
        "vibeflow.node_interface": node_interface,
        "vibeflow.async_lifecycle": async_lifecycle,
        "vibeflow.node_architecture": node_architecture,
        "vibeflow.input_writes": input_writes,
        "vibeflow.maintainability": source_policy_consumer(lambda context, inputs, params: maintainability(context, inputs, params, analysis=analysis)),
    }


def builtin_plugin():
    from vibeflow.targets.python.rules import builtin_rule_resources, builtin_declaration_origins
    from vibeflow.targets.shared.rule_support.plugin import make_builtin_plugin
    rules, rulesets = builtin_rule_resources()
    return make_builtin_plugin(rules, rulesets, python_rule_bindings(), declaration_origins=builtin_declaration_origins())


def project_plugin():
    """Contribute the portable project checks without loading source analyzers."""
    from vibeflow.targets.python.rules.project import project_quality_handlers, project_quality_resources
    from vibeflow.targets.shared.rule_support.plugin import make_builtin_plugin
    from vibeflow.targets.python.rules import builtin_declaration_origins
    rules, ruleset = project_quality_resources()
    return make_builtin_plugin(rules, (ruleset,), project_quality_handlers(),
        declaration_origins=builtin_declaration_origins())
