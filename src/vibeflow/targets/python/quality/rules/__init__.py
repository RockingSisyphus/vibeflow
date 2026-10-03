"""Python implementations of portable, explicitly selected rule resources."""

from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.rules.import_side_effects import import_side_effects
from vibeflow.targets.python.quality.rules.maintainability import maintainability, source_implementation_handlers
from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
from vibeflow.targets.python.quality.rules.node_interface import node_interface
from vibeflow.targets.python.quality.rules.workflow import workflow


def python_rule_handlers():
    from vibeflow.core.rules.builtin import implementation_handlers, project_quality_handlers, workflow_topic_handlers
    from vibeflow.targets.python.quality.rules.definition_review import DefinitionReviewCache
    definition_cache = DefinitionReviewCache()
    analysis = PythonSourceAnalysis()
    return {
        **source_implementation_handlers(analysis), **project_quality_handlers(), **workflow_topic_handlers(),
        "vibeflow.workflow": lambda context, inputs, params: workflow(context, inputs, params, definition_cache=definition_cache),
        "vibeflow.no_side_effects": no_side_effects,
        "vibeflow.import_side_effects": import_side_effects,
        "vibeflow.node_interface": node_interface,
        "vibeflow.maintainability": lambda context, inputs, params: maintainability(context, inputs, params, analysis=analysis),
    }


__all__ = ["python_rule_handlers"]
