from __future__ import annotations

from .graph_config import STATUS_IMPLEMENTED, STATUS_PLANNED
from .health_types import HealthFinding
from .planned_behavior import PLANNED_BEHAVIOR_BLOCKING, PLANNED_BEHAVIOR_PYTHON_STUB, effective_planned_behavior, planned_behavior_label, validate_python_stub_file
from .runtime_helpers import referenced_nodeset_names


def append_planned_findings(graph, state) -> None:
    visited_nodesets: set[str] = set()
    _append_planned_findings_for_graph(graph, state, owner="pipeline")
    for nodeset in graph.nodesets.values():
        if nodeset.name in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.name)
        if nodeset.status == STATUS_PLANNED:
            state.warnings.append(_planned_nodeset_finding(nodeset))
            _append_python_stub_findings(nodeset.planned_behavior, state, object_type="nodeset", object_id=nodeset.name, project_root=graph.project_root)
        _append_planned_findings_for_graph(nodeset.graph, state, owner=f"nodeset:{nodeset.name}")
        if nodeset.status == STATUS_IMPLEMENTED:
            if graph_has_blocking_planned(nodeset.graph):
                state.errors.append(_planned_child_finding(nodeset.name, severity="error"))
            elif graph_has_planned(nodeset.graph):
                state.warnings.append(_planned_child_finding(nodeset.name, severity="warning"))


def graph_has_planned(graph, *, visited_nodesets: set[str] | None = None) -> bool:
    if visited_nodesets is None:
        visited_nodesets = set()
    if any(node.status == STATUS_PLANNED for node in graph.nodes):
        return True
    for nodeset_name in referenced_nodeset_names(graph):
        nodeset = graph.nodesets.get(nodeset_name)
        if nodeset is None or nodeset.name in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.name)
        if nodeset.status == STATUS_PLANNED or graph_has_planned(nodeset.graph, visited_nodesets=visited_nodesets):
            return True
    return False


def graph_has_blocking_planned(graph, *, visited_nodesets: set[str] | None = None) -> bool:
    if visited_nodesets is None:
        visited_nodesets = set()
    for node in graph.nodes:
        nodeset = graph.nodesets.get(node.node_type.removeprefix("nodeset.")) if node.node_type.startswith("nodeset.") else None
        if node.status == STATUS_PLANNED and effective_planned_behavior(node, nodeset).kind == PLANNED_BEHAVIOR_BLOCKING:
            return True
    for nodeset_name in referenced_nodeset_names(graph):
        nodeset = graph.nodesets.get(nodeset_name)
        if nodeset is None or nodeset.name in visited_nodesets:
            continue
        visited_nodesets.add(nodeset.name)
        if nodeset.status == STATUS_PLANNED:
            if nodeset.planned_behavior.kind == PLANNED_BEHAVIOR_BLOCKING:
                return True
            continue
        if graph_has_blocking_planned(nodeset.graph, visited_nodesets=visited_nodesets):
            return True
    return False


def _append_planned_findings_for_graph(graph, state, *, owner: str) -> None:
    for node in graph.nodes:
        if node.status == STATUS_PLANNED:
            nodeset = graph.nodesets.get(node.node_type.removeprefix("nodeset.")) if node.node_type.startswith("nodeset.") else None
            behavior = effective_planned_behavior(node, nodeset)
            state.warnings.append(_planned_node_finding(node, behavior=behavior, owner=owner))
            _append_python_stub_findings(behavior, state, object_type="node", object_id=node.name, project_root=graph.project_root)


def _planned_nodeset_finding(nodeset) -> HealthFinding:
    behavior = nodeset.planned_behavior
    return HealthFinding(
        rule_id="GRAPH.PLANNED.NODESET",
        severity="warning",
        object_type="nodeset",
        object_id=nodeset.name,
        failure_layer="topology",
        message=f"nodeset '{nodeset.name}' is {planned_behavior_label(behavior)} and cannot run as production",
        suggested_fix_type="implement_nodeset",
        details=_behavior_details(behavior),
    )


def _planned_child_finding(name: str, *, severity: str) -> HealthFinding:
    return HealthFinding(
        rule_id="GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD",
        severity=severity,
        object_type="nodeset",
        object_id=name,
        failure_layer="topology",
        message=f"implemented nodeset '{name}' contains planned child nodes",
        suggested_fix_type="implement_nodeset",
    )


def _planned_node_finding(node, *, behavior, owner: str) -> HealthFinding:
    return HealthFinding(
        rule_id="GRAPH.PLANNED.NODE",
        severity="warning",
        object_type="node",
        object_id=node.name,
        failure_layer="topology",
        message=f"node '{node.name}' is {planned_behavior_label(behavior)} and cannot run as production",
        suggested_fix_type="implement_node",
        details={"owner": owner, "flow_kind": node.flow_kind, **_behavior_details(behavior)},
    )


def _append_python_stub_findings(behavior, state, *, object_type: str, object_id: str, project_root: str) -> None:
    if behavior.kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        return
    state.warnings.append(
        HealthFinding(
            rule_id="GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY",
            severity="warning",
            object_type=object_type,
            object_id=object_id,
            failure_layer="topology",
            message=f"{object_type} '{object_id}' uses planned python_stub for development tests only",
            suggested_fix_type="replace_stub_with_implementation",
            details=_behavior_details(behavior),
        )
    )
    for finding in validate_python_stub_file(behavior, project_root=project_root, object_type=object_type, object_id=object_id):
        state.errors.append(finding)


def _behavior_details(behavior) -> dict[str, object]:
    details = {"planned_behavior": behavior.kind}
    if behavior.stub_module:
        details["stub_module"] = behavior.stub_module
    return details
