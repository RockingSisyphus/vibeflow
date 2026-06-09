from __future__ import annotations

from typing import Any, Mapping

from .compiler import CompiledGraph, GraphCompiler
from .graph_config import GraphConfig, NodeSpec, NodesetSpec


def export_mermaid(
    graph: GraphConfig,
    *,
    expand_nodesets: bool = False,
    compiled: CompiledGraph | None = None,
    health_report: object | None = None,
    show_contract: bool = True,
    show_semantics: bool = True,
    show_boundary: bool = True,
    show_findings: bool = True,
) -> str:
    actual_compiled = compiled or GraphCompiler().compile(graph)
    renderer = _MermaidRenderer(
        expand_nodesets=expand_nodesets,
        health_report=health_report,
        show_contract=show_contract,
        show_semantics=show_semantics,
        show_boundary=show_boundary,
        show_findings=show_findings,
    )
    return renderer.render(graph, actual_compiled)


def compiled_graph_payload(graph: GraphConfig, compiled: CompiledGraph) -> dict[str, object]:
    return {
        "nodes": [{"name": node.name, "type": node.node_type, "requires": list(node.requires), "provides": list(node.provides)} for node in graph.nodes],
        "explicit_edges": [list(edge.pair) for edge in compiled.explicit_edges],
        "data_edges": [list(edge.pair) for edge in compiled.data_edges],
        "effective_edges": [
            {"from": edge.source, "to": edge.target, "max_executions": edge.max_executions, "loop": edge.loop}
            for edge in compiled.effective_edges
        ],
        "edge_execution_limits": {f"{source}->{target}": limit for (source, target), limit in compiled.edge_execution_limits.items()},
        "loops": [
            {
                "name": loop.name,
                "edges": [list(edge) for edge in loop.edges],
                "max_iterations": loop.max_iterations,
                "until": loop.until,
                "order": list(compiled.loop_orders.get(loop.name, ())),
            }
            for loop in graph.loops
        ],
        "providers": dict(compiled.providers),
        "consumers": {key: list(values) for key, values in compiled.consumers.items()},
        "nodesets": sorted(graph.nodesets),
    }


class _MermaidRenderer:
    def __init__(
        self,
        *,
        expand_nodesets: bool,
        health_report: object | None,
        show_contract: bool,
        show_semantics: bool,
        show_boundary: bool,
        show_findings: bool,
    ) -> None:
        self.expand_nodesets = expand_nodesets
        self.health_report = health_report
        self.show_contract = show_contract
        self.show_semantics = show_semantics
        self.show_boundary = show_boundary
        self.show_findings = show_findings
        self.node_ids: dict[str, str] = {}
        self.nodeset_node_ids: dict[str, str] = {}

    def render(self, graph: GraphConfig, compiled: CompiledGraph) -> str:
        self.node_ids = {node.name: _safe_id(node.name) for node in graph.nodes}
        self.nodeset_node_ids = _nodeset_node_ids(graph, self.node_ids)
        lines = [
            "flowchart TD",
            "  classDef healthError fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;",
            "  classDef healthWarning fill:#fef3c7,stroke:#d97706,color:#78350f;",
            "  classDef boundaryNode fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;",
            "  classDef nodesetNode fill:#ede9fe,stroke:#7c3aed,color:#3b0764;",
        ]
        self._render_graph_body(lines, graph, compiled, prefix="", indent="  ", visited_nodesets=())
        if self.show_boundary:
            self._render_boundary(lines, graph, compiled, indent="  ")
        self._render_edges(lines, compiled, prefix="", indent="  ")
        self._render_loop_summaries(lines, compiled, indent="  ")
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
            nodeset = _nodeset_for_node(graph, node)
            if nodeset is None:
                lines.append(f'{indent}{node_id}["{_escape_label(self._node_label(node))}"]')
                continue
            lines.append(f'{indent}{node_id}["{_escape_label(self._nodeset_label(node, nodeset))}"]')
            lines.append(f"{indent}class {node_id} nodesetNode;")
            if not self.expand_nodesets:
                continue
            group_id = _safe_id(f"{prefix}{node.name}__expanded")
            lines.append(f'{indent}subgraph {group_id}["{_escape_label(nodeset.name)}"]')
            if nodeset.name in visited_nodesets:
                lines.append(f"{indent}  %% recursive nodeset expansion skipped: {nodeset.name}")
            else:
                nested_compiled = GraphCompiler().compile(nodeset.graph)
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
                self._render_loop_summaries(lines, nested_compiled, indent=f"{indent}  ")
            lines.append(f"{indent}end")

    def _render_edges(self, lines: list[str], compiled: CompiledGraph, *, prefix: str, indent: str) -> None:
        for edge in compiled.effective_edges:
            label_parts = [f"max={edge.max_executions}"]
            if edge.loop:
                label_parts.insert(0, f"loop {edge.loop}")
            source_id = _safe_id(f"{prefix}{edge.source}")
            target_id = _safe_id(f"{prefix}{edge.target}")
            lines.append(f"{indent}{source_id} -->|{' '.join(label_parts)}| {target_id}")

    def _render_loop_summaries(self, lines: list[str], compiled: CompiledGraph, *, indent: str) -> None:
        for loop in compiled.loops:
            edges = ", ".join(f"{source}->{target}" for source, target in loop.edges)
            until = f"; until={loop.until}" if loop.until else ""
            lines.append(f"{indent}%% loop {loop.name}: max_iterations={loop.max_iterations}; edges={edges}{until}")

    def _render_boundary(self, lines: list[str], graph: GraphConfig, compiled: CompiledGraph, *, indent: str) -> None:
        boundary = graph.boundary
        if boundary is None:
            return
        boundary_id = "__boundary__"
        label = [
            "boundary",
            boundary.boundary_type,
            _key_line("consumes", boundary.consumes),
            _key_line("provides", boundary.provides),
        ]
        lines.append(f'{indent}{boundary_id}["{_escape_label(_join_label_lines(label))}"]')
        lines.append(f"{indent}class {boundary_id} boundaryNode;")
        for key in boundary.consumes:
            source = compiled.providers.get(key)
            if source:
                lines.append(f"{indent}{_safe_id(source)} -.->|{_escape_label(key)}| {boundary_id}")
        for key in boundary.provides:
            for target in compiled.consumers.get(key, ()):
                lines.append(f"{indent}{boundary_id} -.->|{_escape_label(key)}| {_safe_id(target)}")

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
                lines.append(f"{indent}class {target_id} {class_name};")

    def _finding_targets(self, graph: GraphConfig, compiled: CompiledGraph, *, object_type: str, object_id: str) -> tuple[str, ...]:
        if object_type == "node" and object_id in self.node_ids:
            return (self.node_ids[object_id],)
        if object_type == "nodeset":
            target = self.nodeset_node_ids.get(object_id)
            return (target,) if target else ()
        if object_type == "boundary" or object_id == "boundary":
            return ("__boundary__",) if graph.boundary is not None else ()
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
        if self.show_semantics:
            lines.extend(_node_semantic_lines(node))
        if self.show_contract:
            lines.extend((_key_line("requires", node.requires), _key_line("provides", node.provides)))
        return _join_label_lines(lines)

    def _nodeset_label(self, node: NodeSpec, nodeset: NodesetSpec) -> str:
        lines = [node.name, node.node_type]
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


def _nodeset_for_node(graph: GraphConfig, node: NodeSpec) -> NodesetSpec | None:
    if not node.node_type.startswith("nodeset."):
        return None
    return graph.nodesets.get(node.node_type.removeprefix("nodeset."))


def _nodeset_node_ids(graph: GraphConfig, node_ids: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in graph.nodes:
        nodeset = _nodeset_for_node(graph, node)
        if nodeset is not None:
            result[nodeset.name] = node_ids[node.name]
    return result


def _node_semantic_lines(node: NodeSpec) -> tuple[str, ...]:
    lines: list[str] = []
    for key in ("display_name", "category", "version", "description"):
        value = node.params.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{key}: {value.strip()}" if key != "description" else value.strip())
    return tuple(lines)


def _key_line(label: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
    return f"{label}: {', '.join(values)}"


def _join_label_lines(lines: tuple[str, ...] | list[str]) -> str:
    return "\n".join(_shorten(line) for line in lines if str(line).strip())


def _shorten(value: object, *, limit: int = 120) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', "'")


def _comment_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in value)
    if not cleaned:
        return "node"
    if cleaned[0].isdigit():
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
