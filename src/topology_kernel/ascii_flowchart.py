from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from .compiler import CompiledGraph, GraphCompiler
from .graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from .node import (
    FLOW_KIND_DATA_STORE,
    FLOW_KIND_DECISION,
    FLOW_KIND_DOCUMENT,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    FLOW_KIND_PREPARATION,
    FLOW_KIND_PROCESS,
    FLOW_KIND_TERMINAL,
)

if TYPE_CHECKING:
    from .registry import NodeRegistry


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
    actual_compiled = compiled or GraphCompiler().compile(graph, registry=registry)
    renderer = _Renderer(
        expand_nodesets=expand_nodesets,
        registry=registry,
        health_report=health_report,
        show_contract=show_contract,
        show_semantics=show_semantics,
        show_findings=show_findings,
    )
    return renderer.render(graph, actual_compiled)


@dataclass
class _Node:
    name: str
    flow_kind: str
    label: tuple[str, ...]
    index: int
    layer: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class _Edge:
    source: str
    target: str
    label: str = ""
    index: int = 0


@dataclass
class _Layout:
    nodes: dict[str, _Node]
    edges: list[_Edge]
    back_edges: set[_Edge]
    width: int
    height: int


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
        layout = self._layout(graph, compiled)
        if layout.nodes:
            canvas = _Canvas(layout.width, layout.height)
            for node in layout.nodes.values():
                _draw_node(canvas, node)
            _draw_edges(canvas, layout)
            lines.extend(f"{indent}{line}" for line in canvas.to_string().splitlines())
        else:
            lines.append(f"{indent}(empty)")
        lines.append("")
        self._render_edges(lines, compiled, indent=indent)
        if self.show_contract or self.show_semantics:
            self._render_contracts(lines, graph, compiled, indent=indent)
        if self.expand_nodesets:
            for node in graph.nodes:
                nodeset = _nodeset_for_node(graph, node)
                if nodeset is None:
                    continue
                nested_compiled = GraphCompiler().compile(nodeset.graph, registry=self.registry)
                self._render_section(lines, nodeset.graph, nested_compiled, title=f"nodeset {nodeset.name}", indent=f"{indent}  ")

    def _layout(self, graph: GraphConfig, compiled: CompiledGraph) -> _Layout:
        findings_by_node = _findings_by_node(self.health_report)
        nodes: dict[str, _Node] = {}
        for index, spec in enumerate(graph.nodes):
            nodeset = _nodeset_for_node(graph, spec)
            flow_kind = _node_flow_kind(spec, compiled) or (nodeset.flow_kind if nodeset else FLOW_KIND_PROCESS)
            label = self._nodeset_label(spec, nodeset, flow_kind) if nodeset else self._node_label(spec, flow_kind)
            markers = findings_by_node.get(spec.name, ())
            if markers:
                label = (*label, *markers)
            nodes[spec.name] = _Node(spec.name, flow_kind, tuple(_shorten(line, limit=46) for line in label if line), index)
        edges = [_Edge(edge.source, edge.target, edge.when, index) for index, edge in enumerate(compiled.effective_edges)]
        back_edges, forward_edges = _detect_back_edges(nodes, edges)
        _assign_layers(nodes, forward_edges)
        layer_nodes = _order_layers(nodes, edges, back_edges)
        _assign_dimensions(nodes)
        _assign_coordinates(nodes, layer_nodes)
        width = max((node.x + node.width for node in nodes.values()), default=0) + 36
        height = max((node.y + node.height for node in nodes.values()), default=0) + 8
        return _Layout(nodes, edges, back_edges, width, height)

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
            nodeset = _nodeset_for_node(graph, node)
            flow_kind = _node_flow_kind(node, compiled) or (nodeset.flow_kind if nodeset else FLOW_KIND_PROCESS)
            details = [f"kind={flow_kind}", f"type={node.node_type}"]
            if node.status == STATUS_PLANNED:
                details.append("status=planned")
            if self._node_is_external(node):
                details.append("external=true")
            if nodeset is not None:
                details.extend((
                    f"requires={','.join(nodeset.requires or node.requires) or '-'}",
                    f"provides={','.join(nodeset.provides or node.provides) or '-'}",
                    f"exports={','.join(nodeset.exports) or '-'}",
                ))
            else:
                details.extend((
                    f"requires={','.join(node.requires) or '-'}",
                    f"provides={','.join(node.provides) or '-'}",
                ))
            lines.append(f"{indent}  {node.name}: " + "; ".join(details))
        lines.append("")

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
            message = _shorten(finding.get("message", ""), limit=160)
            lines.append(f"  [{severity}] {rule_id} {object_type}:{object_id} - {message}")

    def _node_label(self, node: NodeSpec, flow_kind: str) -> tuple[str, ...]:
        lines = [_badge(flow_kind, node), node.name]
        if node.status == STATUS_PLANNED:
            lines.append("PLANNED")
        if self._node_is_external(node):
            lines.append("external")
        return tuple(line for line in lines if line)

    def _nodeset_label(self, node: NodeSpec, nodeset: NodesetSpec | None, flow_kind: str) -> tuple[str, ...]:
        if nodeset is None:
            return self._node_label(node, flow_kind)
        lines = [_badge(flow_kind, node), node.name]
        if node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED:
            lines.append("PLANNED")
        return tuple(line for line in lines if line)

    def _node_is_external(self, node: NodeSpec) -> bool:
        if self.registry is None or node.status == STATUS_PLANNED or node.node_type.startswith("nodeset."):
            return False
        try:
            node_cls = self.registry.get(node.node_type)
        except Exception:
            return False
        return bool(getattr(getattr(node_cls, "NODE_INFO", None), "external", False))


class _Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.grid = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.occupied = [[False for _ in range(self.width)] for _ in range(self.height)]

    def set(self, x: int, y: int, char: str) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height) or self.occupied[y][x]:
            return
        existing = self.grid[y][x]
        self.grid[y][x] = _merge_line(existing, char)

    def force_set(self, x: int, y: int, char: str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = char

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return " "

    def draw_text(self, x: int, y: int, text: str) -> None:
        for offset, char in enumerate(text):
            self.force_set(x + offset, y, char)

    def hline(self, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.set(x, y, "─")

    def vline(self, x: int, y1: int, y2: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.set(x, y, "│")

    def mark_occupied(self, x: int, y: int, width: int, height: int) -> None:
        for yy in range(y, y + height):
            for xx in range(x, x + width):
                if 0 <= xx < self.width and 0 <= yy < self.height:
                    self.occupied[yy][xx] = True

    def can_place_text(self, x: int, y: int, text: str) -> bool:
        if y < 0 or y >= self.height or x < 0 or x + len(text) >= self.width:
            return False
        return all(self.get(x + offset, y) == " " and not self.occupied[y][x + offset] for offset in range(len(text)))

    def to_string(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self.grid).rstrip()


def _draw_node(canvas: _Canvas, node: _Node) -> None:
    lines = _shape_lines(node)
    for y_offset, line in enumerate(lines):
        canvas.draw_text(node.x, node.y + y_offset, line)
    canvas.mark_occupied(node.x, node.y, node.width, node.height)


def _shape_lines(node: _Node) -> list[str]:
    width = node.width
    inner = width - 4
    label = [line[:inner].center(inner) for line in node.label]
    if node.flow_kind == FLOW_KIND_TERMINAL:
        return ["╭" + "═" * (width - 2) + "╮", *(f"│ {line} │" for line in label), "╰" + "═" * (width - 2) + "╯"]
    if node.flow_kind == FLOW_KIND_DECISION:
        return _diamond_shape(label, width)
    if node.flow_kind == FLOW_KIND_IO:
        return _io_shape(label, width)
    if node.flow_kind == FLOW_KIND_PREDEFINED:
        return ["┌║" + "═" * (width - 4) + "║┐", *(f"│║{line}║│" for line in label), "└║" + "═" * (width - 4) + "║┘"]
    if node.flow_kind == FLOW_KIND_DATA_STORE:
        return ["  ." + "═" * (width - 6) + ".  ", "_(" + " " * (width - 4) + ")_", *(f"( {line} )" for line in label), "  '" + "═" * (width - 6) + "'  "]
    if node.flow_kind == FLOW_KIND_DOCUMENT:
        return ["┌" + "─" * (width - 2) + "┐", *(f"│ {line} │" for line in label), "╰" + "~" * (width - 3) + "╮", " " + "~" * (width - 3) + "╯"]
    if node.flow_kind == FLOW_KIND_PREPARATION:
        return ["  /" + "═" * (width - 6) + "\\  ", *(f"< {line} >" for line in label), "  \\" + "═" * (width - 6) + "/  "]
    return ["┌" + "─" * (width - 2) + "┐", *(f"│ {line} │" for line in label), "└" + "─" * (width - 2) + "┘"]


def _diamond_shape(label: list[str], width: int) -> list[str]:
    bar = max(8, min(12, width - 14))
    wide = min(width - 4, bar + 10)
    badge = label[0].strip() if label else "DECISION"
    name = label[1].strip() if len(label) > 1 else ""
    if len(label) > 2:
        name = " ".join((name, *[line.strip() for line in label[2:]])).strip()
    rows = [
        ("╱" + "═" * bar + "╲").center(width),
        ("╱ " + badge[:bar].center(bar) + " ╲").center(width),
        ("╱" + " " * wide + "╲").center(width),
        ("╱" + " " * (wide + 2) + "╲").center(width),
        ("╲ " + name[:wide].center(wide) + " ╱").center(width),
        ("╲" + " " * wide + "╱").center(width),
        ("╲" + " " * max(bar + 2, 1) + "╱").center(width),
        ("╲" + "═" * bar + "╱").center(width),
    ]
    return rows


def _io_shape(label: list[str], width: int) -> list[str]:
    inner = width - 8
    content = [line[:inner].center(inner) for line in label[:2]]
    while len(content) < 2:
        content.append(" " * inner)
    rows = [
        "    ╱" + "━" * inner + "╱",
        "   ╱ " + content[0] + " ╱",
        "  ╱ " + content[1] + " ╱",
        " ╱ " + " " * inner + " ╱",
        "╱" + "━" * inner + "╱",
    ]
    return [row[:width].ljust(width) for row in rows]


def _draw_edges(canvas: _Canvas, layout: _Layout) -> None:
    forward_by_source: dict[str, list[_Edge]] = {}
    for edge in layout.edges:
        if edge in layout.back_edges:
            _draw_back_edge(canvas, edge, layout)
        else:
            forward_by_source.setdefault(edge.source, []).append(edge)
    for edges in forward_by_source.values():
        for branch, edge in enumerate(edges):
            _draw_forward_edge(canvas, edge, layout, branch=branch, branches=len(edges))


def _draw_forward_edge(canvas: _Canvas, edge: _Edge, layout: _Layout, *, branch: int, branches: int) -> None:
    source = layout.nodes[edge.source]
    target = layout.nodes[edge.target]
    start_x = source.x + source.width // 2
    start_y = source.y + source.height
    end_x = target.x + target.width // 2
    end_y = target.y - 1
    if start_x == end_x:
        canvas.vline(start_x, start_y, end_y)
        canvas.force_set(end_x, end_y, "▼")
        _place_label(canvas, edge.label, start_x + 2, (start_y + end_y) // 2)
        return
    mid_y = start_y + 1 + branch * 2 if branches > 1 else (start_y + end_y) // 2
    if mid_y >= end_y:
        mid_y = max(start_y, end_y - 1)
    canvas.vline(start_x, start_y, mid_y)
    canvas.hline(start_x, end_x, mid_y)
    canvas.vline(end_x, mid_y, end_y)
    canvas.force_set(end_x, end_y, "▼")
    _place_label(canvas, edge.label, min(start_x, end_x) + 1, mid_y - 1)


def _draw_back_edge(canvas: _Canvas, edge: _Edge, layout: _Layout) -> None:
    source = layout.nodes[edge.source]
    target = layout.nodes[edge.target]
    source_x = source.x + source.width // 2
    source_y = source.y + source.height
    target_x = target.x + target.width
    target_y = target.y + target.height // 2
    loop_x = max(node.x + node.width for node in layout.nodes.values()) + 5 + edge.index * 2
    lane_y = source.y + source.height + 2
    canvas.vline(source_x, source_y, lane_y)
    canvas.hline(source_x, loop_x, lane_y)
    canvas.vline(loop_x, min(lane_y, target_y), max(lane_y, target_y))
    canvas.hline(target_x + 1, loop_x, target_y)
    canvas.force_set(target_x + 1, target_y, "◄")
    _place_label(canvas, edge.label or "loop", loop_x + 1, (lane_y + target_y) // 2)


def _place_label(canvas: _Canvas, label: str, x: int, y: int) -> None:
    if not label:
        return
    text = _shorten(label, limit=36)
    for yy in (y, y + 1, y - 1):
        if canvas.can_place_text(x, yy, text):
            canvas.draw_text(x, yy, text)
            return
    canvas.draw_text(max(0, min(x, canvas.width - len(text) - 1)), max(0, min(y, canvas.height - 1)), text)


def _detect_back_edges(nodes: dict[str, _Node], edges: list[_Edge]) -> tuple[set[_Edge], list[_Edge]]:
    outgoing: dict[str, list[_Edge]] = {name: [] for name in nodes}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge)
    back_edges: set[_Edge] = set()
    visited: set[str] = set()
    in_stack: set[str] = set()

    def walk(name: str) -> None:
        visited.add(name)
        in_stack.add(name)
        for edge in outgoing.get(name, ()):
            if edge.target in in_stack:
                back_edges.add(edge)
            elif edge.target not in visited:
                walk(edge.target)
        in_stack.discard(name)

    for name in nodes:
        if name not in visited:
            walk(name)
    return back_edges, [edge for edge in edges if edge not in back_edges]


def _assign_layers(nodes: dict[str, _Node], edges: list[_Edge]) -> None:
    incoming_count = {name: 0 for name in nodes}
    outgoing: dict[str, list[_Edge]] = {name: [] for name in nodes}
    for edge in edges:
        if edge.source in nodes and edge.target in nodes:
            incoming_count[edge.target] += 1
            outgoing[edge.source].append(edge)
    queue = [name for name, count in incoming_count.items() if count == 0]
    for name in queue:
        nodes[name].layer = 0
    while queue:
        name = queue.pop(0)
        for edge in outgoing.get(name, ()):
            nodes[edge.target].layer = max(nodes[edge.target].layer, nodes[name].layer + 1)
            incoming_count[edge.target] -= 1
            if incoming_count[edge.target] == 0:
                queue.append(edge.target)


def _order_layers(nodes: dict[str, _Node], edges: list[_Edge], back_edges: set[_Edge]) -> dict[int, list[str]]:
    layers: dict[int, list[str]] = {}
    for node in nodes.values():
        layers.setdefault(node.layer, []).append(node.name)
    forward_edges = [edge for edge in edges if edge not in back_edges]
    for _ in range(4):
        for layer in sorted(layers):
            names = layers[layer]
            if layer == 0:
                names.sort(key=lambda name: nodes[name].index)
                continue
            prev = {name: index for index, name in enumerate(layers.get(layer - 1, ())) }
            names.sort(key=lambda name: _barycenter(name, nodes, forward_edges, prev))
    return layers


def _barycenter(name: str, nodes: dict[str, _Node], edges: list[_Edge], prev: dict[str, int]) -> float:
    incoming = [edge for edge in edges if edge.target == name and edge.source in prev]
    if not incoming:
        return float(nodes[name].index)
    return sum(prev[edge.source] for edge in incoming) / len(incoming)


def _assign_dimensions(nodes: dict[str, _Node]) -> None:
    for node in nodes.values():
        inner = max(_minimum_inner_width(node.flow_kind), *(len(line) for line in node.label))
        node.width = inner + _shape_padding(node.flow_kind)
        node.height = len(_shape_lines(node))


def _minimum_inner_width(flow_kind: str) -> int:
    if flow_kind == FLOW_KIND_DECISION:
        return 18
    if flow_kind == FLOW_KIND_IO:
        return 16
    if flow_kind == FLOW_KIND_DATA_STORE:
        return 14
    if flow_kind == FLOW_KIND_PREDEFINED:
        return 14
    return 12


def _shape_padding(flow_kind: str) -> int:
    if flow_kind in {FLOW_KIND_DECISION, FLOW_KIND_IO}:
        return 8
    if flow_kind in {FLOW_KIND_DATA_STORE, FLOW_KIND_PREPARATION}:
        return 6
    if flow_kind == FLOW_KIND_PREDEFINED:
        return 6
    return 4


def _assign_coordinates(nodes: dict[str, _Node], layers: dict[int, list[str]]) -> None:
    y = 2
    for layer in sorted(layers):
        names = layers[layer]
        row_height = max(nodes[name].height for name in names)
        row_width = sum(nodes[name].width for name in names) + max(0, len(names) - 1) * 10
        x = max(2, 40 - row_width // 2)
        for name in names:
            node = nodes[name]
            node.x = x
            node.y = y + (row_height - node.height) // 2
            x += node.width + 10
        y += row_height + 5


def _merge_line(existing: str, incoming: str) -> str:
    if existing == " ":
        return incoming
    if existing == incoming:
        return existing
    horizontal = "─"
    vertical = "│"
    if {existing, incoming} == {horizontal, vertical}:
        return "┼"
    if existing in "┼├┤┬┴" or incoming in "┼├┤┬┴":
        return "┼"
    return incoming if existing in "─│" else existing


def _nodeset_for_node(graph: GraphConfig, node: NodeSpec) -> NodesetSpec | None:
    if not node.node_type.startswith("nodeset."):
        return None
    return graph.nodesets.get(node.node_type.removeprefix("nodeset."))


def _node_flow_kind(node: NodeSpec, compiled: CompiledGraph) -> str:
    if node.status == STATUS_PLANNED:
        return node.flow_kind
    return compiled.flow_kinds.get(node.name, "")


def _badge(flow_kind: str, node: NodeSpec) -> str:
    if flow_kind == FLOW_KIND_TERMINAL:
        name = node.name.lower()
        return "● END" if name.endswith("end") or name == "end" else "● START"
    if flow_kind == FLOW_KIND_DECISION:
        return "DECISION"
    if flow_kind == FLOW_KIND_IO:
        return "⇄ I/O"
    if flow_kind == FLOW_KIND_PREDEFINED:
        return "CALL"
    if flow_kind == FLOW_KIND_DATA_STORE:
        return "▣ STORE"
    if flow_kind == FLOW_KIND_DOCUMENT:
        return "DOC"
    if flow_kind == FLOW_KIND_PREPARATION:
        return "INIT"
    return "PROCESS"


def _node_semantic_lines(node: NodeSpec) -> tuple[str, ...]:
    lines: list[str] = []
    for key in ("display_name", "category", "version", "description"):
        value = node.params.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key}: {value.strip()}" if key != "description" else value.strip())
    return tuple(lines)


def _key_line(label: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
    return f"{label}: {', '.join(values)}"


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


def _shorten(value: object, *, limit: int = 120) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
