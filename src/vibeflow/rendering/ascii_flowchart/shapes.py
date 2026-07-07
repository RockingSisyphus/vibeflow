from __future__ import annotations

from vibeflow.rendering.ascii_flowchart.canvas import Canvas
from vibeflow.rendering.ascii_flowchart.model import AsciiNode
from vibeflow.node import (
    FLOW_KIND_DATA_STORE,
    FLOW_KIND_DECISION,
    FLOW_KIND_DOCUMENT,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    FLOW_KIND_PREPARATION,
    FLOW_KIND_TERMINAL,
)


def draw_node(canvas: Canvas, node: AsciiNode) -> None:
    lines = shape_lines(node)
    for y_offset, line in enumerate(lines):
        canvas.draw_text(node.x, node.y + y_offset, line)
    canvas.mark_occupied(node.x, node.y, node.width, node.height)


def shape_lines(node: AsciiNode) -> list[str]:
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


def minimum_inner_width(flow_kind: str) -> int:
    if flow_kind == FLOW_KIND_DECISION:
        return 18
    if flow_kind == FLOW_KIND_IO:
        return 16
    if flow_kind in {FLOW_KIND_DATA_STORE, FLOW_KIND_PREDEFINED}:
        return 14
    return 12


def shape_padding(flow_kind: str) -> int:
    if flow_kind in {FLOW_KIND_DECISION, FLOW_KIND_IO}:
        return 8
    if flow_kind in {FLOW_KIND_DATA_STORE, FLOW_KIND_PREPARATION, FLOW_KIND_PREDEFINED}:
        return 6
    return 4


def _diamond_shape(label: list[str], width: int) -> list[str]:
    bar = max(8, min(12, width - 14))
    wide = min(width - 4, bar + 10)
    badge = label[0].strip() if label else "DECISION"
    name = label[1].strip() if len(label) > 1 else ""
    if len(label) > 2:
        name = " ".join((name, *[line.strip() for line in label[2:]])).strip()
    return [
        ("╱" + "═" * bar + "╲").center(width),
        ("╱ " + badge[:bar].center(bar) + " ╲").center(width),
        ("╱" + " " * wide + "╲").center(width),
        ("╱" + " " * (wide + 2) + "╲").center(width),
        ("╲ " + name[:wide].center(wide) + " ╱").center(width),
        ("╲" + " " * wide + "╱").center(width),
        ("╲" + " " * max(bar + 2, 1) + "╱").center(width),
        ("╲" + "═" * bar + "╱").center(width),
    ]


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
