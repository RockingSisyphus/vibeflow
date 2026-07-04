from __future__ import annotations

import re
import tempfile
import xml.sax.saxutils
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .compiler import CompiledGraph
from .flowchart_render_helpers import compile_for_render, nodeset_for_node
from .graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from .mermaid import (
    MERMAID_LAYOUT_DEFAULT,
    _escape_label,
    _mapping_items,
    _resource_label,
    _resources_payload,
    _safe_id,
    export_mermaid,
)
from .mermaid_render import DEFAULT_MERMAID_MAX_EDGES, DEFAULT_MERMAID_MAX_TEXT_SIZE, MermaidRenderError, render_mermaid_svg


REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH = 3200.0
_DETAIL_PANEL_COLUMN_GAP = 56.0
_DETAIL_PANEL_ROW_GAP = 36.0
_DETAIL_PANEL_TITLE_HEIGHT = 40.0
_FRAGMENT_FRAME_PADDING = 10.0
_REVIEW_COLUMNS_STYLE = (
    "<style>.review-title{font-family:Arial,sans-serif;font-size:22px;font-weight:800;fill:#0f172a}"
    ".review-panel-frame{fill:#ffffff;fill-opacity:.94;stroke:#334155;stroke-width:2}"
    ".review-title-bar{fill:#dbeafe;stroke:#334155;stroke-width:2}</style>"
)
_DETAIL_PANEL_STYLE = (
    "<style>.review-title{font-family:Arial,sans-serif;font-size:20px;font-weight:800;fill:#0f172a}"
    ".review-panel-frame{fill:#ffffff;fill-opacity:.94;stroke:#475569;stroke-width:2}"
    ".review-title-bar{fill:#e0f2fe;stroke:#475569;stroke-width:2}"
    ".review-panel-guide{stroke:#64748b;stroke-width:1.5;stroke-dasharray:6 4;fill:none}</style>"
)
_PLACEHOLDER_STYLE = (
    "<style>.placeholder-title{font-family:Arial,sans-serif;font-size:16px;font-weight:700;fill:#111827}"
    ".placeholder-text{font-family:Arial,sans-serif;font-size:14px;fill:#4b5563}"
    ".placeholder-box{fill:#f9fafb;stroke:#d1d5db;stroke-width:1}</style>"
)
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)


@dataclass(frozen=True)
class _SvgFragment:
    title: str
    svg_text: str
    width: float
    height: float


def render_review_columns_svg(
    graph: GraphConfig,
    compiled: CompiledGraph,
    output: Path,
    *,
    registry: object | None = None,
    resources: object | None = None,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
    theme: str = "default",
    background: str = "transparent",
    max_text_size: int | None = None,
    max_edges: int | None = None,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
) -> None:
    actual_review_fragment_max_width = _validate_review_fragment_max_width(review_fragment_max_width)
    actual_max_text_size = max_text_size if max_text_size is not None else DEFAULT_MERMAID_MAX_TEXT_SIZE
    actual_max_edges = max_edges if max_edges is not None else DEFAULT_MERMAID_MAX_EDGES
    with tempfile.TemporaryDirectory(prefix="vibeflow-review-svg-") as temp_dir:
        root = Path(temp_dir)
        columns = _build_columns(
            graph,
            compiled,
            root,
            registry=registry,
            resources=resources,
            expand_nodesets=expand_nodesets,
            show_contract=show_contract,
            show_semantics=show_semantics,
            theme=theme,
            background=background,
            max_text_size=actual_max_text_size,
            max_edges=actual_max_edges,
            review_fragment_max_width=actual_review_fragment_max_width,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_compose_svg(columns, background=background, review_fragment_max_width=actual_review_fragment_max_width), encoding="utf-8")


def _build_columns(
    graph: GraphConfig,
    compiled: CompiledGraph,
    temp_dir: Path,
    *,
    registry: object | None,
    resources: object | None,
    expand_nodesets: bool,
    show_contract: bool,
    show_semantics: bool,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
    review_fragment_max_width: float,
) -> list[list[_SvgFragment]]:
    columns: list[list[_SvgFragment]] = [
        [
            _render_fragment(
                "main pipeline",
                export_mermaid(
                    graph,
                    compiled=compiled,
                    registry=registry,
                    expand_nodesets=False,
                    show_contract=show_contract,
                    show_semantics=show_semantics,
                    mermaid_layout=MERMAID_LAYOUT_DEFAULT,
                ),
                temp_dir,
                theme=theme,
                background=background,
                max_text_size=max_text_size,
                max_edges=max_edges,
            )
        ]
    ]
    columns.extend(_resource_columns(resources, temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges))
    if expand_nodesets:
        nodeset_fragments = _nodeset_fragments(
            graph,
            temp_dir,
            registry=registry,
            show_contract=show_contract,
            show_semantics=show_semantics,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
            review_fragment_max_width=review_fragment_max_width,
        )
        if nodeset_fragments:
            columns.append(nodeset_fragments)
    return columns


def _resource_columns(
    resources: object | None,
    temp_dir: Path,
    *,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
) -> list[list[_SvgFragment]]:
    payload = _resources_payload(resources)
    columns: list[list[_SvgFragment]] = []
    plugins = _mapping_items(payload.get("plugins", ()))
    if plugins:
        columns.append([_render_fragment("plugins", _resource_mermaid("plugins", plugins, kind="plugin"), temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges)])
    base_lib_payload = payload.get("base_lib", {})
    modules = _mapping_items(base_lib_payload.get("modules", ()) if isinstance(base_lib_payload, Mapping) else ())
    if modules:
        columns.append([_render_fragment("base_lib", _resource_mermaid("base_lib", modules, kind="base_lib"), temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges)])
    return columns


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
                f"{node.name} - {nodeset.name}",
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
    if nodeset.name in visited_nodesets:
        return _placeholder_fragment(
            title,
            f"recursive nodeset expansion skipped: {nodeset.name}",
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
            f"{child_node.name} - {child_nodeset.name}",
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
            visited_nodesets=(*visited_nodesets, nodeset.name),
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


def _nodeset_mermaid(
    graph: GraphConfig,
    compiled: CompiledGraph,
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
    node_ids = tuple(_safe_id(node.name) for node in graph.nodes)
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
        "  classDef baseLibResource fill:#ecfdf5,stroke:#059669,color:#064e3b;",
        "  classDef pluginResource fill:#eff6ff,stroke:#2563eb,color:#1e3a8a;",
        "  classDef plannedResource fill:#fef08a,stroke:#ca8a04,stroke-width:3px,stroke-dasharray: 6 3,color:#713f12;",
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


def _compose_svg(
    columns: list[list[_SvgFragment]],
    *,
    background: str,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
) -> str:
    actual_max_width = _validate_review_fragment_max_width(review_fragment_max_width)
    padding = 24.0
    column_gap = 64.0
    row_gap = 44.0
    title_height = 42.0
    column_widths = [max(_display_size(fragment, max_width=actual_max_width)[0] for fragment in column) for column in columns]
    column_heights = [_column_height(column, title_height=title_height, row_gap=row_gap, review_fragment_max_width=actual_max_width) for column in columns]
    total_width = padding * 2 + sum(column_widths) + column_gap * max(0, len(columns) - 1)
    total_height = padding * 2 + (max(column_heights) if column_heights else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" style="max-width: {total_width:.3f}px; background-color: {xml.sax.saxutils.escape(background)};" viewBox="0 0 {total_width:.3f} {total_height:.3f}" role="graphics-document document" aria-roledescription="flowchart-review-columns">',
        _REVIEW_COLUMNS_STYLE,
    ]
    if background != "transparent":
        parts.append(f'<rect x="0" y="0" width="{total_width:.3f}" height="{total_height:.3f}" fill="{xml.sax.saxutils.escape(background)}"/>')
    x = padding
    for column_index, (column, column_width) in enumerate(zip(columns, column_widths)):
        parts.extend(
            _column_svg(
                column,
                x=x,
                y=padding,
                width=column_width,
                title_height=title_height,
                row_gap=row_gap,
                review_fragment_max_width=actual_max_width,
                fragment_prefix=f"column_{column_index}",
            )
        )
        x += column_width + column_gap
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _column_svg(
    column: list[_SvgFragment],
    *,
    x: float,
    y: float,
    width: float,
    title_height: float,
    row_gap: float,
    review_fragment_max_width: float,
    fragment_prefix: str,
) -> list[str]:
    parts: list[str] = []
    cursor = y
    for index, fragment in enumerate(column):
        title = xml.sax.saxutils.escape(fragment.title)
        display_width, display_height = _display_size(fragment, max_width=review_fragment_max_width)
        image_x = x + (width - display_width) / 2
        frame_x = x - _FRAGMENT_FRAME_PADDING
        frame_y = cursor - _FRAGMENT_FRAME_PADDING
        frame_width = width + _FRAGMENT_FRAME_PADDING * 2
        frame_height = title_height + display_height + _FRAGMENT_FRAME_PADDING * 2
        parts.append(
            f'<rect class="review-panel-frame" x="{frame_x:.3f}" y="{frame_y:.3f}" '
            f'width="{frame_width:.3f}" height="{frame_height:.3f}" rx="6"/>'
        )
        parts.append(
            f'<rect class="review-title-bar" x="{frame_x:.3f}" y="{frame_y:.3f}" '
            f'width="{frame_width:.3f}" height="{title_height:.3f}" rx="6"/>'
        )
        parts.append(f'<text class="review-title" x="{x:.3f}" y="{cursor + title_height - 12:.3f}">{title}</text>')
        cursor += title_height
        parts.extend(
            _inline_fragment_svg(
                fragment,
                x=image_x,
                y=cursor,
                width=display_width,
                height=display_height,
                fragment_prefix=fragment_prefix,
                fragment_index=index,
            )
        )
        cursor += display_height + row_gap
    return parts


def _column_height(
    column: list[_SvgFragment],
    *,
    title_height: float,
    row_gap: float,
    review_fragment_max_width: float,
) -> float:
    return sum(title_height + _display_size(fragment, max_width=review_fragment_max_width)[1] for fragment in column) + row_gap * max(0, len(column) - 1)


def _display_size(fragment: _SvgFragment, *, max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH) -> tuple[float, float]:
    if fragment.width <= max_width:
        return fragment.width, fragment.height
    scale = max_width / fragment.width
    return max_width, fragment.height * scale


def _inline_fragment_svg(
    fragment: _SvgFragment,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    fragment_prefix: str,
    fragment_index: int,
) -> list[str]:
    try:
        root = ET.fromstring(fragment.svg_text)
    except ET.ParseError as exc:
        raise MermaidRenderError(f"could not inline SVG fragment '{fragment.title}': {exc}") from exc
    min_x, min_y, source_width, source_height = _viewbox_box(fragment.svg_text)
    scale_x = width / source_width if source_width else 1.0
    scale_y = height / source_height if source_height else 1.0
    prefix = f"vf_{fragment_prefix}_{fragment_index}_"
    _prefix_svg_ids(root, prefix)
    inner = "".join(ET.tostring(child, encoding="unicode") for child in list(root))
    transform = f"translate({x:.3f} {y:.3f}) scale({scale_x:.6f} {scale_y:.6f})"
    if min_x or min_y:
        transform += f" translate({-min_x:.3f} {-min_y:.3f})"
    return [f'<g class="review-inline-fragment" transform="{transform}">{inner}</g>']


def _prefix_svg_ids(root: ET.Element, prefix: str) -> None:
    id_map: dict[str, str] = {}
    for element in root.iter():
        original = element.attrib.get("id")
        if original:
            id_map[original] = f"{prefix}{original}"
    if not id_map:
        return
    for element in root.iter():
        if "id" in element.attrib:
            element.attrib["id"] = id_map[element.attrib["id"]]
        for key, value in list(element.attrib.items()):
            element.attrib[key] = _rewrite_svg_reference(value, id_map)
        if element.text:
            element.text = _rewrite_svg_reference(element.text, id_map)


def _rewrite_svg_reference(value: str, id_map: Mapping[str, str]) -> str:
    rewritten = value
    for old, new in id_map.items():
        escaped = re.escape(old)
        rewritten = re.sub(rf"url\((['\"]?)#{escaped}\1\)", f"url(#{new})", rewritten)
        if rewritten == f"#{old}":
            rewritten = f"#{new}"
    return rewritten


def _validate_review_fragment_max_width(value: float) -> float:
    try:
        width = float(value)
    except (TypeError, ValueError) as exc:
        raise MermaidRenderError("review_fragment_max_width must be a positive number") from exc
    if width <= 0:
        raise MermaidRenderError("review_fragment_max_width must be a positive number")
    return width


def _viewbox_size(svg_text: str) -> tuple[float, float]:
    return _viewbox_box(svg_text)[2:]


def _viewbox_box(svg_text: str) -> tuple[float, float, float, float]:
    match = re.search(r'viewBox="([-0-9.]+) ([-0-9.]+) ([0-9.]+) ([0-9.]+)"', svg_text)
    if match:
        return float(match.group(1)), float(match.group(2)), float(match.group(3)), float(match.group(4))
    width = re.search(r'width="([0-9.]+)"', svg_text)
    height = re.search(r'height="([0-9.]+)"', svg_text)
    return 0.0, 0.0, float(width.group(1)) if width else 100.0, float(height.group(1)) if height else 100.0
