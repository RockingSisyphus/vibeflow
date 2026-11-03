from __future__ import annotations
from vibeflow.tooling.presentation.mermaid.style import mermaid_style, mermaid_shape

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from vibeflow.core.constants import FLOW_KIND_DOCUMENT
from vibeflow.core.flow import GraphConfig, LOOP_DEFINITION_IDS, NodeCallSpec, NodesetTypeSpec, STATUS_PLANNED
from vibeflow.core.planned import effective_planned_behavior, planned_behavior_label
from vibeflow.tooling.presentation.mermaid.style import MERMAID_MAIN_CLASS_ORDER, mermaid_class_def_lines
from vibeflow.tooling.presentation.node_presentation import EffectivePresentation, resolve_presentation


@dataclass(frozen=True)
class _InvocationGroup:
    kind: str
    target: str
    nodeset: NodesetTypeSpec
    nodes: tuple[NodeCallSpec, ...]


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
    sections = [text.rstrip()]
    if mermaid_layout == "review-columns":
        sections.extend(f"%% resources: {item['title']}\n{item['mermaid'].rstrip()}"
                        for item in _resource_fragments(result))
    if not expand_nodesets:
        return "\n\n".join(sections) + "\n"
    for group in _expanded_groups(graph):
        sections.append(
            f"%% expanded {group.kind}: {group.target}\n"
            + _graph_mermaid(
                result,
                group.nodeset.graph,
                result.compiled_nodeset_types[group.target],
                direction=_body_direction(group.nodeset.graph),
                show_contract=show_contract,
                show_semantics=show_semantics,
            ).rstrip()
        )
    return "\n\n".join(sections) + "\n"


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
        node_class = _node_class(node, nodeset=nodeset, flow_kind=flow_kind, is_external=is_external)
        presentation = _node_presentation_fact(result, graph, node) or resolve_presentation(descriptor, flow_kind=flow_kind,
            native_class="externalDependency" if descriptor is not None and bool(getattr(descriptor, "external", False)) and nodeset is None else "loopNode" if node.definition_id in LOOP_DEFINITION_IDS else "nodesetNode" if nodeset is not None else "documentNode" if flow_kind == FLOW_KIND_DOCUMENT else "defaultNode",
            status_class=node_class if node_class == "plannedNode" else "", call_style=node.style, node=node, compiled=compiled)
        label = [display_name, "", f"id: {node.id}", f"definition_id: {node.definition_id}"]
        if presentation.values.get("icon"):
            label[0] = f"{presentation.values['icon']} {label[0]}"
        if descriptor is not None:
            selection = node.rulesets if node.rulesets is not None else descriptor.rulesets
            label.append(f"rulesets: {', '.join(str(getattr(ref, 'rule_id', ref)) for ref in selection) or 'unconstrained'}")
            if getattr(descriptor, "tags", ()):
                label.append(f"tags: {', '.join(descriptor.tags)}")
        if node.definition_id in LOOP_DEFINITION_IDS:
            label.append(f"body: {node.loop.body}")
        elif node.definition_id in graph.nodeset_types:
            label.append(f"type_key: {node.definition_id}")
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
                    f"effect_scope: {'unavailable' if is_planned else _effect_scope(compiled, node.id, flow_kind)}",
                    f"execution_lock: {_lock_text(graph, node) or 'none'}",
                )
            )
            if is_external:
                label.append("external: true")
        escaped = _escape_label("\\n".join(label))
        shape = mermaid_shape(presentation.shape)
        node_id = _safe_id(node.id)
        lines.append(f'  {node_id}@{{ shape: {shape}, label: "{escaped}" }}')
        lines.append(
            f"  class {node_id} "
            f"{_node_class(node, nodeset=nodeset, flow_kind=flow_kind, is_external=is_external)};"
        )
        if is_external:
            lines.append(f"  class {node_id} externalBoundary;")
        custom_style = mermaid_style(presentation)
        if custom_style:
            lines.append(f"  style {node_id} {custom_style};")
    for index, edge in enumerate(compiled.effective_edges):
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
        if edge in compiled.data_bypass_edges:
            lines.append(f"  linkStyle {index} stroke-dasharray:6 4,stroke-width:2px;")
        elif edge in compiled.mainline_edges:
            lines.append(f"  linkStyle {index} stroke-width:4px;")
    return "\n".join(lines) + "\n"


def _node_presentation_fact(result, graph, node):
    """Render the same checked presentation that the Architecture records."""
    architecture = getattr(result, "architecture", None) or {}
    document = architecture.get("workflow", {}) if graph is result.graph else next((
        architecture.get("nodeset_types", {}).get(definition.type_key, {}).get("body") or {}
        for definition in result.graph.nodeset_types.values() if definition.graph is graph), {})
    for record in document.get("nodes", ()):
        if record.get("id") == node.id and record.get("definition_id") == node.definition_id:
            presentation = record.get("presentation", {})
            values = presentation.get("values", {})
            if "shape" in values:
                return EffectivePresentation(values, presentation.get("sources", {}), presentation.get("modifiers", {}).get("planned", False))
    return None


def _node_descriptor(result: object, node: NodeCallSpec) -> object | None:
    catalogs = getattr(result, "catalogs", None)
    nodes = getattr(catalogs, "nodes", None)
    get_descriptor = getattr(nodes, "get", None)
    if not callable(get_descriptor):
        return None
    return get_descriptor(node.definition_id)


def _nodeset_for_node(graph: GraphConfig, node: NodeCallSpec) -> NodesetTypeSpec | None:
    if node.definition_id in LOOP_DEFINITION_IDS:
        return graph.nodeset_types.get(node.loop.body)
    return graph.nodeset_types.get(node.definition_id)


def _body_direction(graph: GraphConfig) -> str:
    """A folded child still makes its enclosing graph a vertical parent flow."""
    return "TD" if any(_nodeset_for_node(graph, node) is not None for node in graph.nodes) else "LR"


def _node_class(
    node: NodeCallSpec,
    *,
    nodeset: NodesetTypeSpec | None,
    flow_kind: str,
    is_external: bool,
) -> str:
    if node.status == STATUS_PLANNED or (
        nodeset is not None and nodeset.status == STATUS_PLANNED
    ):
        return "plannedNode"
    if is_external:
        return "externalDependency"
    if node.definition_id in LOOP_DEFINITION_IDS:
        return "loopNode"
    if nodeset is not None:
        return "nodesetNode"
    if flow_kind == FLOW_KIND_DOCUMENT:
        return "documentNode"
    return "defaultNode"


def _invocation_groups(graph: GraphConfig) -> tuple[_InvocationGroup, ...]:
    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[NodeCallSpec]] = {}
    nodeset_types: dict[tuple[str, str], NodesetTypeSpec] = {}
    for node in graph.nodes:
        kind = ""
        target = ""
        if node.definition_id in LOOP_DEFINITION_IDS and node.loop.body:
            kind, target = "loop_body", node.loop.body
        elif node.definition_id in graph.nodeset_types:
            kind, target = "nodeset", node.definition_id
        nodeset = graph.nodeset_types.get(target)
        if nodeset is None or not nodeset.expand:
            continue
        key = (kind, target)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
            nodeset_types[key] = nodeset
        grouped[key].append(node)
    return tuple(
        _InvocationGroup(kind, target, nodeset_types[(kind, target)], tuple(grouped[(kind, target)]))
        for kind, target in order
    )


def _expanded_groups(graph: GraphConfig, visited: tuple[str, ...] = ()):
    """Only walk visible references; source checks and execution use their own traversal."""
    for group in _invocation_groups(graph):
        yield group
        if group.target not in visited:
            yield from _expanded_groups(group.nodeset.graph, (*visited, group.target))


def _resource_fragments(result: object):
    """Show the resources of this workflow, never the implementation catalog."""
    return tuple({"id": kind, "title": kind, "mermaid": _resource_mermaid(kind, records)}
                 for kind, records in _resource_records(result) if records)


def _resource_records(result: object) -> tuple[tuple[str, tuple[Mapping[str, object], ...]], ...]:
    resources = result.architecture.get("resources", {})
    base_lib = resources.get("base_lib", {}) if isinstance(resources, Mapping) else {}
    catalogs = result.catalogs
    config = getattr(getattr(result, "document", None), "data", {})
    base_options = config.get("base_lib", {})
    base_selections = {str(item.get("id", item.get("module", ""))): item
                       for item in base_options.get("modules", ()) if isinstance(item, Mapping)} if isinstance(base_options, Mapping) else {}
    base_records = tuple({**record, **dict(base_selections.get(str(record.get("id", "")), {}))}
                         for record in _mapping_records(base_lib))
    selected_plugins = getattr(catalogs, "plugin_records", ())
    # A package can contribute many lifecycle and business resources.  It is
    # still one selected plugin in the user's workflow.
    plugin_records = tuple(selected_plugins) if selected_plugins else tuple(result.plugin_records)
    selected_records = []
    for record in plugin_records:
        declaration = dict(record.get("declaration", {}))
        lifecycle = []
        for descriptor in getattr(catalogs, "plugins", ()):
            origin = getattr(catalogs, "origins", {}).get(("plugins", descriptor.id))
            if origin and origin.owner.plugin_id == record.get("id"):
                lifecycle.append(descriptor.to_dict())
        selected_records.append({**declaration, **dict(record), "_health_status":
            _resource_health_status(result, ("plugin_declaration", "plugin"), (declaration, *lifecycle))})


    return (
        ("plugins", tuple(selected_records)),
        ("base_lib", tuple({**record, "_health_status": _resource_health_status(result, ("base_lib",), (record,))}
                           for record in base_records)),
    )


def _resource_health_status(result, kinds, records):
    """Transfer health status to selected cards without exposing source internals."""
    identities = {record.get("id") for record in records}
    paths = set()
    for record in records:
        for implementation in record.get("implementations", ()):
            for locator in (implementation.get("source", {}), *implementation.get("implementation_files", ())):
                if locator.get("kind") == "file":
                    paths.add(str((getattr(result.root, "path", Path.cwd()) / str(locator.get("ref", ""))).resolve()))
    findings = getattr(getattr(result, "rule_report", None), "findings", ())
    severities = set()
    for finding in findings:
        item = finding.to_dict() if hasattr(finding, "to_dict") else finding
        subject = item.get("object_id", item.get("subject_id"))
        if (subject in identities and item.get("object_type") in kinds or not subject
                and item.get("source_location", {}).get("path") in paths):
            severities.add(item.get("severity"))
    return "healthError" if "error" in severities else "healthWarning" if "warning" in severities else ""

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
    resource_kind = {"plugins": "plugin", "base_lib": "base_lib"}.get(kind, kind)
    for index, record in enumerate(records):
        resource_id = f"{root}_{index}"
        identifier = str(record.get("id") or record.get("module") or f"{kind}_{index}")
        status = str(record.get("status", "implemented"))
        display_name = str(record.get("display_name", "") or identifier)
        native_class = {"base_lib": "baseLibResource", "plugin": "pluginResource"}.get(resource_kind, "")
        presentation = resolve_presentation(record, resource_kind=resource_kind, native_class=native_class,
            status_class="plannedResource" if status == "planned" else record.get("_health_status", ""), call_style=record.get("style"))
        shape = mermaid_shape(presentation.shape)
        icon = str(presentation.values.get("icon", ""))
        label = f"{icon + ' ' if icon else ''}{display_name}\\nid: {identifier}\\nstatus: {status}"
        lines.append(f'  {resource_id}@{{ shape: {shape}, label: "{_escape_label(label)}" }}')
        lines.append(f"  {root} -.-> {resource_id}")
        lines.append(f"  style {resource_id} {mermaid_style(presentation)}")
    return "\n".join(lines) + "\n"


def _safe_id(value: str) -> str:
    from vibeflow.tooling.presentation.mermaid.identity import mermaid_identity
    normalized = mermaid_identity(value)
    return f"vf_{normalized or 'item'}"


def _escape_label(value: str) -> str:
    return value.replace('"', "'").replace("<", "&lt;").replace(">", "&gt;")


def _effect_scope(compiled: object, node_id: str, flow_kind: str) -> str:
    return getattr(compiled, "effect_scopes", {}).get(
        node_id,
        "unconstrained",
    )


def _lock_text(graph: GraphConfig, node: NodeCallSpec) -> str:
    if node.execution_lock is not None:
        scope = "block" if node.definition_id in LOOP_DEFINITION_IDS or node.definition_id in graph.nodeset_types else "node"
        return f"{node.execution_lock.key} ({scope})"
    if graph.execution_lock is not None:
        return f"{graph.execution_lock.key} (root, inherited)"
    return ""


__all__ = ["render_mermaid"]
