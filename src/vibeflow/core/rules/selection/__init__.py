"""Shared rule selection API, independent of language analysis."""
from vibeflow.core.rules.selection.models import RuleReference, RuleSelection, selection_data, selection_refs
from vibeflow.core.rules.selection.resolve import resolve_graph_selection, resolve_node_selection

__all__ = ["RuleReference", "RuleSelection", "selection_data", "selection_refs", "resolve_graph_selection", "resolve_node_selection"]
