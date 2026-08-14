from __future__ import annotations

from dataclasses import dataclass
from html import escape as escape_xml
from pathlib import Path
import re
import tempfile
from typing import Mapping

from vibeflow.core.constants import FLOW_KIND_DOCUMENT, FLOW_KIND_GLOBAL_STATE
from vibeflow.core.flow import GraphConfig, LOOP_NODE_TYPES, NodeSpec, NodesetSpec, STATUS_PLANNED
from vibeflow.core.planned import effective_planned_behavior, planned_behavior_label
from vibeflow.tooling.application.mermaid_shapes import mermaid_shape_for_flow_kind
from vibeflow.tooling.presentation.mermaid import (
    DEFAULT_MERMAID_MAX_EDGES,
    DEFAULT_MERMAID_MAX_TEXT_SIZE,
    EXPANDED_MERMAID_MAX_EDGES,
    EXPANDED_MERMAID_MAX_TEXT_SIZE,
    render_mermaid_svg,
)
from vibeflow.tooling.presentation.style import MERMAID_MAIN_CLASS_ORDER, mermaid_class_def_lines
from vibeflow.tooling.presentation.review_layout import (
    _compose_svg,
    _validate_review_fragment_max_width,
    _viewbox_size,
)
from vibeflow.tooling.presentation.review_types import (
    REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    SvgFragment,
)


ReviewCoverage = tuple[str, str, str]


@dataclass(frozen=True)
class _InvocationGroup:
    kind: str
    target: str
    nodeset: NodesetSpec
    nodes: tuple[NodeSpec, ...]


def render_mermaid(
    result: object,
    *,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
    mermaid_layout: str = "default",
) -> str:
    graph = result.graph
    text = _graph_mermaid(
        result,
        graph,
        result.compiled,
        direction="TD",
        show_contract=show_contract,
        show_semantics=show_semantics,
    )
    if not expand_nodesets:
        return text
    sections = [text.rstrip()]
    for group in _invocation_groups(graph):
        sections.append(
            f"%% expanded {group.kind}: {group.target}\n"
            + _graph_mermaid(
                result,
                group.nodeset.graph,
                result.compiled_nodesets[group.target],
                direction="LR",
                show_contract=show_contract,
                show_semantics=show_semantics,
            ).rstrip()
        )
    return "\n\n".join(sections) + "\n"


def render_ascii(
    result: object,
    *,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
) -> str:
    lines: list[str] = []

    def append_graph(graph: GraphConfig, compiled: object, *, title: str, indent: str) -> None:
        lines.append(f"{indent}{title} ({graph.entry_mode})")
        incoming = {node.id: [] for node in graph.nodes}
        for edge in compiled.effective_edges:
            incoming.setdefault(edge.target, []).append(edge.source)
        for node in graph.nodes:
            parents = ", ".join(sorted(incoming.get(node.id, ()))) or "entry"
            semantics = ""
            if show_semantics:
                flow_kind = compiled.flow_kinds.get(node.id, node.flow_kind)
                semantics = (
                    f" flow_kind={flow_kind or 'process'}"
                    f" effect_scope={_effect_scope(compiled, node.id, flow_kind)}"
                    f" runtime_dispatch={_runtime_dispatch(compiled, node.id)}"
                )
            lines.append(
                f"{indent}- {node.id} [{node.type_used}] <- {parents}{semantics}"
            )
        if expand_nodesets:
            for group in _invocation_groups(graph):
                append_graph(
                    group.nodeset.graph,
                    result.compiled_nodesets[group.target],
                    title=f"{group.kind} {group.target}",
                    indent=indent + "  ",
                )

    append_graph(result.graph, result.compiled, title=f"workflow {result.plan.workflow_id}", indent="")
    return "\n".join(lines) + "\n"


def write_review_svg(
    result: object,
    output: Path,
    *,
    expand_nodesets: bool,
    show_contract: bool = True,
    show_semantics: bool = True,
    theme: str = "default",
    background: str = "transparent",
    max_text_size: int | None = None,
    max_edges: int | None = None,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    mermaid_layout: str = "default",
) -> frozenset[ReviewCoverage]:
    actual_width = _validate_review_fragment_max_width(review_fragment_max_width)
    actual_text_size = max_text_size or (
        EXPANDED_MERMAID_MAX_TEXT_SIZE if expand_nodesets else DEFAULT_MERMAID_MAX_TEXT_SIZE
    )
    actual_edges = max_edges or (
        EXPANDED_MERMAID_MAX_EDGES if expand_nodesets else DEFAULT_MERMAID_MAX_EDGES
    )
    if not expand_nodesets and mermaid_layout == "default":
        output.parent.mkdir(parents=True, exist_ok=True)
        render_mermaid_svg(
            _graph_mermaid(
                result,
                result.graph,
                result.compiled,
                direction="TD",
                show_contract=show_contract,
                show_semantics=show_semantics,
            ),
            output,
            theme=theme,
            background=background,
            max_text_size=actual_text_size,
            max_edges=actual_edges,
        )
        return frozenset()
    coverage: set[ReviewCoverage] = set()
    with tempfile.TemporaryDirectory(prefix="vibeflow-javascript-review-") as raw:
        temp_dir = Path(raw)
        root_target = result.graph.root_id or result.root.id
        main = _render_fragment(
            "main pipeline",
            _graph_mermaid(
                result,
                result.graph,
                result.compiled,
                direction="TD",
                show_contract=show_contract,
                show_semantics=show_semantics,
            ),
            temp_dir,
            kind="workflow",
            owner="",
            target=root_target,
            theme=theme,
            background=background,
            max_text_size=actual_text_size,
            max_edges=actual_edges,
        )
        coverage.add(("workflow", "", root_target))
        columns: list[list[SvgFragment]] = [[main]]
        for resource_kind, records in _resource_records(result):
            if not records:
                continue
            fragment = _render_fragment(
                resource_kind,
                _resource_mermaid(resource_kind, records),
                temp_dir,
                kind="resource",
                owner="workflow",
                target=resource_kind,
                theme=theme,
                background=background,
                max_text_size=actual_text_size,
                max_edges=actual_edges,
            )
            columns.append([fragment])
            coverage.add(("resource", "workflow", resource_kind))
        if expand_nodesets:
            details: list[SvgFragment] = []
            for group in _invocation_groups(result.graph):
                details.append(
                    _render_group_fragment(
                        result,
                        group,
                        temp_dir,
                        owner="workflow",
                        theme=theme,
                        background=background,
                        show_contract=show_contract,
                        show_semantics=show_semantics,
                        max_text_size=actual_text_size,
                        max_edges=actual_edges,
                        review_fragment_max_width=actual_width,
                        coverage=coverage,
                        visited=(),
                    )
                )
            if details:
                columns.append(details)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            _compose_svg(
                columns,
                background=background,
                review_fragment_max_width=actual_width,
            ),
            encoding="utf-8",
        )
    return frozenset(coverage)


def render_review_svg(result: object) -> str:
    with tempfile.TemporaryDirectory(prefix="vibeflow-javascript-svg-") as raw:
        output = Path(raw) / "review.svg"
        write_review_svg(
            result,
            output,
            expand_nodesets=True,
            mermaid_layout="review-columns",
        )
        return output.read_text(encoding="utf-8")


def expected_review_coverage(result: object) -> frozenset[ReviewCoverage]:
    expected: set[ReviewCoverage] = set()
    root_target = result.graph.root_id or result.root.id
    expected.add(("workflow", "", root_target))
    for resource_kind, records in _resource_records(result):
        if records:
            expected.add(("resource", "workflow", resource_kind))

    def visit(graph: GraphConfig, *, owner: str, visited: tuple[str, ...]) -> None:
        for group in _invocation_groups(graph):
            key = (group.kind, owner, group.target)
            expected.add(key)
            if group.target in visited:
                continue
            child_owner = f"{owner}/{group.kind}:{group.target}"
            visit(
                group.nodeset.graph,
                owner=child_owner,
                visited=(*visited, group.target),
            )

    visit(result.graph, owner="workflow", visited=())
    return frozenset(expected)


def _render_group_fragment(
    result: object,
    group: _InvocationGroup,
    temp_dir: Path,
    *,
    owner: str,
    theme: str,
    background: str,
    show_contract: bool,
    show_semantics: bool,
    max_text_size: int,
    max_edges: int,
    review_fragment_max_width: float,
    coverage: set[ReviewCoverage],
    visited: tuple[str, ...],
) -> SvgFragment:
    coverage.add((group.kind, owner, group.target))
    title = _group_title(group)
    if group.target in visited or not group.nodeset.graph.nodes:
        mermaid = (
            "flowchart LR\n"
            f'  placeholder["{_escape_label(title)}\\n'
            f'{_escape_label("recursive expansion skipped" if group.target in visited else "nodeset has no concrete pipeline")}"]\n'
        )
        return _render_fragment(
            title,
            mermaid,
            temp_dir,
            kind=group.kind,
            owner=owner,
            target=group.target,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
        )
    compiled = result.compiled_nodesets[group.target]
    children = _invocation_groups(group.nodeset.graph)
    if not children:
        return _render_fragment(
            title,
            _graph_mermaid(
                result,
                group.nodeset.graph,
                compiled,
                direction="LR",
                show_contract=show_contract,
                show_semantics=show_semantics,
            ),
            temp_dir,
            kind=group.kind,
            owner=owner,
            target=group.target,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
        )
    parent = _render_fragment(
        "parent flow",
        _graph_mermaid(
            result,
            group.nodeset.graph,
            compiled,
            direction="TD",
            show_contract=show_contract,
            show_semantics=show_semantics,
        ),
        temp_dir,
        kind="body",
        owner=owner,
        target=group.target,
        theme=theme,
        background=background,
        max_text_size=max_text_size,
        max_edges=max_edges,
    )
    child_owner = f"{owner}/{group.kind}:{group.target}"
    child_fragments = [
        _render_group_fragment(
            result,
            child,
            temp_dir,
            owner=child_owner,
            theme=theme,
            background=background,
            show_contract=show_contract,
            show_semantics=show_semantics,
            max_text_size=max_text_size,
            max_edges=max_edges,
            review_fragment_max_width=review_fragment_max_width,
            coverage=coverage,
            visited=(*visited, group.target),
        )
        for child in children
    ]
    nested = _compose_svg(
        [[parent], child_fragments],
        background=background,
        review_fragment_max_width=review_fragment_max_width,
    )
    width, height = _viewbox_size(nested)
    return SvgFragment(
        title,
        nested,
        width,
        height,
        review_kind=group.kind,
        review_owner=owner,
        review_target=group.target,
    )


def _render_fragment(
    title: str,
    mermaid: str,
    temp_dir: Path,
    *,
    kind: str,
    owner: str,
    target: str,
    theme: str,
    background: str,
    max_text_size: int,
    max_edges: int,
) -> SvgFragment:
    path = temp_dir / f"fragment_{len(tuple(temp_dir.glob('fragment_*.svg')))}.svg"
    render_mermaid_svg(
        mermaid,
        path,
        theme=theme,
        background=background,
        max_text_size=max_text_size,
        max_edges=max_edges,
    )
    svg_text = path.read_text(encoding="utf-8")
    width, height = _viewbox_size(svg_text)
    return SvgFragment(
        title,
        svg_text,
        width,
        height,
        review_kind=kind,
        review_owner=owner,
        review_target=target,
    )


def _graph_mermaid(
    result: object,
    graph: GraphConfig,
    compiled: object,
    *,
    direction: str,
    show_contract: bool,
    show_semantics: bool,
) -> str:
    lines = [
        f"flowchart {direction}",
        *(f"  {line}" for line in mermaid_class_def_lines(MERMAID_MAIN_CLASS_ORDER)),
    ]
    for node in graph.nodes:
        descriptor = _node_descriptor(result, node)
        nodeset = _nodeset_for_node(graph, node)
        is_planned = node.status == STATUS_PLANNED or (
            nodeset is not None and nodeset.status == STATUS_PLANNED
        )
        is_external = (
            not is_planned
            and nodeset is None
            and bool(getattr(descriptor, "external", False))
        )
        display_name = (
            node.metadata.display_name
            or str(getattr(descriptor, "display_name", "") or "")
            or node.id
        )
        if is_external and not display_name.startswith("[EXTERNAL]"):
            display_name = f"[EXTERNAL] {display_name}"
        description = (
            node.metadata.description
            or str(getattr(descriptor, "description", "") or "")
        )
        flow_kind = compiled.flow_kinds.get(node.id, node.flow_kind)
        label = [display_name, "", f"id: {node.id}", f"type_used: {node.type_used}"]
        if node.type_used in LOOP_NODE_TYPES:
            label.append(f"body: {node.loop.body}")
        elif node.type_used in graph.nodesets:
            label.append(f"type_key: {node.type_used}")
        if is_planned:
            behavior = effective_planned_behavior(node, nodeset)
            label.extend(
                (
                    "",
                    "---------- status ----------",
                    f"status: {planned_behavior_label(behavior)}",
                )
            )
            if behavior.stub_module:
                label.append(f"stub: {behavior.stub_module}")
        if description:
            label.extend(("", "---------- meta ----------", f"desc: {description}"))
        if show_semantics:
            label.extend(
                (
                    f"flow_kind: {flow_kind or 'process'}",
                    f"effect_scope: {_effect_scope(compiled, node.id, flow_kind)}",
                    f"runtime_dispatch: {_runtime_dispatch(compiled, node.id)}",
                    f"execution_lock: {_lock_text(graph, node) or 'none'}",
                )
            )
            if node.async_mode:
                label.append(f"async: {node.async_mode}")
            if node.result_key:
                label.append(f"result_key: {node.result_key}")
            if is_external:
                label.append("external: true")
        escaped = _escape_label("\\n".join(label))
        shape = mermaid_shape_for_flow_kind(flow_kind or "process")
        node_id = _safe_id(node.id)
        lines.append(f'  {node_id}@{{ shape: {shape}, label: "{escaped}" }}')
        lines.append(
            f"  class {node_id} "
            f"{_node_class(node, nodeset=nodeset, flow_kind=flow_kind, is_external=is_external)};"
        )
        if is_external:
            lines.append(f"  class {node_id} externalBoundary;")
        custom_style = _custom_node_style(node)
        if custom_style:
            lines.append(f"  style {node_id} {custom_style};")
    edge_pairs = {
        name: {item.pair for item in values}
        for name, values in (
            ("mainline", compiled.mainline_edges),
            ("data_bypass", compiled.data_bypass_edges),
            ("async", compiled.async_edges),
        )
    }
    for index, edge in enumerate(compiled.effective_edges):
        pair = edge.pair
        edge_labels: list[str] = []
        if edge.when:
            edge_labels.append(edge.when)
        if show_contract:
            contract = _edge_contract_text(graph, edge)
            if contract:
                edge_labels.append(contract)
        label = (
            f'|"{_escape_label(" / ".join(edge_labels))}"|'
            if edge_labels
            else ""
        )
        lines.append(f"  {_safe_id(edge.source)} -->{label} {_safe_id(edge.target)}")
        if pair in edge_pairs["mainline"]:
            lines.append(f"  linkStyle {index} stroke-width:4px;")
        elif pair in edge_pairs["data_bypass"]:
            lines.append(f"  linkStyle {index} stroke-dasharray:6 4,stroke-width:2px;")
        elif pair in edge_pairs["async"]:
            lines.append(f"  linkStyle {index} stroke-dasharray:3 3;")
    return "\n".join(lines) + "\n"


def _node_descriptor(result: object, node: NodeSpec) -> object | None:
    catalogs = getattr(result, "catalogs", None)
    nodes = getattr(catalogs, "nodes", None)
    get_descriptor = getattr(nodes, "get", None)
    if not callable(get_descriptor):
        return None
    return get_descriptor(node.type_used)


def _nodeset_for_node(graph: GraphConfig, node: NodeSpec) -> NodesetSpec | None:
    if node.type_used in LOOP_NODE_TYPES:
        return graph.nodesets.get(node.loop.body)
    return graph.nodesets.get(node.type_used)


def _node_class(
    node: NodeSpec,
    *,
    nodeset: NodesetSpec | None,
    flow_kind: str,
    is_external: bool,
) -> str:
    if node.status == STATUS_PLANNED or (
        nodeset is not None and nodeset.status == STATUS_PLANNED
    ):
        return "plannedNode"
    if is_external:
        return "externalDependency"
    if node.type_used in LOOP_NODE_TYPES:
        return "loopNode"
    if nodeset is not None:
        return "nodesetNode"
    if flow_kind == FLOW_KIND_DOCUMENT:
        return "documentNode"
    return "defaultNode"


def _custom_node_style(node: NodeSpec) -> str:
    style = node.style.to_dict()
    fields: list[str] = []
    if "fill" in style:
        fields.append(f"fill:{style['fill']}")
    if "stroke" in style:
        fields.append(f"stroke:{style['stroke']}")
    if "text" in style:
        fields.append(f"color:{style['text']}")
    return ",".join(fields)


def _invocation_groups(graph: GraphConfig) -> tuple[_InvocationGroup, ...]:
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[NodeSpec]] = {}
    nodesets: dict[tuple[str, str], NodesetSpec] = {}
    for node in graph.nodes:
        kind = ""
        target = ""
        if node.type_used in LOOP_NODE_TYPES and node.loop.body:
            kind, target = "loop_body", node.loop.body
        elif node.type_used in graph.nodesets:
            kind, target = "nodeset", node.type_used
        nodeset = graph.nodesets.get(target)
        if nodeset is None:
            continue
        key = (kind, target)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
            nodesets[key] = nodeset
        grouped[key].append(node)
    return tuple(
        _InvocationGroup(kind, target, nodesets[(kind, target)], tuple(grouped[(kind, target)]))
        for kind, target in order
    )


def _group_title(group: _InvocationGroup) -> str:
    title = group.nodeset.display_name or group.target
    calls = [node.id for node in group.nodes[:3]]
    if len(group.nodes) > 3:
        calls.append(f"+{len(group.nodes) - 3}")
    return f"{title} (calls: {len(group.nodes)} [{', '.join(calls)}], type_key: {group.target})"


def _resource_records(result: object) -> tuple[tuple[str, tuple[Mapping[str, object], ...]], ...]:
    resources = result.architecture.get("resources", {})
    base_lib = resources.get("base_lib", {}) if isinstance(resources, Mapping) else {}
    capabilities = resources.get("capabilities", {}) if isinstance(resources, Mapping) else {}
    base_records = _mapping_records(base_lib)
    capability_records = _mapping_records(capabilities)
    return (
        ("plugins", tuple(result.plugin_records)),
        ("base_lib", base_records),
        ("capabilities", capability_records),
        ("host_extensions", tuple(result.host_records)),
    )


def _mapping_records(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Mapping):
        return ()
    return tuple(
        dict(record) if isinstance(record, Mapping) else {"id": str(key)}
        for key, record in sorted(value.items(), key=lambda item: str(item[0]))
    )


def _edge_contract_text(graph: GraphConfig, edge: object, *, max_items: int = 2) -> str:
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get(str(getattr(edge, "source", "")))
    target = nodes.get(str(getattr(edge, "target", "")))
    if source is None or target is None:
        return ""
    required_types = {requirement.type for requirement in target.requires}
    items = [
        _provider_edge_text(provider)
        for provider in source.provides
        if provider.type in required_types
    ]
    if len(items) > max_items:
        items = [*items[:max_items], f"+{len(items) - max_items} more"]
    return ", ".join(items)


def _provider_edge_text(provider: object) -> str:
    key = str(getattr(provider, "key", "")).strip()
    data_type = str(getattr(provider, "type", "")).strip()
    display_name = str(getattr(provider, "display_name", "")).strip()
    identity = (
        f"{key} to {data_type}"
        if key and data_type and key != data_type
        else data_type or key
    )
    if display_name and identity:
        return f"{display_name} (id: {identity})"
    return display_name or identity


def _resource_mermaid(kind: str, records: tuple[Mapping[str, object], ...]) -> str:
    root = _safe_id(f"resource_{kind}")
    lines = ["flowchart LR", f'  {root}@{{ shape: hex, label: "{_escape_label(kind)}" }}']
    for index, record in enumerate(records):
        resource_id = f"{root}_{index}"
        identifier = str(record.get("id") or record.get("module") or f"{kind}_{index}")
        status = str(record.get("status", "implemented"))
        display_name = str(record.get("display_name", "") or identifier)
        label = f"{display_name}\\nid: {identifier}\\nstatus: {status}"
        lines.append(f'  {resource_id}@{{ shape: hex, label: "{_escape_label(label)}" }}')
        lines.append(f"  {root} -.-> {resource_id}")
    return "\n".join(lines) + "\n"


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return f"vf_{normalized or 'item'}"


def _escape_label(value: str) -> str:
    return value.replace('"', "'").replace("<", "&lt;").replace(">", "&gt;")


def _runtime_dispatch(compiled: object, node_id: str) -> str:
    value = getattr(compiled, "runtime_dispatches", {}).get(node_id)
    return "detected" if value is True else "none" if value is False else "unknown"


def _effect_scope(compiled: object, node_id: str, flow_kind: str) -> str:
    return getattr(compiled, "effect_scopes", {}).get(
        node_id,
        "global_state" if flow_kind == FLOW_KIND_GLOBAL_STATE else "none",
    )


def _lock_text(graph: GraphConfig, node: NodeSpec) -> str:
    if node.execution_lock is not None:
        scope = "block" if node.type_used in LOOP_NODE_TYPES or node.type_used in graph.nodesets else "node"
        return f"{node.execution_lock.key} ({scope})"
    if graph.execution_lock is not None:
        return f"{graph.execution_lock.key} (root, inherited)"
    return ""


__all__ = [
    "ReviewCoverage",
    "expected_review_coverage",
    "render_ascii",
    "render_mermaid",
    "render_review_svg",
    "write_review_svg",
]
