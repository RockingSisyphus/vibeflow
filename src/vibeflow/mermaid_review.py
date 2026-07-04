from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .compiler import CompiledGraph
from .flowchart_render_helpers import compile_for_render, nodeset_for_node
from .graph_config import GraphConfig
from .visual_style import MERMAID_MAIN_CLASS_ORDER, mermaid_class_def_lines


@dataclass(frozen=True)
class _ResourceColumnSpec:
    column_id: str
    title: str
    root_id: str
    root_label: str
    root_class: str
    child_class: str
    child_shape: str
    label_kind: str


_PLUGIN_COLUMN = _ResourceColumnSpec(
    column_id="__vibeflow_layout_plugins",
    title="plugins",
    root_id="resource_plugins",
    root_label="plugins",
    root_class="pluginResource",
    child_class="pluginResource",
    child_shape="hex",
    label_kind="plugin",
)
_BASE_LIB_COLUMN = _ResourceColumnSpec(
    column_id="__vibeflow_layout_base_lib",
    title="base_lib",
    root_id="resource_base_lib",
    root_label="base_lib",
    root_class="baseLibResource",
    child_class="baseLibResource",
    child_shape="fr-rect",
    label_kind="base_lib",
)


def render_review_columns(renderer: Any, graph: GraphConfig, compiled: CompiledGraph) -> str:
    lines = [
        "flowchart LR",
        *(f"  {line}" for line in mermaid_class_def_lines(MERMAID_MAIN_CLASS_ORDER)),
        "  classDef layoutAnchor fill:transparent,stroke:transparent,color:transparent;",
    ]
    column_anchors = _render_main_column(renderer, lines, graph, compiled)
    column_anchors.extend(_render_resource_columns(renderer, lines))
    nodeset_anchor = _render_nodesets_column(renderer, lines, graph)
    if nodeset_anchor:
        column_anchors.append(nodeset_anchor)
    for source, target in zip(column_anchors, column_anchors[1:]):
        lines.append(f"  {source} ~~~ {target}")
    if renderer.show_findings:
        renderer._render_findings(lines, graph, compiled, indent="  ")
    return "\n".join(lines) + "\n"


def _render_main_column(renderer: Any, lines: list[str], graph: GraphConfig, compiled: CompiledGraph) -> list[str]:
    anchor = "__vibeflow_layout_main_anchor"
    lines.append('  subgraph __vibeflow_layout_main["main pipeline"]')
    lines.append("    direction TB")
    _render_anchor(lines, anchor, indent="    ")
    renderer._render_graph_body(lines, graph, compiled, prefix="", indent="    ", visited_nodesets=(), expand_inline=False)
    renderer._render_edges(lines, compiled, prefix="", indent="    ")
    if graph.nodes:
        lines.append(f"    {anchor} ~~~ {_safe_id(graph.nodes[0].name)}")
    lines.append("  end")
    return [anchor]


def _render_resource_columns(renderer: Any, lines: list[str]) -> list[str]:
    payload = _resources_payload(renderer.resources)
    if not payload:
        return []
    anchors: list[str] = []
    plugin_anchor = _render_resource_column(renderer, lines, _PLUGIN_COLUMN, _mapping_items(payload.get("plugins", ())))
    if plugin_anchor:
        anchors.append(plugin_anchor)
    base_lib_payload = payload.get("base_lib", {})
    modules = base_lib_payload.get("modules", ()) if isinstance(base_lib_payload, Mapping) else ()
    base_lib_anchor = _render_resource_column(renderer, lines, _BASE_LIB_COLUMN, _mapping_items(modules))
    if base_lib_anchor:
        anchors.append(base_lib_anchor)
    return anchors


def _render_resource_column(renderer: Any, lines: list[str], spec: _ResourceColumnSpec, resources: tuple[Mapping[str, object], ...]) -> str:
    if not resources:
        return ""
    anchor = f"{spec.column_id}_anchor"
    lines.append(f'  subgraph {spec.column_id}["{_escape_label(spec.title)}"]')
    lines.append("    direction TB")
    _render_anchor(lines, anchor, indent="    ")
    renderer._render_resource_group(
        lines,
        root_id=spec.root_id,
        root_label=spec.root_label,
        root_class=spec.root_class,
        child_class=spec.child_class,
        child_shape=spec.child_shape,
        resources=resources,
        label_kind=spec.label_kind,
        indent="    ",
    )
    lines.append(f"    {anchor} ~~~ {spec.root_id}")
    lines.append("  end")
    return anchor


def _render_nodesets_column(renderer: Any, lines: list[str], graph: GraphConfig) -> str:
    if not renderer.expand_nodesets:
        return ""
    nodeset_nodes = [(node, nodeset_for_node(graph, node)) for node in graph.nodes]
    nodeset_nodes = [(node, nodeset) for node, nodeset in nodeset_nodes if nodeset is not None]
    if not nodeset_nodes:
        return ""
    column_anchor = "__vibeflow_layout_nodesets_anchor"
    lines.append('  subgraph __vibeflow_layout_nodesets["expanded nodesets"]')
    lines.append("    direction TB")
    _render_anchor(lines, column_anchor, indent="    ")
    previous_anchor = column_anchor
    for node, nodeset in nodeset_nodes:
        if nodeset is None:
            continue
        group_anchor = _render_one_nodeset(renderer, lines, node, nodeset)
        lines.append(f"    {previous_anchor} ~~~ {group_anchor}")
        previous_anchor = group_anchor
    lines.append("  end")
    return column_anchor


def _render_one_nodeset(renderer: Any, lines: list[str], node: Any, nodeset: Any) -> str:
    group_id = _safe_id(f"__vibeflow_layout_nodesets__{node.name}__expanded")
    group_anchor = _safe_id(f"{group_id}__anchor")
    lines.append(f'    subgraph {group_id}["{_escape_label(f"{node.name} - {nodeset.name}")}"]')
    lines.append("      direction LR")
    _render_anchor(lines, group_anchor, indent="      ")
    nested_compiled = compile_for_render(nodeset.graph, None, renderer.registry)
    nested_prefix = f"__vibeflow_layout_nodesets__{node.name}__"
    renderer._render_graph_body(
        lines,
        nodeset.graph,
        nested_compiled,
        prefix=nested_prefix,
        indent="      ",
        visited_nodesets=(nodeset.name,),
        expand_inline=True,
    )
    renderer._render_edges(lines, nested_compiled, prefix=nested_prefix, indent="      ")
    if nodeset.graph.nodes:
        lines.append(f"      {group_anchor} ~~~ {_safe_id(f'{nested_prefix}{nodeset.graph.nodes[0].name}')}")
    lines.append("    end")
    return group_anchor


def _render_anchor(lines: list[str], node_id: str, *, indent: str) -> None:
    lines.append(f'{indent}{node_id}@{{ shape: circle, label: "" }}')
    lines.append(f"{indent}class {node_id} layoutAnchor;")


def _resources_payload(resources: object | None) -> Mapping[str, object]:
    from .mermaid import _resources_payload as impl

    return impl(resources)


def _mapping_items(value: object) -> tuple[Mapping[str, object], ...]:
    from .mermaid import _mapping_items as impl

    return impl(value)


def _escape_label(value: str) -> str:
    from .mermaid import _escape_label as impl

    return impl(value)


def _safe_id(value: str) -> str:
    from .mermaid import _safe_id as impl

    return impl(value)
