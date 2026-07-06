from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from typing import Any, Mapping

from .compiler import CompiledGraph
from .data_contract import providers_to_dicts, requirements_to_dicts
from .flowchart_render_helpers import compile_for_render, node_flow_kind, node_is_external, nodeset_for_node

from .mermaid_labels import (
    _comment_text,
    _edge_contract_text,
    _edge_style,
    _escape_edge_label,
    _escape_label,
    _expanded_nodeset_title,
    _health_findings,
    _join_label_lines,
    _join_label_sections,
    _loop_stop_text,
    _mapping_items,
    _node_metadata_lines,
    _node_shape,
    _nodeset_node_ids,
    _resource_label,
    _resources_payload,
    _safe_id,
    _section_label,
)
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
                "id": node.id,
                "type_used": node.type_used,
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
        "mainline_edges": [list(edge.pair) for edge in compiled.mainline_edges],
        "data_bypass_edges": [list(edge.pair) for edge in compiled.data_bypass_edges],
        "async_edges": [list(edge.pair) for edge in compiled.async_edges],
        "schedule_edges": [list(edge.pair) for edge in compiled.schedule_edges],
        "transfer_edges": [list(edge.pair) for edge in compiled.transfer_edges],
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
        self.edge_index = 0

    def render(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        self.node_ids = {node.id: _safe_id(node.id) for node in graph.nodes}
        self.nodeset_node_ids = _nodeset_node_ids(graph, self.node_ids)
        self.node_classes = self._finding_classes(graph, compiled) if self.show_findings else {}
        self.edge_index = 0
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
            node_id = _safe_id(f"{prefix}{node.id}")
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
            is_loop = node.type_used in LOOP_NODE_TYPES
            class_name = self._class_for_node(node_id, preferred_class="loopNode" if is_loop else "nodesetNode", planned=node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED)
            label = self._loop_label(node, nodeset) if is_loop else self._nodeset_label(node, nodeset)
            lines.append(f"{indent}{_node_shape(node_id, label, flow_kind, shape='trap-b' if is_loop else '')}")
            if class_name:
                lines.append(f"{indent}class {node_id} {class_name};")
            self._render_custom_node_style(lines, node, node_id, indent=indent)
            if not should_expand:
                continue
            group_id = _safe_id(f"{prefix}{node.id}__expanded")
            group_title = _expanded_nodeset_title(node, nodeset)
            lines.append(f'{indent}subgraph {group_id}["{_escape_label(group_title)}"]')
            if nodeset.type_key in visited_nodesets:
                lines.append(f"{indent}  %% recursive nodeset expansion skipped: {nodeset.type_key}")
            else:
                nested_compiled = compile_for_render(nodeset.graph, None, self.registry)
                nested_prefix = f"{prefix}{node.id}__"
                self._render_graph_body(
                    lines,
                    nodeset.graph,
                    nested_compiled,
                    prefix=nested_prefix,
                    indent=f"{indent}  ",
                    visited_nodesets=(*visited_nodesets, nodeset.type_key),
                    expand_inline=True,
                )
                self._render_edges(lines, nodeset.graph, nested_compiled, prefix=nested_prefix, indent=f"{indent}  ")
            lines.append(f"{indent}end")

    def _render_edges(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, prefix: str, indent: str) -> None:
        for edge in compiled.effective_edges:
            source_id = _safe_id(f"{prefix}{edge.source}")
            target_id = _safe_id(f"{prefix}{edge.target}")
            label_text = self._edge_label(graph, edge)
            label = f'|"{_escape_edge_label(label_text)}"|' if label_text else ""
            self._append_edge_line(lines, f"{indent}{source_id} -->{label} {target_id}", style=_edge_style(compiled, edge))

    def _append_edge_line(self, lines: list[str], line: str, *, style: str = "") -> None:
        edge_index = self.edge_index
        lines.append(line)
        self.edge_index += 1
        if style:
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(f"{indent}linkStyle {edge_index} {style};")

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
            self._append_edge_line(lines, f"{indent}{root_id} -.-> {resource_id}")
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
        sections: list[list[str]] = [[self._node_title(node)], [f"id: {node.id}", f"type_used: {node.type_used}"]]
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
        title = node.metadata.display_name or nodeset.display_name or node.id
        sections: list[list[str]] = [[title], [f"id: {node.id}", f"type_used: {node.type_used}"]]
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
                    f"type_key: {nodeset.type_key}",
                    f"desc: {nodeset.description}",
                ]
            )
        return _join_label_sections(sections)

    def _loop_label(self, node: NodeSpec, nodeset: NodesetSpec) -> str:
        title = node.metadata.display_name or nodeset.display_name or node.id
        sections: list[list[str]] = [[title], [f"id: {node.id}", f"type_used: {node.type_used}"]]
        spec = node.loop
        loop_lines = [_section_label("loop"), f"body: {nodeset.type_key}", f"stop: {_loop_stop_text(spec)}", f"max: {spec.max_iterations}"]
        sections.append(loop_lines)
        if self.show_semantics:
            call_lines = _node_metadata_lines(node)
            if call_lines:
                sections.append([_section_label("meta"), *call_lines])
        return _join_label_sections(sections)

    def _node_title(self, node: NodeSpec) -> str:
        if node.metadata.display_name:
            return node.metadata.display_name
        if self.registry is not None and node.status != STATUS_PLANNED:
            try:
                node_cls = self.registry.get(node.type_used)
            except Exception:
                node_cls = None
            info = getattr(node_cls, "NODE_INFO", None) if node_cls is not None else None
            display_name = str(getattr(info, "display_name", "")).strip() if info is not None else ""
            if display_name:
                return display_name
        return node.id

    def _edge_label(self, graph: GraphConfig, edge: object) -> str:
        when = str(getattr(edge, "when", "")).strip()
        data_text = _edge_contract_text(graph, edge) if self.show_contract else ""
        sections: list[list[str]] = []
        if when:
            sections.append([_section_label("when"), f"when: {when}"])
        if data_text:
            sections.append([_section_label("data"), f"data: {data_text}"])
        return _join_label_sections(sections)

    def _node_semantic_lines(self, node: NodeSpec) -> tuple[str, ...]:
        lines = list(_node_metadata_lines(node))
        if self.registry is not None and node.status != STATUS_PLANNED:
            try:
                node_cls = self.registry.get(node.type_used)
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
