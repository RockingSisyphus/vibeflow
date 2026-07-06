from __future__ import annotations

import re
import xml.sax.saxutils
from pathlib import Path
from typing import Mapping

from .flowchart_render_helpers import compile_for_render, nodeset_for_node
from .graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from .mermaid import MERMAID_LAYOUT_DEFAULT, _escape_label, _resource_label, _safe_id, export_mermaid
from .mermaid_render import DEFAULT_MERMAID_MAX_EDGES, DEFAULT_MERMAID_MAX_TEXT_SIZE, render_mermaid_svg
from .mermaid_review_layout import _column_height, _column_svg, _display_size, _validate_review_fragment_max_width, _viewbox_size
from .mermaid_review_types import (
    DETAIL_PANEL_COLUMN_GAP as _DETAIL_PANEL_COLUMN_GAP,
    DETAIL_PANEL_ROW_GAP as _DETAIL_PANEL_ROW_GAP,
    DETAIL_PANEL_STYLE as _DETAIL_PANEL_STYLE,
    DETAIL_PANEL_TITLE_HEIGHT as _DETAIL_PANEL_TITLE_HEIGHT,
    PLACEHOLDER_STYLE as _PLACEHOLDER_STYLE,
    REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    _SvgFragment,
)
from .visual_style import MERMAID_RESOURCE_CLASS_ORDER, mermaid_class_def_lines

def _nodeset_fragments(
    graph: GraphConfig,
    temp_dir: Path,
    *,
    registry: object | None,
    show_contract: bool,
    show_semantics: bool,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
    review_fragment_max_width: float,
) -> list[_SvgFragment]:
    fragments: list[_SvgFragment] = []
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is None:
            continue
        fragments.append(
            _render_nodeset_detail_fragment(
                _nodeset_fragment_title(node, nodeset),
                nodeset,
                temp_dir,
                registry=registry,
                show_contract=show_contract,
                show_semantics=show_semantics,
                theme=theme,
                background=background,
                max_text_size=max_text_size,
                max_edges=max_edges,
                review_fragment_max_width=review_fragment_max_width,
                visited_nodesets=(),
            )
        )
    return fragments

def _render_nodeset_detail_fragment(
    title: str,
    nodeset: NodesetSpec,
    temp_dir: Path,
    *,
    registry: object | None,
    show_contract: bool,
    show_semantics: bool,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    visited_nodesets: tuple[str, ...] = (),
) -> _SvgFragment:
    if nodeset.type_key in visited_nodesets:
        return _placeholder_fragment(
            title,
            f"recursive nodeset expansion skipped: {nodeset.type_key}",
            background=background,
        )
    if not nodeset.graph.nodes:
        return _placeholder_fragment(title, "nodeset has no concrete pipeline", background=background)

    compiled = compile_for_render(nodeset.graph, None, registry)
    child_nodesets = _direct_nodeset_calls(nodeset.graph)
    if not child_nodesets:
        return _render_fragment(
            title,
            _nodeset_mermaid(
                nodeset.graph,
                compiled,
                registry=registry,
                show_contract=show_contract,
                show_semantics=show_semantics,
                direction="LR",
            ),
            temp_dir,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
        )

    parent_fragment = _render_fragment(
        "parent flow",
        _nodeset_mermaid(
            nodeset.graph,
            compiled,
            registry=registry,
            show_contract=show_contract,
            show_semantics=show_semantics,
            direction="TD",
        ),
        temp_dir,
        theme=theme,
        background=background,
        max_text_size=max_text_size,
        max_edges=max_edges,
    )
    child_fragments = [
        _render_nodeset_detail_fragment(
            _nodeset_fragment_title(child_node, child_nodeset),
            child_nodeset,
            temp_dir,
            registry=registry,
            show_contract=show_contract,
            show_semantics=show_semantics,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
            review_fragment_max_width=review_fragment_max_width,
            visited_nodesets=(*visited_nodesets, nodeset.type_key),
        )
        for child_node, child_nodeset in child_nodesets
    ]
    svg_text = _compose_detail_panel_svg(
        parent_fragment,
        child_fragments,
        background=background,
        review_fragment_max_width=review_fragment_max_width,
    )
    width, height = _viewbox_size(svg_text)
    return _SvgFragment(title=title, svg_text=svg_text, width=width, height=height)

def _direct_nodeset_calls(graph: GraphConfig) -> tuple[tuple[NodeSpec, NodesetSpec], ...]:
    calls: list[tuple[NodeSpec, NodesetSpec]] = []
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is not None:
            calls.append((node, nodeset))
    return tuple(calls)

def _nodeset_fragment_title(node: NodeSpec, nodeset: NodesetSpec) -> str:
    title = node.metadata.display_name or nodeset.display_name or node.id
    return f"{title} (id: {node.id}, type_key: {nodeset.type_key})"

def _nodeset_mermaid(
    graph: GraphConfig,
    compiled: object,
    *,
    registry: object | None,
    show_contract: bool,
    show_semantics: bool,
    direction: str,
) -> str:
    text = export_mermaid(
        graph,
        compiled=compiled,
        registry=registry,
        expand_nodesets=False,
        show_contract=show_contract,
        show_semantics=show_semantics,
        mermaid_layout=MERMAID_LAYOUT_DEFAULT,
    )
    text = _force_flowchart_direction(text, direction)
    return _inject_layout_spine(text, graph)

def _force_flowchart_direction(mermaid_text: str, direction: str) -> str:
    return re.sub(r"^flowchart\s+\w+", f"flowchart {direction}", mermaid_text, count=1)

def _inject_layout_spine(mermaid_text: str, graph: GraphConfig) -> str:
    node_ids = tuple(_safe_id(node.id) for node in graph.nodes)
    if not node_ids:
        return mermaid_text
    start_id = _unique_layout_id("__vibeflow_layout_start", node_ids)
    end_id = _unique_layout_id("__vibeflow_layout_end", (*node_ids, start_id))
    chain = (start_id, *node_ids, end_id)
    lines = mermaid_text.rstrip().splitlines()
    lines.extend(
        (
            "  classDef layoutAnchor fill:transparent,stroke:transparent,color:transparent;",
            f'  {start_id}@{{ shape: rect, label: "" }}',
            f'  {end_id}@{{ shape: rect, label: "" }}',
            f"  class {start_id},{end_id} layoutAnchor;",
        )
    )
    for source, target in zip(chain, chain[1:]):
        lines.append(f"  {source} ~~~ {target}")
    return "\n".join(lines) + "\n"

def _unique_layout_id(base: str, reserved: tuple[str, ...]) -> str:
    reserved_ids = set(reserved)
    candidate = base
    while candidate in reserved_ids:
        candidate += "_"
    return candidate

def _compose_detail_panel_svg(
    parent_fragment: _SvgFragment,
    child_fragments: list[_SvgFragment],
    *,
    background: str,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
) -> str:
    actual_max_width = _validate_review_fragment_max_width(review_fragment_max_width)
    padding = 24.0
    parent_width, parent_height = _display_size(parent_fragment, max_width=actual_max_width)
    child_width = max((_display_size(fragment, max_width=actual_max_width)[0] for fragment in child_fragments), default=0.0)
    parent_block_height = _DETAIL_PANEL_TITLE_HEIGHT + parent_height
    child_block_height = (
        _column_height(
            child_fragments,
            title_height=_DETAIL_PANEL_TITLE_HEIGHT,
            row_gap=_DETAIL_PANEL_ROW_GAP,
            review_fragment_max_width=actual_max_width,
        )
        if child_fragments
        else 0.0
    )
    total_width = padding * 2 + parent_width
    if child_fragments:
        total_width += _DETAIL_PANEL_COLUMN_GAP + child_width
    total_height = padding * 2 + max(parent_block_height, child_block_height)
    parts = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="100%" style="max-width: {total_width:.3f}px; '
            f'background-color: {xml.sax.saxutils.escape(background)};" '
            f'viewBox="0 0 {total_width:.3f} {total_height:.3f}" role="graphics-document document" '
            'aria-roledescription="flowchart-nodeset-detail-panel">'
        ),
        _DETAIL_PANEL_STYLE,
    ]
    if background != "transparent":
        parts.append(
            f'<rect x="0" y="0" width="{total_width:.3f}" height="{total_height:.3f}" '
            f'fill="{xml.sax.saxutils.escape(background)}"/>'
        )
    parts.extend(
        _column_svg(
            [parent_fragment],
            x=padding,
            y=padding,
            width=parent_width,
            title_height=_DETAIL_PANEL_TITLE_HEIGHT,
            row_gap=_DETAIL_PANEL_ROW_GAP,
            review_fragment_max_width=actual_max_width,
            fragment_prefix="parent",
        )
    )
    if child_fragments:
        child_x = padding + parent_width + _DETAIL_PANEL_COLUMN_GAP
        parts.extend(
            _column_svg(
                child_fragments,
                x=child_x,
                y=padding,
                width=child_width,
                title_height=_DETAIL_PANEL_TITLE_HEIGHT,
                row_gap=_DETAIL_PANEL_ROW_GAP,
                review_fragment_max_width=actual_max_width,
                fragment_prefix="children",
            )
        )
        guide_y = padding + _DETAIL_PANEL_TITLE_HEIGHT / 2
        parts.append(
            f'<path class="review-panel-guide" d="M {padding + parent_width + 12:.3f} '
            f'{guide_y:.3f} H {child_x - 12:.3f}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"

def _placeholder_fragment(title: str, message: str, *, background: str) -> _SvgFragment:
    width = 520.0
    height = 110.0
    parts = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
            f'style="max-width: {width:.3f}px; background-color: {xml.sax.saxutils.escape(background)};" '
            f'viewBox="0 0 {width:.3f} {height:.3f}" role="graphics-document document" '
            'aria-roledescription="flowchart-nodeset-placeholder">'
        ),
        _PLACEHOLDER_STYLE,
    ]
    if background != "transparent":
        parts.append(
            f'<rect x="0" y="0" width="{width:.3f}" height="{height:.3f}" '
            f'fill="{xml.sax.saxutils.escape(background)}"/>'
        )
    parts.extend(
        (
            f'<rect class="placeholder-box" x="1" y="1" width="{width - 2:.3f}" height="{height - 2:.3f}" rx="6"/>',
            f'<text class="placeholder-title" x="20" y="38">{xml.sax.saxutils.escape(title)}</text>',
            f'<text class="placeholder-text" x="20" y="68">{xml.sax.saxutils.escape(message)}</text>',
            "</svg>",
        )
    )
    svg_text = "\n".join(parts) + "\n"
    return _SvgFragment(title=title, svg_text=svg_text, width=width, height=height)

def _render_fragment(
    title: str,
    mermaid_text: str,
    temp_dir: Path,
    *,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
) -> _SvgFragment:
    path = temp_dir / f"fragment_{len(list(temp_dir.glob('fragment_*.svg')))}.svg"
    render_mermaid_svg(
        mermaid_text,
        path,
        theme=theme,
        background=background,
        max_text_size=max_text_size,
        max_edges=max_edges,
    )
    svg_text = path.read_text(encoding="utf-8")
    width, height = _viewbox_size(svg_text)
    return _SvgFragment(title=title, svg_text=svg_text, width=width, height=height)

def _resource_mermaid(root_label: str, resources: tuple[Mapping[str, object], ...], *, kind: str) -> str:
    root_id = f"resource_{root_label}"
    child_shape = "hex" if kind == "plugin" else "fr-rect"
    child_class = "pluginResource" if kind == "plugin" else "baseLibResource"
    lines = [
        "flowchart LR",
        *(f"  {line}" for line in mermaid_class_def_lines(MERMAID_RESOURCE_CLASS_ORDER)),
        f'  {root_id}@{{ shape: hex, label: "{_escape_label(root_label)}" }}',
        f"  class {root_id} {child_class};",
    ]
    for index, resource in enumerate(resources):
        resource_id = f"{root_id}_{index}"
        label = _resource_label(resource, kind=kind, show_semantics=True)
        lines.append(f'  {resource_id}@{{ shape: {child_shape}, label: "{_escape_label(label)}" }}')
        lines.append(f"  {root_id} -.-> {resource_id}")
        status = str(resource.get("status", "implemented"))
        lines.append(f"  class {resource_id} {'plannedResource' if status == STATUS_PLANNED else child_class};")
    return "\n".join(lines) + "\n"
