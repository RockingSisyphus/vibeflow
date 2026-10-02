"""Public Rule evaluation boundary for the JavaScript Target.

Process and source access live in the build service; callers consume portable
Rule results and descriptor-owned facts through this facade.
"""

from vibeflow.targets.javascript.build.rule_session import (
    JavascriptRuleReport,
    builtin_javascript_handlers,
    node_type_calls,
    run_javascript_rules,
    run_javascript_workflow_rules,
)

__all__ = ["JavascriptRuleReport", "builtin_javascript_handlers", "node_type_calls", "run_javascript_rules", "run_javascript_workflow_rules"]
