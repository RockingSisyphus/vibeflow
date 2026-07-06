from __future__ import annotations

import re
import tempfile
import xml.sax.saxutils
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping

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
from .mermaid_render import DEFAULT_MERMAID_MAX_EDGES, DEFAULT_MERMAID_MAX_TEXT_SIZE

from . import mermaid_review_fragments as _review_fragments
from .mermaid_review_fragments import _compose_detail_panel_svg, _nodeset_fragments, _nodeset_mermaid, _resource_mermaid
from .mermaid_review_layout import _compose_svg, _validate_review_fragment_max_width
from .mermaid_review_types import REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH, _SvgFragment
from .visual_style import MERMAID_RESOURCE_CLASS_ORDER, mermaid_class_def_lines


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
_SVG_URL_REFERENCE_PATTERN = re.compile(r"url\((?P<quote>['\"]?)#(?P<id>[^'\"\)\s]+)(?P=quote)\)")
_CSS_ID_SELECTOR_PATTERN = re.compile(r"#(?P<id>[A-Za-z_][\w:.-]*)(?=[\s.\[>{+~,:])")

ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)


_DEFAULT_RENDER_FRAGMENT = _review_fragments._render_fragment


def _render_fragment(*args, **kwargs):
    return _DEFAULT_RENDER_FRAGMENT(*args, **kwargs)


_RENDER_FRAGMENT_WRAPPER = _render_fragment


def _render_nodeset_detail_fragment(*args, **kwargs):
    current_render_fragment = globals()["_render_fragment"]
    delegate = _DEFAULT_RENDER_FRAGMENT if current_render_fragment is _RENDER_FRAGMENT_WRAPPER else current_render_fragment
    original = _review_fragments._render_fragment
    _review_fragments._render_fragment = delegate
    try:
        return _review_fragments._render_nodeset_detail_fragment(*args, **kwargs)
    finally:
        _review_fragments._render_fragment = original


def render_review_columns_svg(
    graph: GraphConfig,
    compiled: object,
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
    compiled: object,
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
