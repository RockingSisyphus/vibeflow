from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from typing import Any, Mapping

from .compiler import CompiledGraph
from .data_contract import providers_to_dicts, requirements_to_dicts
from .flowchart_render_helpers import compile_for_render, node_flow_kind, node_is_external, nodeset_for_node
from .graph_config import GraphConfig, LOOP_NODE_TYPES, NodeSpec, NodesetSpec, STATUS_PLANNED
from .node import FLOW_KIND_DATA_STORE, FLOW_KIND_DECISION, FLOW_KIND_DOCUMENT, FLOW_KIND_IO, FLOW_KIND_PREDEFINED, FLOW_KIND_PREPARATION, FLOW_KIND_PROCESS, FLOW_KIND_TERMINAL
from .planned_behavior import effective_planned_behavior, planned_behavior_label
from .runtime_helpers import has_planned, planned_items
from .visual_style import MERMAID_MAIN_CLASS_ORDER, mermaid_class_def_lines

if TYPE_CHECKING:
    from .registry import NodeRegistry


MERMAID_LAYOUT_DEFAULT = "default"
MERMAID_LAYOUT_REVIEW_COLUMNS = "review-columns"
_MERMAID_LAYOUTS = {MERMAID_LAYOUT_DEFAULT, MERMAID_LAYOUT_REVIEW_COLUMNS}
_SECTION_SEPARATOR_WIDTH = 10


def export_mermaid(
    graph: GraphConfig,
    *,
    expand_nodesets: bool = False,
    compiled: CompiledGraph | None = None,
    registry: NodeRegistry | None = None,
    health_report: object | None = None,
    resources: object | None = None,
    show_contract: bool = True,
    show_semantics: bool = True,
    show_findings: bool = True,
    mermaid_layout: str = MERMAID_LAYOUT_DEFAULT,
) -> str:
    actual_compiled = compile_for_render(graph, compiled, registry)
    renderer = _MermaidRenderer(
        expand_nodesets=expand_nodesets,
        registry=registry,
        health_report=health_report,
        resources=resources,
        show_contract=show_contract,
        show_semantics=show_semantics,
        show_findings=show_findings,
        mermaid_layout=mermaid_layout,
    )
    return renderer.render(graph, actual_compiled)


def compiled_graph_payload(graph: GraphConfig, compiled: CompiledGraph, *, resources: object | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "nodes": [
            {
                "name": node.name,
                "type": node.node_type,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "status": node.status,
                "planned_behavior": node.planned_behavior.to_dict(),
                "flow_kind": node_flow_kind(node, compiled),
                "metadata": node.metadata.to_dict(),
                "style": node.style.to_dict(),
                "similar_to": node.similar_to.to_dict(),
            }
            for node in graph.nodes
        ],
        "explicit_edges": [list(edge.pair) for edge in compiled.explicit_edges],
        "data_edges": [list(edge.pair) for edge in compiled.data_edges],
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
        "providers": dict(compiled.providers),
        "consumers": {key: list(values) for key, values in compiled.consumers.items()},
        "nodesets": sorted(graph.nodesets),
        "planned": [dict(item) for item in planned_items(graph)],
        "production_ready": not has_planned(graph),
    }
    resource_payload = _resources_payload(resources)
    if resource_payload:
        payload["resources"] = resource_payload
    return payload


class _MermaidRenderer:
    def __init__(
        self,
        *,
        expand_nodesets: bool,
        registry: NodeRegistry | None,
        health_report: object | None,
        resources: object | None,
        show_contract: bool,
        show_semantics: bool,
        show_findings: bool,
        mermaid_layout: str,
    ) -> None:
        if mermaid_layout not in _MERMAID_LAYOUTS:
            raise ValueError(f"unknown Mermaid layout: {mermaid_layout}")
        self.expand_nodesets = expand_nodesets
        self.registry = registry
        self.health_report = health_report
        self.resources = resources
        self.show_contract = show_contract
        self.show_semantics = show_semantics
        self.show_findings = show_findings
        self.mermaid_layout = mermaid_layout
        self.node_ids: dict[str, str] = {}
        self.nodeset_node_ids: dict[str, str] = {}
        self.node_classes: dict[str, str] = {}

    def render(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        self.node_ids = {node.name: _safe_id(node.name) for node in graph.nodes}
        self.nodeset_node_ids = _nodeset_node_ids(graph, self.node_ids)
        self.node_classes = self._finding_classes(graph, compiled) if self.show_findings else {}
        if self.mermaid_layout == MERMAID_LAYOUT_REVIEW_COLUMNS:
            return self._render_review_columns(graph, compiled)
        lines = [
            "flowchart TD",
            *(f"  {line}" for line in mermaid_class_def_lines(MERMAID_MAIN_CLASS_ORDER)),
        ]
        self._render_graph_body(lines, graph, compiled, prefix="", indent="  ", visited_nodesets=())
        self._render_edges(lines, graph, compiled, prefix="", indent="  ")
        self._render_resources(lines, indent="  ")
        if self.show_findings:
            self._render_findings(lines, graph, compiled, indent="  ")
        return "\n".join(lines) + "\n"

    def _render_review_columns(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        from .mermaid_review import render_review_columns

        return render_review_columns(self, graph, compiled)

    def _render_graph_body(
        self,
        lines: list[str],
        graph: GraphConfig,
        compiled: CompiledGraph,
        *,
        prefix: str,
        indent: str,
        visited_nodesets: tuple[str, ...],
        expand_inline: bool | None = None,
    ) -> None:
        should_expand = self.expand_nodesets if expand_inline is None else expand_inline
        for node in graph.nodes:
            node_id = _safe_id(f"{prefix}{node.name}")
            nodeset = nodeset_for_node(graph, node)
            if nodeset is None:
                flow_kind = node_flow_kind(node, compiled) or FLOW_KIND_PROCESS
                preferred_class = self._preferred_class_for_node(node, flow_kind=flow_kind)
                class_name = self._class_for_node(node_id, preferred_class=preferred_class, planned=node.status == STATUS_PLANNED)
                lines.append(f"{indent}{_node_shape(node_id, self._node_label(node), flow_kind)}")
                if class_name:
                    lines.append(f"{indent}class {node_id} {class_name};")
                self._render_custom_node_style(lines, node, node_id, indent=indent)
                continue
            flow_kind = node_flow_kind(node, compiled) or nodeset.flow_kind
            is_loop = node.node_type in LOOP_NODE_TYPES
            class_name = self._class_for_node(node_id, preferred_class="loopNode" if is_loop else "nodesetNode", planned=node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED)
            label = self._loop_label(node, nodeset) if is_loop else self._nodeset_label(node, nodeset)
            lines.append(f"{indent}{_node_shape(node_id, label, flow_kind, shape='trap-b' if is_loop else '')}")
            if class_name:
                lines.append(f"{indent}class {node_id} {class_name};")
            self._render_custom_node_style(lines, node, node_id, indent=indent)
            if not should_expand:
                continue
            group_id = _safe_id(f"{prefix}{node.name}__expanded")
            lines.append(f'{indent}subgraph {group_id}["{_escape_label(nodeset.name)}"]')
            if nodeset.name in visited_nodesets:
                lines.append(f"{indent}  %% recursive nodeset expansion skipped: {nodeset.name}")
            else:
                nested_compiled = compile_for_render(nodeset.graph, None, self.registry)
                nested_prefix = f"{prefix}{node.name}__"
                self._render_graph_body(
                    lines,
                    nodeset.graph,
                    nested_compiled,
                    prefix=nested_prefix,
                    indent=f"{indent}  ",
                    visited_nodesets=(*visited_nodesets, nodeset.name),
                    expand_inline=True,
                )
                self._render_edges(lines, nodeset.graph, nested_compiled, prefix=nested_prefix, indent=f"{indent}  ")
            lines.append(f"{indent}end")

    def _render_edges(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, prefix: str, indent: str) -> None:
        for edge in compiled.effective_edges:
            source_id = _safe_id(f"{prefix}{edge.source}")
            target_id = _safe_id(f"{prefix}{edge.target}")
            label_text = self._edge_label(graph, edge)
            label = f"|{_escape_edge_label(label_text)}|" if label_text else ""
            lines.append(f"{indent}{source_id} -->{label} {target_id}")

    def _render_resources(self, lines: list[str], *, indent: str) -> None:
        payload = _resources_payload(self.resources)
        if not payload:
            return
        base_lib = payload.get("base_lib", {})
        if isinstance(base_lib, Mapping):
            modules = _mapping_items(base_lib.get("modules", ()))
            self._render_resource_group(
                lines,
                root_id="resource_base_lib",
                root_label="base_lib",
                root_class="baseLibResource",
                child_class="baseLibResource",
                child_shape="fr-rect",
                resources=modules,
                label_kind="base_lib",
                indent=indent,
            )
        plugins = _mapping_items(payload.get("plugins", ()))
        self._render_resource_group(
            lines,
            root_id="resource_plugins",
            root_label="plugins",
            root_class="pluginResource",
            child_class="pluginResource",
            child_shape="hex",
            resources=plugins,
            label_kind="plugin",
            indent=indent,
        )

    def _render_resource_group(
        self,
        lines: list[str],
        *,
        root_id: str,
        root_label: str,
        root_class: str,
        child_class: str,
        child_shape: str,
        resources: tuple[Mapping[str, object], ...],
        label_kind: str,
        indent: str,
    ) -> None:
        if not resources:
            return
        lines.append(f'{indent}{root_id}@{{ shape: hex, label: "{_escape_label(root_label)}" }}')
        lines.append(f"{indent}class {root_id} {root_class};")
        for index, resource in enumerate(resources):
            resource_id = f"{root_id}_{index}"
            label = _resource_label(resource, kind=label_kind, show_semantics=self.show_semantics)
            lines.append(f'{indent}{resource_id}@{{ shape: {child_shape}, label: "{_escape_label(label)}" }}')
            lines.append(f"{indent}{root_id} -.-> {resource_id}")
            status = str(resource.get("status", "implemented"))
            lines.append(f"{indent}class {resource_id} {'plannedResource' if status == STATUS_PLANNED else child_class};")

    def _render_findings(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, indent: str) -> None:
        for finding in _health_findings(self.health_report):
            severity = str(finding.get("severity", "error"))
            rule_id = str(finding.get("rule_id", ""))
            object_type = str(finding.get("object_type", ""))
            object_id = str(finding.get("object_id", ""))
            message = str(finding.get("message", ""))
            lines.append(f"{indent}%% finding {severity} {rule_id} {object_type}:{object_id} {_comment_text(message)}")
            class_name = "healthWarning" if severity == "warning" else "healthError"
            for target_id in self._finding_targets(graph, compiled, object_type=object_type, object_id=object_id):
                self.node_classes.setdefault(target_id, class_name)

    def _finding_classes(self, graph: GraphConfig, compiled: CompiledGraph) -> dict[str, str]:
        classes: dict[str, str] = {}
        for finding in _health_findings(self.health_report):
            severity = str(finding.get("severity", "error"))
            object_type = str(finding.get("object_type", ""))
            object_id = str(finding.get("object_id", ""))
            class_name = "healthWarning" if severity == "warning" else "healthError"
            for target_id in self._finding_targets(graph, compiled, object_type=object_type, object_id=object_id):
                if classes.get(target_id) != "healthError":
                    classes[target_id] = class_name
        return classes

    def _class_for_node(self, node_id: str, *, preferred_class: str = "", planned: bool = False) -> str:
        finding_class = self.node_classes.get(node_id)
        if finding_class:
            return finding_class
        if planned:
            return "plannedNode"
        return preferred_class or "defaultNode"

    def _preferred_class_for_node(self, node: NodeSpec, *, flow_kind: str) -> str:
        if self._node_is_external(node):
            return "externalDependency"
        if flow_kind == FLOW_KIND_DOCUMENT:
            return "documentNode"
        return "defaultNode"

    def _render_custom_node_style(self, lines: list[str], node: NodeSpec, node_id: str, *, indent: str) -> None:
        style = node.style.to_dict()
        if not style:
            return
        fields: list[str] = []
        if "fill" in style:
            fields.append(f"fill:{style['fill']}")
        if "stroke" in style:
            fields.append(f"stroke:{style['stroke']}")
        if "text" in style:
            fields.append(f"color:{style['text']}")
        if fields:
            lines.append(f"{indent}style {node_id} {','.join(fields)};")

    def _node_is_external(self, node: NodeSpec) -> bool:
        return node_is_external(node, self.registry)

    def _finding_targets(self, graph: GraphConfig, compiled: CompiledGraph, *, object_type: str, object_id: str) -> tuple[str, ...]:
        if object_type == "node" and object_id in self.node_ids:
            return (self.node_ids[object_id],)
        if object_type == "nodeset":
            target = self.nodeset_node_ids.get(object_id)
            return (target,) if target else ()
        if object_type == "contract_key":
            targets: list[str] = []
            provider = compiled.providers.get(object_id)
            if provider and provider in self.node_ids:
                targets.append(self.node_ids[provider])
            for consumer in compiled.consumers.get(object_id, ()):
                if consumer in self.node_ids:
                    targets.append(self.node_ids[consumer])
            return tuple(dict.fromkeys(targets))
        return ()

    def _node_label(self, node: NodeSpec) -> str:
        sections: list[list[str]] = [[self._node_title(node)], [f"id: {node.name}", f"type: {node.node_type}"]]
        if node.status == STATUS_PLANNED:
            planned_lines = [_section_label("status"), f"status: {planned_behavior_label(node.planned_behavior)}"]
            if node.planned_behavior.stub_module:
                planned_lines.append(f"stub: {node.planned_behavior.stub_module}")
            sections.append(planned_lines)
        if self.show_semantics:
            semantic_lines = self._node_semantic_lines(node)
            if semantic_lines:
                sections.append([_section_label("meta"), *semantic_lines])
        return _join_label_sections(sections)

    def _nodeset_label(self, node: NodeSpec, nodeset: NodesetSpec) -> str:
        title = node.metadata.display_name or nodeset.display_name or node.name
        sections: list[list[str]] = [[title], [f"id: {node.name}", f"type: {node.node_type}"]]
        if node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED:
            behavior = effective_planned_behavior(node, nodeset)
            planned_lines = [_section_label("status"), f"status: {planned_behavior_label(behavior)}"]
            if behavior.stub_module:
                planned_lines.append(f"stub: {behavior.stub_module}")
            sections.append(planned_lines)
        if self.show_semantics:
            call_lines = _node_metadata_lines(node)
            if call_lines:
                sections.append([_section_label("call"), *call_lines])
            sections.append(
                [
                    _section_label("nodeset"),
                    f"nodeset: {nodeset.name}",
                    f"category: {nodeset.category}",
                    f"version: {nodeset.version}",
                    f"desc: {nodeset.description}",
                ]
            )
        return _join_label_sections(sections)

    def _loop_label(self, node: NodeSpec, nodeset: NodesetSpec) -> str:
        title = node.metadata.display_name or node.name
        sections: list[list[str]] = [[title], [f"id: {node.name}", f"type: {node.node_type}"]]
        spec = node.loop
        loop_lines = [_section_label("loop"), f"body: {nodeset.name}", f"stop: {_loop_stop_text(spec)}", f"max: {spec.max_iterations}"]
        sections.append(loop_lines)
        if self.show_semantics:
            call_lines = _node_metadata_lines(node)
            if call_lines:
                sections.append([_section_label("meta"), *call_lines])
        return _join_label_sections(sections)

    def _node_title(self, node: NodeSpec) -> str:
        if node.metadata.display_name:
            return node.metadata.display_name
        if self.registry is not None and node.status != STATUS_PLANNED and not node.node_type.startswith("nodeset."):
            try:
                node_cls = self.registry.get(node.node_type)
            except Exception:
                node_cls = None
            info = getattr(node_cls, "NODE_INFO", None) if node_cls is not None else None
            display_name = str(getattr(info, "display_name", "")).strip() if info is not None else ""
            if display_name:
                return display_name
        return node.name

    def _edge_label(self, graph: GraphConfig, edge: object) -> str:
        when = str(getattr(edge, "when", "")).strip()
        data_text = _edge_contract_text(graph, edge) if self.show_contract else ""
        if when and data_text:
            return f"when: {when}\ndata: {data_text}"
        return when or data_text

    def _node_semantic_lines(self, node: NodeSpec) -> tuple[str, ...]:
        lines = list(_node_metadata_lines(node))
        if self.registry is not None and node.status != STATUS_PLANNED and not node.node_type.startswith("nodeset."):
            try:
                node_cls = self.registry.get(node.node_type)
            except Exception:
                node_cls = None
            info = getattr(node_cls, "NODE_INFO", None) if node_cls is not None else None
            if info is not None and not lines:
                for label, value in (
                    ("category", getattr(info, "category", "")),
                    ("version", getattr(info, "version", "")),
                    ("desc", getattr(info, "description", "")),
                ):
                    text = str(value).strip()
                    if text:
                        lines.append(f"{label}: {text}")
            if info is not None and getattr(info, "external", False):
                lines.append("external: true")
        return tuple(lines)


def _nodeset_node_ids(graph: GraphConfig, node_ids: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is not None:
            result[nodeset.name] = node_ids[node.name]
    return result


def _node_metadata_lines(node: NodeSpec) -> tuple[str, ...]:
    lines: list[str] = []
    metadata = node.metadata
    if metadata.category:
        lines.append(f"category: {metadata.category}")
    if metadata.version:
        lines.append(f"version: {metadata.version}")
    if metadata.description:
        lines.append(f"desc: {metadata.description}")
    return tuple(lines)


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
    if resources is None:
        return {}
    if hasattr(resources, "to_dict") and callable(getattr(resources, "to_dict")):
        payload = resources.to_dict()
    else:
        payload = resources
    return payload if isinstance(payload, Mapping) else {}


def _mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


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
    source_name = str(getattr(edge, "source", ""))
    target_name = str(getattr(edge, "target", ""))
    nodes = {node.name: node for node in graph.nodes}
    source = nodes.get(source_name)
    target = nodes.get(target_name)
    if source is None or target is None:
        return ""
    required_types = {requirement.type for requirement in target.requires}
    if not required_types:
        return ""
    items = [_provider_edge_text(provider) for provider in source.provides if provider.type in required_types]
    if not items:
        return ""
    visible = items[:max_items]
    if len(items) > max_items:
        visible.append(f"+{len(items) - max_items} more")
    return ", ".join(visible)


def _provider_edge_text(provider: object) -> str:
    key = str(getattr(provider, "key", "")).strip()
    data_type = str(getattr(provider, "type", "")).strip()
    if key and data_type and key != data_type:
        return f"{key} -> {data_type}"
    return data_type or key


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
