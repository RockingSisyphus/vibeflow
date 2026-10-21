"""Public Rule evaluation boundary for the JavaScript Target.

Process and source access live in the build service; callers consume portable
Rule results and descriptor-owned facts through this facade.
"""

from vibeflow.targets.javascript.build.rule_session import (
    JavascriptRuleReport,
    node_definition_calls,
    source_node_calls,
    run_javascript_rules,
    run_javascript_workflow_rules,
)

__all__ = ["JavascriptRuleReport", "node_definition_calls", "source_node_calls", "run_javascript_rules", "run_javascript_workflow_rules"]
