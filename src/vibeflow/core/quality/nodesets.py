"""Target-neutral maintainability findings for composed nodesets."""

from __future__ import annotations

from vibeflow.core.findings import HealthFinding
from vibeflow.core.flow import GraphConfig
from vibeflow.core.nodeset_dependencies import (
    NODESET_WIDTH_WARNING,
    analyze_nodeset_dependencies,
    nodeset_dependency_cycles,
    nodeset_depth_violations,
)


def nodeset_quality_findings(
    graph: GraphConfig, *, max_depth: int = 4
) -> tuple[HealthFinding, ...]:
    """Measure width, recursion and nesting without choosing a command gate."""

    findings: list[HealthFinding] = []
    for nodeset in sorted(graph.nodesets.values(), key=lambda item: item.type_key):
        count = len(nodeset.graph.nodes)
        if count > NODESET_WIDTH_WARNING:
            findings.append(
                HealthFinding(
                    rule_id="NODESET.SMELL.TOO_WIDE",
                    severity="warning",
                    object_type="nodeset",
                    object_id=nodeset.type_key,
                    failure_layer="topology",
                    message=f"nodeset has {count} internal nodes; consider splitting it",
                    suggested_fix_type="fix_nodeset",
                    details={"node_count": count, "limit": NODESET_WIDTH_WARNING},
                )
            )
    dependencies = analyze_nodeset_dependencies(graph)
    for cycle in nodeset_dependency_cycles(dependencies):
        findings.append(
            HealthFinding(
                rule_id="NODESET.RECURSION",
                severity="error",
                object_type="nodeset",
                object_id=cycle[0],
                failure_layer="topology",
                message="nodeset recursion is forbidden: " + " -> ".join(cycle),
                suggested_fix_type="fix_nodeset",
                details={"cycle": cycle},
            )
        )
    for violation in nodeset_depth_violations(graph, max_depth=max_depth):
        findings.append(
            HealthFinding(
                rule_id="NODESET.NESTING.DEPTH_EXCEEDED",
                severity="error",
                object_type="nodeset",
                object_id=violation.chain[0],
                failure_layer="topology",
                message=(
                    f"nodeset nesting depth {violation.actual_depth} exceeds configured "
                    f"maximum {max_depth}: {' -> '.join(violation.chain)}"
                ),
                suggested_fix_type="fix_nodeset",
                details=violation.to_details(),
            )
        )
    return tuple(findings)


__all__ = ["nodeset_quality_findings"]
