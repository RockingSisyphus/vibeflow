from __future__ import annotations

import textwrap
from typing import Any, Mapping

from vibeflow.rendering.helpers import nodeset_for_node
from vibeflow.rendering.review_model import (
    display_source_path,
    edge_roles,
    edge_transfers,
    mapping_items,
    rendered_resources_payload,
    resources_payload,
)
from vibeflow.graph_config import GraphConfig, NodeSpec, NodesetSpec
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

_SECTION_SEPARATOR_WIDTH = 10

def _nodeset_node_ids(graph: GraphConfig, node_ids: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is not None:
            result[nodeset.type_key] = node_ids[node.id]
    return result

def _expanded_nodeset_title(node: NodeSpec, nodeset: NodesetSpec) -> str:
    title = node.metadata.display_name or nodeset.display_name or node.id or nodeset.type_key
    return f"{title} (id: {node.id}, type_key: {nodeset.type_key})"

def _node_metadata_lines(node: NodeSpec) -> tuple[str, ...]:
    lines: list[str] = []
    metadata = node.metadata
    if metadata.description:
        lines.append(f"desc: {metadata.description}")
    return tuple(lines)

def _source_lines(root_id: object = "", root_path: object = "", source_path: object = "") -> tuple[str, ...]:
    lines: list[str] = []
    root_id_text = str(root_id or "").strip()
    root_path_text = str(root_path or "").strip()
    source_path_text = str(source_path or "").strip()
    if root_id_text:
        lines.append(f"root: {root_id_text}")
    elif root_path_text:
        lines.append(f"root_path: {root_path_text}")
    if source_path_text:
        lines.append(f"path: {_display_source_path(source_path_text, root_path_text)}")
    return tuple(lines)

def _display_source_path(source_path: str, root_path: str) -> str:
    return display_source_path(source_path, root_path) or source_path

def _loop_stop_text(spec: object) -> str:
    stop_after = int(getattr(spec, "stop_after", 0) or 0)
    if stop_after:
        return f"stop_after: {stop_after}"
    stop_when = getattr(spec, "stop_when", None)
    source = str(getattr(stop_when, "source", "")).strip() if stop_when is not None else ""
    if source:
        equals = str(getattr(stop_when, "equals", True)).lower()
        return f"stop_when: {source} == {equals}"
    return "unset"

def _section_label(name: str) -> str:
    border = "-" * _SECTION_SEPARATOR_WIDTH
    return f"{border} {name} {border}"

def _node_shape(node_id: str, label: str, flow_kind: object, *, shape: str = "") -> str:
    escaped = _escape_label(label)
    kind = str(flow_kind)
    actual_shape = shape or {
        FLOW_KIND_TERMINAL: "stadium",
        FLOW_KIND_PROCESS: "rect",
        FLOW_KIND_DECISION: "diam",
        FLOW_KIND_IO: "lean-r",
        FLOW_KIND_PREDEFINED: "fr-rect",
        FLOW_KIND_DATA_STORE: "cyl",
        FLOW_KIND_DOCUMENT: "doc",
        FLOW_KIND_PREPARATION: "hex",
    }.get(kind, "rect")
    return f'{node_id}@{{ shape: {actual_shape}, label: "{escaped}" }}'

def _resources_payload(resources: object | None) -> Mapping[str, object]:
    return resources_payload(resources)

def _rendered_resources_payload(resources: object | None, graph: GraphConfig | None = None) -> dict[str, object]:
    return rendered_resources_payload(resources, graph)

def _mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    return mapping_items(value)

def _resource_label(resource: Mapping[str, object], *, kind: str, show_semantics: bool) -> str:
    info = resource.get("info", {})
    info_map = info if isinstance(info, Mapping) else {}
    module = str(resource.get("module", "")).strip()
    name = str(resource.get("name", "")).strip()
    class_name = str(resource.get("class", "")).strip()
    status = str(resource.get("status", "implemented")).strip() or "implemented"
    display_name = _resource_value(resource, info_map, "display_name") or name or module or class_name
    identity_lines: list[str] = []
    resource_id_text = name or module or class_name
    if resource_id_text:
        identity_lines.append(f"id: {resource_id_text}")
    if kind == "base_lib":
        identity_lines.append("type: base_lib")
    else:
        plugin_type = str(resource.get("type", info_map.get("type", ""))).strip()
        if plugin_type:
            identity_lines.append(f"type: {plugin_type}")
    identity_lines.append(f"status: {status}")

    source_lines: list[str] = []
    if module:
        source_lines.append(f"module: {module}")
    if kind == "plugin" and class_name:
        source_lines.append(f"class: {class_name}")
    root_id = str(resource.get("root_id", "")).strip()
    root_path = str(resource.get("root_path", "")).strip()
    source_path = str(resource.get("source_path", "")).strip()
    if root_id:
        source_lines.append(f"root: {root_id}")
    elif root_path:
        source_lines.append(f"root_path: {root_path}")
    if source_path:
        source_lines.append(f"path: {_display_source_path(source_path, root_path)}")

    sections: list[list[str]] = [[display_name], identity_lines]
    if source_lines:
        sections.append([_section_label("resource"), *source_lines])
    if show_semantics:
        category = _resource_value(resource, info_map, "category")
        version = _resource_value(resource, info_map, "version")
        description = _resource_value(resource, info_map, "description")
        config_keys = resource.get("config_keys", ())
        meta_lines: list[str] = []
        if category:
            meta_lines.append(f"category: {category}")
        if version:
            meta_lines.append(f"version: {version}")
        if description:
            meta_lines.append(f"desc: {description}")
        if kind == "plugin" and isinstance(config_keys, list) and config_keys:
            meta_lines.append("config: " + ", ".join(str(key) for key in config_keys))
        if meta_lines:
            sections.append([_section_label("meta"), *meta_lines])
    return _join_label_sections(sections)

def _resource_value(resource: Mapping[str, object], info_map: Mapping[str, object], field: str) -> str:
    return str(resource.get(field, "")).strip() or str(info_map.get(field, "")).strip()

def _edge_contract_text(graph: GraphConfig, edge: object, *, max_items: int = 2) -> str:
    items = [_provider_edge_text(item["provider"]) for item in edge_transfers(graph, edge)]
    if not items:
        return ""
    visible = items[:max_items]
    if len(items) > max_items:
        visible.append(f"+{len(items) - max_items} more")
    return ", ".join(visible)

def _provider_edge_text(provider: object) -> str:
    if isinstance(provider, Mapping):
        key = str(provider.get("key", "")).strip()
        data_type = str(provider.get("type", "")).strip()
        display_name = str(provider.get("display_name", "")).strip()
    else:
        key = str(getattr(provider, "key", "")).strip()
        data_type = str(getattr(provider, "type", "")).strip()
        display_name = str(getattr(provider, "display_name", "")).strip()
    identity = f"{key} -> {data_type}" if key and data_type and key != data_type else (data_type or key)
    if display_name and identity:
        return f"{display_name} (id: {identity})"
    if display_name:
        return display_name
    if key and data_type and key != data_type:
        return f"{key} -> {data_type}"
    return data_type or key

def _edge_style(compiled: object, edge: object) -> str:
    roles = edge_roles(compiled, edge)
    if "data_bypass" in roles:
        return "stroke-dasharray:6 4,stroke-width:2px"
    if "mainline" in roles:
        return "stroke-width:4px"
    return ""

def _join_label_lines(lines: tuple[str, ...] | list[str]) -> str:
    out: list[str] = []
    for line in lines:
        if not str(line).strip():
            continue
        out.extend(_wrap_label_line(line))
    return "\n".join(out)

def _join_label_sections(sections: list[list[str]]) -> str:
    out: list[str] = []
    for section in sections:
        lines = _join_label_lines(section).splitlines()
        if not lines:
            continue
        if out:
            out.append("")
        out.extend(lines)
    return "\n".join(out)

def _wrap_label_line(value: object, *, width: int = 56, max_lines: int = 4) -> list[str]:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return []
    max_lines = _label_line_max_lines(text, default=max_lines)
    subsequent_indent = _label_line_indent(text)
    wrapped = textwrap.wrap(
        text,
        width=width,
        subsequent_indent=subsequent_indent,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [text]
    if len(wrapped) <= max_lines:
        return wrapped
    truncated = wrapped[:max_lines]
    truncated[-1] = truncated[-1].rstrip(". ") + "..."
    return truncated

def _label_line_indent(text: str) -> str:
    if _is_section_label(text):
        return ""
    prefix, separator, _ = text.partition(": ")
    if not separator or len(prefix) > 8:
        return ""
    return " " * (len(prefix) + len(separator))

def _label_line_max_lines(text: str, *, default: int) -> int:
    if text.startswith("desc: "):
        return 3
    if _is_section_label(text):
        return 1
    return min(default, 2)

def _is_section_label(text: str) -> bool:
    return text.startswith("-" * 4)

def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', "'")

def _escape_edge_label(value: str) -> str:
    return _escape_label(value).replace("|", "/")

def _comment_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()

def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in value)
    if not cleaned:
        return "node"
    if cleaned[0].isdigit() or cleaned.lower() in {"end", "class", "classdef", "flowchart", "graph", "subgraph"}:
        return f"n_{cleaned}"
    return cleaned

def _health_findings(report: object | None) -> tuple[Mapping[str, Any], ...]:
    if report is None:
        return ()
    payload: object
    if hasattr(report, "to_dict") and callable(getattr(report, "to_dict")):
        payload = report.to_dict()
    else:
        payload = report
    if not isinstance(payload, Mapping):
        return ()
    findings: list[Mapping[str, Any]] = []
    for key in ("errors", "warnings", "skipped"):
        items = payload.get(key, ())
        if not isinstance(items, list):
            continue
        findings.extend(item for item in items if isinstance(item, Mapping))
    return tuple(findings)
