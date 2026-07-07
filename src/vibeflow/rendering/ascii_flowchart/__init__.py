from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from vibeflow.rendering.ascii_flowchart.canvas import Canvas
from vibeflow.rendering.ascii_flowchart.layout import build_layout, draw_edges
from vibeflow.rendering.ascii_flowchart.model import AsciiEdge, AsciiNode
from vibeflow.rendering.ascii_flowchart.shapes import draw_node
from vibeflow.compiler import CompiledGraph
from vibeflow.rendering.helpers import compile_for_render, node_flow_kind, node_is_external, nodeset_for_node, shorten
from vibeflow.graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from vibeflow.node import (
    FLOW_KIND_DATA_STORE,
    FLOW_KIND_DECISION,
    FLOW_KIND_DOCUMENT,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    FLOW_KIND_PREPARATION,
    FLOW_KIND_PROCESS,
    FLOW_KIND_TERMINAL,
)
from vibeflow.graph_config.planned_behavior import effective_planned_behavior, planned_behavior_label

if TYPE_CHECKING:
    from vibeflow.registry import NodeRegistry


# Layout and edge-routing are a compact Python adaptation of the Sugiyama-style
# flowchart renderer used by mermaid2term (MIT package metadata). The parser is
# intentionally not copied: this renderer consumes kernel GraphConfig directly.


def export_ascii_flowchart(
    graph: GraphConfig,
    *,
    expand_nodesets: bool = False,
    compiled: CompiledGraph | None = None,
    registry: NodeRegistry | None = None,
    health_report: object | None = None,
    show_contract: bool = True,
    show_semantics: bool = True,
    show_findings: bool = True,
) -> str:
    return _Renderer(
        expand_nodesets=expand_nodesets,
        registry=registry,
        health_report=health_report,
        show_contract=show_contract,
        show_semantics=show_semantics,
        show_findings=show_findings,
    ).render(graph, compile_for_render(graph, compiled, registry))


class _Renderer:
    def __init__(
        self,
        *,
        expand_nodesets: bool,
        registry: NodeRegistry | None,
        health_report: object | None,
        show_contract: bool,
        show_semantics: bool,
        show_findings: bool,
    ) -> None:
        self.expand_nodesets = expand_nodesets
        self.registry = registry
        self.health_report = health_report
        self.show_contract = show_contract
        self.show_semantics = show_semantics
        self.show_findings = show_findings

    def render(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        lines = ["TOPOLOGY FLOWCHART", ""]
        self._render_section(lines, graph, compiled, title="pipeline", indent="")
        if self.show_findings:
            self._render_findings(lines)
        return "\n".join(lines).rstrip() + "\n"

    def _render_section(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, title: str, indent: str) -> None:
        lines.append(f"{indent}{title}")
        lines.append(f"{indent}{'-' * len(title)}")
        layout = build_layout(self._ascii_nodes(graph, compiled), self._ascii_edges(compiled))
        if layout.nodes:
            canvas = Canvas(layout.width, layout.height)
            for node in layout.nodes.values():
                draw_node(canvas, node)
            draw_edges(canvas, layout)
            lines.extend(f"{indent}{line}" for line in canvas.to_string().splitlines())
        else:
            lines.append(f"{indent}(empty)")
        lines.append("")
        self._render_edges(lines, compiled, indent=indent)
        if self.show_contract or self.show_semantics:
            self._render_contracts(lines, graph, compiled, indent=indent)
        if self.expand_nodesets:
            self._render_nodesets(lines, graph, indent=indent)

    def _ascii_nodes(self, graph: GraphConfig, compiled: CompiledGraph) -> dict[str, AsciiNode]:
        findings_by_node = _findings_by_node(self.health_report)
        nodes: dict[str, AsciiNode] = {}
        for index, spec in enumerate(graph.nodes):
            nodeset = nodeset_for_node(graph, spec)
            flow_kind = node_flow_kind(spec, compiled) or (nodeset.flow_kind if nodeset else FLOW_KIND_PROCESS)
            label = self._nodeset_label(spec, nodeset, flow_kind) if nodeset else self._node_label(spec, flow_kind)
            markers = findings_by_node.get(spec.id, ())
            if markers:
                label = (*label, *markers)
            nodes[spec.id] = AsciiNode(spec.id, flow_kind, tuple(shorten(line, limit=46) for line in label if line), index)
        return nodes

    def _ascii_edges(self, compiled: CompiledGraph) -> list[AsciiEdge]:
        return [AsciiEdge(edge.source, edge.target, edge.when, index) for index, edge in enumerate(compiled.effective_edges)]

    def _render_nodesets(self, lines: list[str], graph: GraphConfig, *, indent: str) -> None:
        for node in graph.nodes:
            nodeset = nodeset_for_node(graph, node)
            if nodeset is None:
                continue
            nested_compiled = compile_for_render(nodeset.graph, None, self.registry)
            title = node.metadata.display_name or nodeset.display_name or node.id
            self._render_section(lines, nodeset.graph, nested_compiled, title=f"nodeset {title} (id={node.id}, type_key={nodeset.type_key})", indent=f"{indent}  ")

    def _render_edges(self, lines: list[str], compiled: CompiledGraph, *, indent: str) -> None:
        if not compiled.effective_edges:
            lines.append(f"{indent}Flow edges: (none)")
            lines.append("")
            return
        lines.append(f"{indent}Flow edges:")
        order = {name: index for index, name in enumerate(compiled.order)}
        for edge in compiled.effective_edges:
            label = f" --[{edge.when}]--> " if edge.when else " ----> "
            marker = "  (back edge)" if order.get(edge.target, -1) <= order.get(edge.source, -1) else ""
            lines.append(f"{indent}  {edge.source}{label}{edge.target}{marker}")
        lines.append("")

    def _render_contracts(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, indent: str) -> None:
        lines.append(f"{indent}Node contracts:")
        for node in graph.nodes:
            lines.append(f"{indent}  {node.id}: " + "; ".join(self._contract_details(graph, node, compiled)))
        lines.append("")

    def _contract_details(self, graph: GraphConfig, node: NodeSpec, compiled: CompiledGraph) -> list[str]:
        nodeset = nodeset_for_node(graph, node)
        flow_kind = node_flow_kind(node, compiled) or (nodeset.flow_kind if nodeset else FLOW_KIND_PROCESS)
        details = [f"kind={flow_kind}", f"type_used={node.type_used}"]
        if node.status == STATUS_PLANNED:
            behavior = effective_planned_behavior(node, nodeset)
            details.append(f"status={planned_behavior_label(behavior).replace(' ', '_')}")
            if behavior.stub_module:
                details.append(f"stub={behavior.stub_module}")
        if self._node_is_external(node):
            details.append("external=true")
        if nodeset is None:
            details.extend((f"requires={_contract_text(node.requires)}", f"provides={_contract_text(node.provides)}"))
        else:
            details.extend((f"type_key={nodeset.type_key}", f"requires={_contract_text(nodeset.requires or node.requires)}", f"provides={_contract_text(nodeset.provides or node.provides)}"))
        return details

    def _render_findings(self, lines: list[str]) -> None:
        findings = _health_findings(self.health_report)
        if not findings:
            return
        lines.append("Findings:")
        for finding in findings:
            severity = str(finding.get("severity", "error")).upper()
            rule_id = str(finding.get("rule_id", ""))
            object_type = str(finding.get("object_type", ""))
            object_id = str(finding.get("object_id", ""))
            message = shorten(finding.get("message", ""), limit=160)
            lines.append(f"  [{severity}] {rule_id} {object_type}:{object_id} - {message}")

    def _node_label(self, node: NodeSpec, flow_kind: str) -> tuple[str, ...]:
        lines = [_badge(flow_kind, node), node.id]
        if node.status == STATUS_PLANNED:
            lines.append(planned_behavior_label(node.planned_behavior).upper())
            if node.planned_behavior.stub_module:
                lines.append(f"stub: {node.planned_behavior.stub_module}")
        if self._node_is_external(node):
            lines.append("external")
        return tuple(line for line in lines if line)

    def _nodeset_label(self, node: NodeSpec, nodeset: NodesetSpec | None, flow_kind: str) -> tuple[str, ...]:
        if nodeset is None:
            return self._node_label(node, flow_kind)
        lines = [_badge(flow_kind, node), node.id]
        if node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED:
            behavior = effective_planned_behavior(node, nodeset)
            lines.append(planned_behavior_label(behavior).upper())
            if behavior.stub_module:
                lines.append(f"stub: {behavior.stub_module}")
        return tuple(line for line in lines if line)

    def _node_is_external(self, node: NodeSpec) -> bool:
        return node_is_external(node, self.registry)


def _badge(flow_kind: str, node: NodeSpec) -> str:
    if flow_kind == FLOW_KIND_TERMINAL:
        node_id = node.id.lower()
        return "● END" if node_id.endswith("end") or node_id == "end" else "● START"
    badges = {
        FLOW_KIND_DECISION: "DECISION",
        FLOW_KIND_IO: "⇄ I/O",
        FLOW_KIND_PREDEFINED: "CALL",
        FLOW_KIND_DATA_STORE: "▣ STORE",
        FLOW_KIND_DOCUMENT: "DOC",
        FLOW_KIND_PREPARATION: "INIT",
    }
    return badges.get(flow_kind, "PROCESS")


def _findings_by_node(report: object | None) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for finding in _health_findings(report):
        if finding.get("object_type") != "node":
            continue
        node = str(finding.get("object_id", ""))
        if not node:
            continue
        severity = str(finding.get("severity", "error")).upper()
        rule_id = str(finding.get("rule_id", ""))
        result.setdefault(node, []).append(f"{severity}: {rule_id}")
    return {node: tuple(values) for node, values in result.items()}


def _health_findings(report: object | None) -> tuple[Mapping[str, Any], ...]:
    if report is None:
        return ()
    payload: object = report.to_dict() if hasattr(report, "to_dict") and callable(getattr(report, "to_dict")) else report
    if not isinstance(payload, Mapping):
        return ()
    findings: list[Mapping[str, Any]] = []
    for key in ("errors", "warnings", "skipped"):
        items = payload.get(key, ())
        if isinstance(items, list):
            findings.extend(item for item in items if isinstance(item, Mapping))
    return tuple(findings)


def _contract_text(values: tuple[object, ...]) -> str:
    if not values:
        return "-"
    return ",".join(_contract_item_text(item) for item in values)


def _contract_item_text(item: object) -> str:
    key = getattr(item, "key", "")
    data_type = getattr(item, "type", "")
    cardinality = getattr(item, "cardinality", "")
    if key and data_type:
        return f"{key}->{data_type}"
    if data_type and cardinality:
        return f"{data_type}({cardinality})"
    return str(item)
