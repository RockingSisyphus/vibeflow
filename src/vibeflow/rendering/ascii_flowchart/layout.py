from __future__ import annotations

from vibeflow.rendering.ascii_flowchart.canvas import Canvas
from vibeflow.rendering.ascii_flowchart.model import AsciiEdge, AsciiLayout, AsciiNode
from vibeflow.rendering.ascii_flowchart.shapes import minimum_inner_width, shape_lines, shape_padding
from vibeflow.rendering.helpers import shorten


def build_layout(nodes: dict[str, AsciiNode], edges: list[AsciiEdge]) -> AsciiLayout:
    back_edges, forward_edges = _detect_back_edges(nodes, edges)
    _assign_layers(nodes, forward_edges)
    layer_nodes = _order_layers(nodes, edges, back_edges)
    _assign_dimensions(nodes)
    _assign_coordinates(nodes, layer_nodes)
    width = max((node.x + node.width for node in nodes.values()), default=0) + 36
    height = max((node.y + node.height for node in nodes.values()), default=0) + 8
    return AsciiLayout(nodes, edges, back_edges, width, height)


def draw_edges(canvas: Canvas, layout: AsciiLayout) -> None:
    forward_by_source: dict[str, list[AsciiEdge]] = {}
    for edge in layout.edges:
        if edge in layout.back_edges:
            _draw_back_edge(canvas, edge, layout)
        else:
            forward_by_source.setdefault(edge.source, []).append(edge)
    for edges in forward_by_source.values():
        for branch, edge in enumerate(edges):
            _draw_forward_edge(canvas, edge, layout, branch=branch, branches=len(edges))


def _draw_forward_edge(canvas: Canvas, edge: AsciiEdge, layout: AsciiLayout, *, branch: int, branches: int) -> None:
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


def _draw_back_edge(canvas: Canvas, edge: AsciiEdge, layout: AsciiLayout) -> None:
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


def _place_label(canvas: Canvas, label: str, x: int, y: int) -> None:
    if not label:
        return
    text = shorten(label, limit=36)
    for yy in (y, y + 1, y - 1):
        if canvas.can_place_text(x, yy, text):
            canvas.draw_text(x, yy, text)
            return
    canvas.draw_text(max(0, min(x, canvas.width - len(text) - 1)), max(0, min(y, canvas.height - 1)), text)


def _detect_back_edges(nodes: dict[str, AsciiNode], edges: list[AsciiEdge]) -> tuple[set[AsciiEdge], list[AsciiEdge]]:
    outgoing: dict[str, list[AsciiEdge]] = {name: [] for name in nodes}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge)
    back_edges: set[AsciiEdge] = set()
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


def _assign_layers(nodes: dict[str, AsciiNode], edges: list[AsciiEdge]) -> None:
    incoming_count = {name: 0 for name in nodes}
    outgoing: dict[str, list[AsciiEdge]] = {name: [] for name in nodes}
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


def _order_layers(nodes: dict[str, AsciiNode], edges: list[AsciiEdge], back_edges: set[AsciiEdge]) -> dict[int, list[str]]:
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


def _barycenter(name: str, nodes: dict[str, AsciiNode], edges: list[AsciiEdge], prev: dict[str, int]) -> float:
    incoming = [edge for edge in edges if edge.target == name and edge.source in prev]
    if not incoming:
        return float(nodes[name].index)
    return sum(prev[edge.source] for edge in incoming) / len(incoming)


def _assign_dimensions(nodes: dict[str, AsciiNode]) -> None:
    for node in nodes.values():
        inner = max(minimum_inner_width(node.flow_kind), *(len(line) for line in node.label))
        node.width = inner + shape_padding(node.flow_kind)
        node.height = len(shape_lines(node))


def _assign_coordinates(nodes: dict[str, AsciiNode], layers: dict[int, list[str]]) -> None:
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
