from __future__ import annotations


RULE_CATALOG: dict[str, dict[str, str]] = {
    "GRAPH.CYCLE.FORBIDDEN": {
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
    "GRAPH.SMELL.MISSING_NODE_DESCRIPTION": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.DATA.UNCONSUMED_PROVIDER": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.DATA.RUNTIME_REQUIREMENT_UNREACHABLE": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.DATA.NO_PAYLOAD_BYPASS": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.JOIN.ALL_DEPENDS_ON_TRANSFER_ONLY": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.JOIN.ALL_BRANCHES_MUTUALLY_EXCLUSIVE": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "GRAPH.JOIN.REDUNDANT_ALL": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_config",
    },
    "NODESET.SMELL.TOO_WIDE": {
        "severity": "warning",
        "layer": "topology",
        "suggested_fix_type": "fix_nodeset",
    },
    "NODESET.NESTING.DEPTH_EXCEEDED": {
        "severity": "error",
        "layer": "topology",
        "suggested_fix_type": "fix_nodeset",
    },
}


def rule_catalog() -> dict[str, dict[str, str]]:
    return {rule_id: dict(payload) for rule_id, payload in sorted(RULE_CATALOG.items())}
