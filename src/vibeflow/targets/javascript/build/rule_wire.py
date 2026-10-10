"""Pure finite encoding at the Rule worker boundary; never runs analysis."""
from dataclasses import replace
from typing import Any, Mapping
from vibeflow.core.rules.models import plain
from vibeflow.targets.javascript.build.graph_wire import graph_wire


def rule_wire_facts(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Encode the native shared Nodeset registry as finite declarations and refs."""
    def encode(key, value):
        if key in {"graph", "global_graph", "declaration_graph"} and value is not None:
            return graph_wire(value, plain)
        if key == "definition" and value is not None:
            finite = replace(value, graph=replace(value.graph, nodesets={}))
            return {**plain(finite), "graph": graph_wire(value.graph, plain)}
        return plain(value)
    portable = {key: plain(value) for key, value in facts.items()
                if key not in {"graph", "global_graph", "declaration_graph", "definition", "graphs", "catalogs", "prefetched_quality", "analysis_cache"}}
    for key in ("graph", "global_graph", "declaration_graph", "definition"):
        if facts.get(key) is not None:
            portable[key] = encode(key, facts[key])
    if "graphs" in facts:
        portable["graphs"] = [{key: encode(key, value)
            for key, value in item.items()} for item in facts["graphs"]]
    return portable
