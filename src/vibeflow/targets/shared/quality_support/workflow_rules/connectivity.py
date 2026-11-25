"""Require a single weakly connected component of scheduling nodes."""

from collections import defaultdict

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleResult
from vibeflow.targets.shared.quality_support.workflow_rules.flow import node_participates_in_flow


def check_connectivity(context, inputs, params):
    graph = context.require("graph")
    compiled = context.require("compiled")
    neighbors = {node.id: [] for node in graph.nodes if node_participates_in_flow(graph, node)}
    for edge in compiled.resolved_schedule_edges:
        if edge.source in neighbors and edge.target in neighbors:
            neighbors[edge.source].append(edge.target)
            neighbors[edge.target].append(edge.source)

    components = []
    unseen = set(neighbors)
    for start in neighbors:
        if start not in unseen:
            continue
        unseen.remove(start)
        pending = [start]
        component = []
        while pending:
            node = pending.pop()
            component.append(node)
            for neighbor in neighbors[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        components.append(component)

    if len(components) <= 1:
        return RuleResult()

    entries_by_start = defaultdict(list)
    for name, entry in graph.entries.items():
        entries_by_start[entry.start].append(name)
    owner = context.facts.get("owner", "pipeline")
    return RuleResult(findings=(HealthFinding(
        rule_id="GRAPH.FLOW.DISCONNECTED",
        severity="error",
        object_type="workflow" if owner == "pipeline" else "nodeset",
        object_id=owner,
        failure_layer="topology",
        message=f"scheduling graph has {len(components)} disconnected components",
        suggested_fix_type="fix_config",
        details={"components": [
            {"nodes": sorted(component), "entries": sorted(
                name for node in component for name in entries_by_start.get(node, ()))}
            for component in components
        ]},
    ),))
