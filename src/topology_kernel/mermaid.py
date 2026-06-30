from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any, Mapping

from .compiler import CompiledGraph
from .flowchart_render_helpers import compile_for_render, node_flow_kind, node_is_external, nodeset_for_node, shorten
from .graph_config import GraphConfig, NodeSpec, NodesetSpec, STATUS_PLANNED
from .node import FLOW_KIND_DATA_STORE, FLOW_KIND_DECISION, FLOW_KIND_DOCUMENT, FLOW_KIND_IO, FLOW_KIND_PREDEFINED, FLOW_KIND_PREPARATION, FLOW_KIND_PROCESS, FLOW_KIND_TERMINAL

if TYPE_CHECKING:
    from .registry import NodeRegistry


def export_mermaid(
    graph: GraphConfig,
    *,
    expand_nodesets: bool = False,
    compiled: CompiledGraph | None = None,
    registry: NodeRegistry | None = None,
    health_report: object | None = None,
    show_contract: bool = True,
    show_semantics: bool = True,
    show_findings: bool = True,
) -> str:
    actual_compiled = compile_for_render(graph, compiled, registry)
    renderer = _MermaidRenderer(
        expand_nodesets=expand_nodesets,
        registry=registry,
        health_report=health_report,
        show_contract=show_contract,
        show_semantics=show_semantics,
        show_findings=show_findings,
    )
    return renderer.render(graph, actual_compiled)


def compiled_graph_payload(graph: GraphConfig, compiled: CompiledGraph) -> dict[str, object]:
    return {
        "nodes": [
            {
                "name": node.name,
                "type": node.node_type,
                "requires": list(node.requires),
                "provides": list(node.provides),
                "status": node.status,
                "flow_kind": node_flow_kind(node, compiled),
            }
            for node in graph.nodes
        ],
        "explicit_edges": [list(edge.pair) for edge in compiled.explicit_edges],
        "data_edges": [list(edge.pair) for edge in compiled.data_edges],
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
        "providers": dict(compiled.providers),
        "consumers": {key: list(values) for key, values in compiled.consumers.items()},
        "nodesets": sorted(graph.nodesets),
    }


class _MermaidRenderer:
    def __init__(
        self,
        *,
        expand_nodesets: bool,
        registry: NodeRegistry | None,
        health_report: object | None,
        show_contract: bool,
        show_semantics: bool,
        show_findings: bool,
    ) -> None:
        self.expand_nodesets = expand_nodesets
        self.registry = registry
        self.health_report = health_report
        self.show_contract = show_contract
        self.show_semantics = show_semantics
        self.show_findings = show_findings
        self.node_ids: dict[str, str] = {}
        self.nodeset_node_ids: dict[str, str] = {}
        self.node_classes: dict[str, str] = {}

    def render(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        self.node_ids = {node.name: _safe_id(node.name) for node in graph.nodes}
        self.nodeset_node_ids = _nodeset_node_ids(graph, self.node_ids)
        self.node_classes = self._finding_classes(graph, compiled) if self.show_findings else {}
        lines = [
            "flowchart TD",
            "  classDef healthError fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;",
            "  classDef healthWarning fill:#fef3c7,stroke:#d97706,color:#78350f;",
            "  classDef externalDependency fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;",
            "  classDef documentNode fill:#f0fdf4,stroke:#16a34a,color:#14532d;",
            "  classDef nodesetNode fill:#ede9fe,stroke:#7c3aed,color:#3b0764;",
            "  classDef plannedNode fill:#fef08a,stroke:#ca8a04,stroke-width:3px,stroke-dasharray: 6 3,color:#713f12;",
        ]
        self._render_graph_body(lines, graph, compiled, prefix="", indent="  ", visited_nodesets=())
        self._render_edges(lines, compiled, prefix="", indent="  ")
        if self.show_findings:
            self._render_findings(lines, graph, compiled, indent="  ")
        return "\n".join(lines) + "\n"

    def _render_graph_body(
        self,
        lines: list[str],
        graph: GraphConfig,
        compiled: CompiledGraph,
        *,
        prefix: str,
        indent: str,
        visited_nodesets: tuple[str, ...],
    ) -> None:
        for node in graph.nodes:
            node_id = _safe_id(f"{prefix}{node.name}")
            nodeset = nodeset_for_node(graph, node)
            if nodeset is None:
                flow_kind = node_flow_kind(node, compiled) or FLOW_KIND_PROCESS
                preferred_class = "externalDependency" if self._node_is_external(node) else ""
                class_name = self._class_for_node(node_id, preferred_class=preferred_class, planned=node.status == STATUS_PLANNED)
                lines.append(f"{indent}{_node_shape(node_id, self._node_label(node), flow_kind)}")
                if class_name:
                    lines.append(f"{indent}class {node_id} {class_name};")
                continue
            flow_kind = node_flow_kind(node, compiled) or nodeset.flow_kind
            class_name = self._class_for_node(node_id, preferred_class="nodesetNode", planned=node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED)
            lines.append(f"{indent}{_node_shape(node_id, self._nodeset_label(node, nodeset), flow_kind)}")
            if class_name:
                lines.append(f"{indent}class {node_id} {class_name};")
            if not self.expand_nodesets:
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
                )
                self._render_edges(lines, nested_compiled, prefix=nested_prefix, indent=f"{indent}  ")
            lines.append(f"{indent}end")

    def _render_edges(self, lines: list[str], compiled: CompiledGraph, *, prefix: str, indent: str) -> None:
        for edge in compiled.effective_edges:
            source_id = _safe_id(f"{prefix}{edge.source}")
            target_id = _safe_id(f"{prefix}{edge.target}")
            label = f"|{_escape_label(edge.when)}|" if edge.when else ""
            lines.append(f"{indent}{source_id} -->{label} {target_id}")

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
        if planned:
            return "plannedNode"
        return self.node_classes.get(node_id) or preferred_class

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
        lines = [node.name, node.node_type]
        if node.status == STATUS_PLANNED:
            lines.append("planned")
        if self.show_semantics:
            lines.extend(self._node_semantic_lines(node))
        if self.show_contract:
            lines.extend((_key_line("requires", node.requires), _key_line("provides", node.provides)))
        return _join_label_lines(lines)

    def _nodeset_label(self, node: NodeSpec, nodeset: NodesetSpec) -> str:
        lines = [node.name, node.node_type]
        if node.status == STATUS_PLANNED or nodeset.status == STATUS_PLANNED:
            lines.append("planned")
        if self.show_semantics:
            lines.extend(
                (
                    nodeset.display_name,
                    f"category: {nodeset.category}",
                    f"version: {nodeset.version}",
                    nodeset.description,
                )
            )
        if self.show_contract:
            lines.extend(
                (
                    _key_line("requires", nodeset.requires or node.requires),
                    _key_line("provides", nodeset.provides or node.provides),
                    _key_line("exports", nodeset.exports),
                )
            )
        return _join_label_lines(lines)

    def _node_semantic_lines(self, node: NodeSpec) -> tuple[str, ...]:
        lines: list[str] = []
        if self.registry is not None and node.status != STATUS_PLANNED and not node.node_type.startswith("nodeset."):
            try:
                node_cls = self.registry.get(node.node_type)
            except Exception:
                node_cls = None
            info = getattr(node_cls, "NODE_INFO", None) if node_cls is not None else None
            if info is not None:
                lines.extend(
                    str(value)
                    for value in (
                        getattr(info, "display_name", ""),
                        f"category: {getattr(info, 'category', '')}",
                        f"version: {getattr(info, 'version', '')}",
                        getattr(info, "description", ""),
                    )
                    if str(value).strip()
                )
                if getattr(info, "external", False):
                    lines.append("external: true")
        lines.extend(_node_param_semantic_lines(node))
        return tuple(lines)


def _nodeset_node_ids(graph: GraphConfig, node_ids: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in graph.nodes:
        nodeset = nodeset_for_node(graph, node)
        if nodeset is not None:
            result[nodeset.name] = node_ids[node.name]
    return result


def _node_param_semantic_lines(node: NodeSpec) -> tuple[str, ...]:
    lines: list[str] = []
    for key in ("display_name", "category", "version", "description"):
        value = node.params.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key}: {value.strip()}" if key != "description" else value.strip())
    return tuple(lines)


def _node_shape(node_id: str, label: str, flow_kind: object) -> str:
    escaped = _escape_label(label)
    kind = str(flow_kind)
    shape = {
        FLOW_KIND_TERMINAL: "stadium",
        FLOW_KIND_PROCESS: "rect",
        FLOW_KIND_DECISION: "diam",
        FLOW_KIND_IO: "lean-r",
        FLOW_KIND_PREDEFINED: "fr-rect",
        FLOW_KIND_DATA_STORE: "cyl",
        FLOW_KIND_DOCUMENT: "doc",
        FLOW_KIND_PREPARATION: "hex",
    }.get(kind, "rect")
    return f'{node_id}@{{ shape: {shape}, label: "{escaped}" }}'


def _key_line(label: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
    return f"{label}: {', '.join(values)}"


def _join_label_lines(lines: tuple[str, ...] | list[str]) -> str:
    return "\n".join(shorten(line) for line in lines if str(line).strip())


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', "'")


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
