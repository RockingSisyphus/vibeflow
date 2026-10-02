"""Private, per-check reuse of whole-definition review results."""
from dataclasses import fields
import json

from vibeflow.core.rules.models import plain


def _graph_snapshot(graph):
    return {item.name: plain(getattr(graph, item.name)) for item in fields(graph) if item.name != "nodesets"}


def _signature(value):
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"))


class DefinitionReviewCache:
    """Handlers retain this cache; it is never exposed as a mutable fact."""

    def __init__(self):
        self._results = {}

    def identity(self, graph, context, inputs, params):
        registry = context.facts.get("registry")
        source = context.facts.get("source_context")
        actual_rule = context.facts.get("rule_invocations", {}).get(context.subject.get("rule_call_id"))
        declarations = [{"descriptor": registry.descriptor(key).to_dict(), "config": registry.get_config_spec(key),
            "source":registry.source_info(key)}
            for key in registry.available()] if registry is not None else []
        definitions = [{**{item.name: getattr(value, item.name) for item in fields(value) if item.name != "graph"},
            "graph": _graph_snapshot(value.graph)} for _, value in sorted(graph.nodesets.items())]
        key = _signature({"rule": actual_rule, "phase": context.phase, "definitions": definitions,
            "inputs": inputs, "params": params, "global_config": context.facts.get("global_config"),
            "declarations": declarations, "source": [(item.path, item.text) for item in source.files] if source is not None else []})
        return key, _signature(_graph_snapshot(graph))

    def get(self, identity):
        key, graph = identity
        item = self._results.get(key)
        return item[1] if item is not None and graph in item[0] else None

    def store(self, identity, graph, result):
        key, current = identity
        covered = {current, *(_signature(_graph_snapshot(value.graph)) for value in graph.nodesets.values())}
        self._results[key] = (covered, result)
