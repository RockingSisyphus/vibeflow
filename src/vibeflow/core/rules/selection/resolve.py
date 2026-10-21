"""The single precedence rule for static, inherited and explicit choices."""
from vibeflow.core.rules.selection.dynamic import explicit_selection
from vibeflow.core.rules.selection.models import RuleSelection
from vibeflow.core.rules.selection.static import node_defaults, workflow_defaults


def resolve_graph_selection(graph, *, rulesets, path=(), parent=None):
    defaults = parent.references if parent is not None else workflow_defaults(rulesets)
    explicit = explicit_selection(graph)
    if explicit is not None:
        return RuleSelection(explicit, "dynamic", "/".join(path) or "pipeline", defaults)
    if parent is not None:
        return RuleSelection(defaults, "inherited", parent.origin)
    return RuleSelection(defaults, "static", "workflow_defaults")


def resolve_node_selection(descriptor, call=None):
    defaults = node_defaults(descriptor)
    explicit = explicit_selection(call) if call is not None else None
    return (RuleSelection(explicit, "dynamic", call.id, defaults) if explicit is not None
            else RuleSelection(defaults, "static", getattr(descriptor, "ruleset_origin", descriptor.id)))
