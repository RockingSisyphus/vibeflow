from __future__ import annotations

import re
import xml.sax.saxutils
import xml.etree.ElementTree as ET
from typing import Mapping

from vibeflow.rendering.mermaid.render import MermaidRenderError
from vibeflow.rendering.mermaid.review_types import (
    FRAGMENT_FRAME_PADDING as _FRAGMENT_FRAME_PADDING,
    REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    REVIEW_COLUMNS_STYLE as _REVIEW_COLUMNS_STYLE,
    _SvgFragment,
)

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"
_SVG_URL_REFERENCE_PATTERN = re.compile(r"""url\((?P<quote>['"]?)#(?P<id>[^'"\)\s]+)(?P=quote)\)""")
_CSS_ID_SELECTOR_PATTERN = re.compile(r"#(?P<id>[A-Za-z_][\w:.-]*)(?=[\s.\[>{+~,:])")

ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)

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
    root_id = root.attrib.get("id")
    root_id_attribute = f" id={xml.sax.saxutils.quoteattr(root_id)}" if root_id else ""
    return [f'<g class="review-inline-fragment"{root_id_attribute} transform="{transform}">{inner}</g>']

def _prefix_svg_ids(root: ET.Element, prefix: str) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for element in root.iter():
        original = element.attrib.get("id")
        if original:
            id_map[original] = f"{prefix}{original}"
    if not id_map:
        return {}
    for element in root.iter():
        if "id" in element.attrib:
            element.attrib["id"] = id_map[element.attrib["id"]]
        for key, value in list(element.attrib.items()):
            element.attrib[key] = _rewrite_svg_reference(value, id_map)
        if element.text:
            element.text = _rewrite_svg_reference(element.text, id_map)
    return id_map

def _rewrite_svg_reference(value: str, id_map: Mapping[str, str]) -> str:
    if "#" not in value:
        return value
    if value.startswith("#") and value[1:] in id_map:
        return f"#{id_map[value[1:]]}"

    def replace_url(match: re.Match[str]) -> str:
        new = id_map.get(match.group("id"))
        if not new:
            return match.group(0)
        return f"url(#{new})"

    rewritten = _SVG_URL_REFERENCE_PATTERN.sub(replace_url, value)
    return _rewrite_css_id_selectors(rewritten, id_map)

def _rewrite_css_id_selectors(value: str, id_map: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        new = id_map.get(match.group("id"))
        if not new:
            return match.group(0)
        index = match.start() - 1
        while index >= 0 and value[index].isspace():
            index -= 1
        if index >= 0 and value[index] not in "{},>+~":
            return match.group(0)
        return f"#{new}"

    return _CSS_ID_SELECTOR_PATTERN.sub(replace, value)

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
