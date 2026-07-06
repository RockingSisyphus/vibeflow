from __future__ import annotations

from .compiler import GraphCompiler, GraphCompileError
from .health_types import HealthFinding
from .mainline import analyze_mainline


def append_mainline_health(graph, compiled, state, *, registry, owner: str = "pipeline", visited_nodesets: set[str] | None = None) -> None:
    if visited_nodesets is None:
        visited_nodesets = set()
    analysis = analyze_mainline(graph, compiled.effective_edges, compiled.flow_kinds, owner=owner)
    state.mainline[owner] = analysis.to_dict()
    for finding in analysis.findings:
        state.warnings.append(
            HealthFinding(
                rule_id=finding.rule_id,
                severity="warning",
                object_type="edge",
                object_id=f"{finding.source}->{finding.target}",
                failure_layer="topology",
                message=finding.message,
                suggested_fix_type="fix_config",
                details=dict(finding.details),
            )
        )
    for nodeset in graph.nodesets.values():
        if nodeset.status == "planned" or nodeset.name in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.name)
        try:
            nested = GraphCompiler().compile(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.name}")
        except GraphCompileError:
            continue
        append_mainline_health(nodeset.graph, nested, state, registry=registry, owner=f"nodeset:{nodeset.name}", visited_nodesets=visited_nodesets)
