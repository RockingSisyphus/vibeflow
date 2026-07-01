from __future__ import annotations


RULE_CATALOG: dict[str, dict[str, str]] = {
    "GRAPH.CYCLE.MISSING_DECISION_EXIT": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.EDGE.CONFLICTING_DUPLICATE": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.EDGE.DUPLICATE": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.SMELL.CONFUSING_NODE_NAME": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.DATA.UNCONSUMED_PROVIDER": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "NODESET.SMELL.TOO_WIDE": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_nodeset",
    },
}


def rule_catalog() -> dict[str, dict[str, str]]:
    return {rule_id: dict(payload) for rule_id, payload in sorted(RULE_CATALOG.items())}
