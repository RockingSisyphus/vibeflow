from __future__ import annotations

import base64
import re
import tempfile
import xml.sax.saxutils
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .compiler import CompiledGraph
from .flowchart_render_helpers import compile_for_render, nodeset_for_node
from .graph_config import GraphConfig, STATUS_PLANNED
from .mermaid import MERMAID_LAYOUT_DEFAULT, _escape_label, _mapping_items, _resource_label, _resources_payload, export_mermaid
from .mermaid_render import DEFAULT_MERMAID_MAX_EDGES, DEFAULT_MERMAID_MAX_TEXT_SIZE, render_mermaid_svg


REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH = 3200.0


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
) -> None:
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
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_compose_svg(columns, background=background), encoding="utf-8")


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
) -> list[_SvgFragment]:
    fragments: list[_SvgFragment] = []
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is None:
            continue
        nested_compiled = compile_for_render(nodeset.graph, None, registry)
        text = export_mermaid(
            nodeset.graph,
            compiled=nested_compiled,
            registry=registry,
            expand_nodesets=True,
            show_contract=show_contract,
            show_semantics=show_semantics,
            mermaid_layout=MERMAID_LAYOUT_DEFAULT,
        ).replace("flowchart TD", "flowchart LR", 1)
        fragments.append(_render_fragment(f"{node.name} - {nodeset.name}", text, temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges))
    return fragments


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


def _compose_svg(columns: list[list[_SvgFragment]], *, background: str) -> str:
    padding = 24.0
    column_gap = 64.0
    row_gap = 44.0
    title_height = 30.0
    column_widths = [max(_display_size(fragment)[0] for fragment in column) for column in columns]
    column_heights = [_column_height(column, title_height=title_height, row_gap=row_gap) for column in columns]
    total_width = padding * 2 + sum(column_widths) + column_gap * max(0, len(columns) - 1)
    total_height = padding * 2 + (max(column_heights) if column_heights else 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100%" style="max-width: {total_width:.3f}px; background-color: {xml.sax.saxutils.escape(background)};" viewBox="0 0 {total_width:.3f} {total_height:.3f}" role="graphics-document document" aria-roledescription="flowchart-review-columns">',
        "<style>.review-title{font-family:Arial,sans-serif;font-size:18px;font-weight:700;fill:#111827}.review-column-bg{fill:transparent;stroke:#d1d5db;stroke-width:1}</style>",
    ]
    if background != "transparent":
        parts.append(f'<rect x="0" y="0" width="{total_width:.3f}" height="{total_height:.3f}" fill="{xml.sax.saxutils.escape(background)}"/>')
    x = padding
    for column, column_width in zip(columns, column_widths):
        parts.extend(_column_svg(column, x=x, y=padding, width=column_width, title_height=title_height, row_gap=row_gap))
        x += column_width + column_gap
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _column_svg(column: list[_SvgFragment], *, x: float, y: float, width: float, title_height: float, row_gap: float) -> list[str]:
    parts: list[str] = []
    cursor = y
    for fragment in column:
        title = xml.sax.saxutils.escape(fragment.title)
        display_width, display_height = _display_size(fragment)
        image_x = x + (width - display_width) / 2
        parts.append(f'<text class="review-title" x="{x:.3f}" y="{cursor + 20:.3f}">{title}</text>')
        cursor += title_height
        payload = base64.b64encode(fragment.svg_text.encode("utf-8")).decode("ascii")
        href = f"data:image/svg+xml;base64,{payload}"
        parts.append(f'<image x="{image_x:.3f}" y="{cursor:.3f}" width="{display_width:.3f}" height="{display_height:.3f}" href="{href}" xlink:href="{href}"/>')
        cursor += display_height + row_gap
    return parts


def _column_height(column: list[_SvgFragment], *, title_height: float, row_gap: float) -> float:
    return sum(title_height + _display_size(fragment)[1] for fragment in column) + row_gap * max(0, len(column) - 1)


def _display_size(fragment: _SvgFragment) -> tuple[float, float]:
    if fragment.width <= REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH:
        return fragment.width, fragment.height
    scale = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH / fragment.width
    return REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH, fragment.height * scale


def _viewbox_size(svg_text: str) -> tuple[float, float]:
    match = re.search(r'viewBox="[-0-9.]+ [-0-9.]+ ([0-9.]+) ([0-9.]+)"', svg_text)
    if match:
        return float(match.group(1)), float(match.group(2))
    width = re.search(r'width="([0-9.]+)"', svg_text)
    height = re.search(r'height="([0-9.]+)"', svg_text)
    return float(width.group(1)) if width else 100.0, float(height.group(1)) if height else 100.0
