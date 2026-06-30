from __future__ import annotations

from .graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from .health_types import HealthFinding


def append_planned_findings(graph, state) -> None:
    _append_planned_findings_for_graph(graph, state, owner="pipeline")
    for nodeset in graph.nodesets.values():
        if nodeset.status == STATUS_PLANNED:
            state.warnings.append(_planned_nodeset_finding(nodeset.name))
        _append_planned_findings_for_graph(nodeset.graph, state, owner=f"nodeset:{nodeset.name}")
        if nodeset.status == STATUS_IMPLEMENTED and graph_has_planned(nodeset.graph):
            state.errors.append(_planned_child_finding(nodeset.name))


def graph_has_planned(graph) -> bool:
    return any(node.status == STATUS_PLANNED for node in graph.nodes) or any(nodeset.status == STATUS_PLANNED or graph_has_planned(nodeset.graph) for nodeset in graph.nodesets.values())


def _append_planned_findings_for_graph(graph, state, *, owner: str) -> None:
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            state.warnings.append(_planned_node_finding(node, owner=owner))


def _planned_nodeset_finding(name: str) -> HealthFinding:
    return HealthFinding(rule_id="GRAPH.PLANNED.NODESET", severity="warning", object_type="nodeset", object_id=name, failure_layer="topology", message=f"nodeset '{name}' is planned and cannot run yet", suggested_fix_type="implement_nodeset")


def _planned_child_finding(name: str) -> HealthFinding:
    return HealthFinding(rule_id="GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD", severity="error", object_type="nodeset", object_id=name, failure_layer="topology", message=f"implemented nodeset '{name}' contains planned child nodes", suggested_fix_type="implement_nodeset")


def _planned_node_finding(node, *, owner: str) -> HealthFinding:
    return HealthFinding(rule_id="GRAPH.PLANNED.NODE", severity="warning", object_type="node", object_id=node.name, failure_layer="topology", message=f"node '{node.name}' is planned and cannot run yet", suggested_fix_type="implement_node", details={"owner": owner, "flow_kind": node.flow_kind})
