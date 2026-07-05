from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data_contract import provider_keys
from .graph_algorithms import strongly_connected_components
from .graph_config import EdgeSpec, GraphConfig, LOOP_NODE_TYPES, NodeSpec, STATUS_PLANNED
from .node import FLOW_KIND_DECISION, FLOW_KIND_PREDEFINED
from .plugin import PluginRegistry


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    explicit_edges: tuple[EdgeSpec, ...]
    data_edges: tuple[EdgeSpec, ...]
    effective_edges: tuple[EdgeSpec, ...]
    providers: dict[str, str]
    consumers: dict[str, tuple[str, ...]]
    flow_kinds: dict[str, str]


@dataclass
class GraphCompileError(ValueError):
    detail: str
    rule_id: str = "GRAPH.COMPILE"
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        return f"{self.rule_id}: Graph compile error: {self.detail}"


class GraphCompiler:
    def compile(
        self,
        graph: GraphConfig,
        *,
        registry: Any | None = None,
        known_nodesets: set[str] | None = None,
        plugin_registry: PluginRegistry | None = None,
        owner: str = "pipeline",
    ) -> CompiledGraph:
        _call_compiler_plugins(plugin_registry, "before_compile", graph)
        nodes_by_name = {node.name: node for node in graph.nodes}
        _validate_no_explicit_cycles(nodes_by_name, graph.edges, owner=owner)
        _validate_node_types(graph.nodes, registry=registry, nodesets=known_nodesets or set(graph.nodesets))
        providers = _collect_providers(graph.nodes, input_keys=set(provider_keys(graph.inputs)))
        consumers = _collect_consumers(graph.nodes)
        provider_types = {provider.key: provider.type for node in graph.nodes for provider in node.provides}
        data_edges = _derive_data_edges(graph.nodes, providers, provider_types, available_inputs=set(provider_keys(graph.inputs)))
        effective_edges = _merge_edges(graph.edges)
        flow_kinds = _node_flow_kinds(nodes_by_name, registry=registry)
        _validate_routing_edge_conditions(graph.edges, flow_kinds=flow_kinds)
        compiled = CompiledGraph(
            order=tuple(node.name for node in graph.nodes),
            explicit_edges=graph.edges,
            data_edges=data_edges,
            effective_edges=effective_edges,
            providers=providers,
            consumers=consumers,
            flow_kinds=flow_kinds,
        )
        _call_compiler_plugins(plugin_registry, "after_compile", graph, compiled)
        return compiled


def _call_compiler_plugins(plugin_registry: PluginRegistry | None, hook: str, *args) -> None:
    if plugin_registry is None:
        return
    for plugin in plugin_registry.compiler_plugins():
        method = getattr(plugin, hook, None)
        if not callable(method):
            continue
        try:
            method(*args)
        except Exception as exc:
            plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
            raise GraphCompileError(f"compiler plugin '{plugin_name}' {hook} failed: {exc}") from exc


def _validate_node_types(nodes: tuple[NodeSpec, ...], *, registry: Any | None, nodesets: set[str]) -> None:
    if registry is None:
        return
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.node_type in LOOP_NODE_TYPES:
            continue
        if node.node_type.startswith("nodeset."):
            nodeset_name = node.node_type.removeprefix("nodeset.")
            if nodeset_name not in nodesets:
                raise GraphCompileError(f"node '{node.name}' references unknown nodeset '{nodeset_name}'")
            continue
        try:
            registry.get(node.node_type)
        except Exception as exc:
            raise GraphCompileError(f"node '{node.name}' has unknown type '{node.node_type}'") from exc


def _collect_providers(nodes: tuple[NodeSpec, ...], *, input_keys: set[str] | None = None) -> dict[str, str]:
    input_keys = input_keys or set()
    providers: dict[str, str] = {}
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        for provider_spec in node.provides:
            key = provider_spec.key
            if key in input_keys:
                raise GraphCompileError(f"key '{key}' is declared by pipeline.inputs and provided by node '{node.name}'")
            if key in providers:
                raise GraphCompileError(f"key '{key}' provided by both '{providers[key]}' and '{node.name}'")
            providers[key] = node.name
    return providers


def _collect_consumers(nodes: tuple[NodeSpec, ...]) -> dict[str, tuple[str, ...]]:
    consumers: dict[str, list[str]] = {}
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        for requirement in node.requires:
            consumers.setdefault(requirement.type, []).append(node.name)
    return {key: tuple(values) for key, values in consumers.items()}


def _derive_data_edges(
    nodes: tuple[NodeSpec, ...],
    providers: dict[str, str],
    provider_types: dict[str, str],
    *,
    available_inputs: set[str],
) -> tuple[EdgeSpec, ...]:
    edges: list[EdgeSpec] = []
    for node in nodes:
        for requirement in node.requires:
            for provider_key, provider in providers.items():
                if provider_types.get(provider_key) == requirement.type and provider_key not in available_inputs and provider != node.name:
                    edges.append(EdgeSpec(source=provider, target=node.name))
    return tuple(edges)


def _merge_edges(edges: tuple[EdgeSpec, ...]) -> tuple[EdgeSpec, ...]:
    merged: dict[tuple[str, str], EdgeSpec] = {}
    for edge in edges:
        _merge_edge_into(merged, edge)
    return tuple(merged.values())


def _merge_edge_into(merged: dict[tuple[str, str], EdgeSpec], edge: EdgeSpec) -> None:
    existing = merged.get(edge.pair)
    if existing is None:
        merged[edge.pair] = edge
        return
    merged[edge.pair] = EdgeSpec(edge.source, edge.target, existing.when or edge.when)


def explicit_flow_cycles(nodes_by_name: dict[str, NodeSpec], edges: tuple[EdgeSpec, ...], *, owner: str = "pipeline") -> tuple[dict[str, object], ...]:
    adjacency: dict[str, list[str]] = {name: [] for name in nodes_by_name}
    for edge in edges:
        if edge.source in nodes_by_name and edge.target in nodes_by_name:
            adjacency.setdefault(edge.source, []).append(edge.target)
    cycles: list[dict[str, object]] = []
    for component in strongly_connected_components(adjacency):
        if len(component) == 1:
            node = component[0]
            if node not in adjacency.get(node, ()):
                continue
        members = sorted(component)
        member_set = set(component)
        cycle_edges = sorted(f"{edge.source}->{edge.target}" for edge in edges if edge.source in member_set and edge.target in member_set)
        cycles.append({"owner": owner, "members": members, "edges": cycle_edges})
    return tuple(cycles)


def _validate_no_explicit_cycles(nodes_by_name: dict[str, NodeSpec], edges: tuple[EdgeSpec, ...], *, owner: str) -> None:
    cycles = explicit_flow_cycles(nodes_by_name, edges, owner=owner)
    if not cycles:
        return
    first = cycles[0]
    members = [str(item) for item in first.get("members", ())]
    raise GraphCompileError(
        "explicit flow cycle is forbidden in ordinary graph: " + " -> ".join(members) + "; use vibeflow.loop.while for loops",
        "GRAPH.CYCLE.FORBIDDEN",
        details={
            "owner": owner,
            "members": list(first.get("members", ())),
            "edges": list(first.get("edges", ())),
            "cycles": list(cycles),
            "suggestion": "Replace ordinary edge cycles with a vibeflow.loop.while node whose body is a nodeset.",
        },
    )


def _validate_routing_edge_conditions(edges: tuple[EdgeSpec, ...], *, flow_kinds: dict[str, str]) -> None:
    if not flow_kinds:
        return
    for edge in edges:
        if flow_kinds.get(edge.source) == FLOW_KIND_DECISION and not edge.when:
            raise GraphCompileError(
                f"edge {edge.source}->{edge.target} from routing node must declare when",
                "GRAPH.DECISION.MISSING_EDGE_CONDITION",
            )


def _node_flow_kinds(nodes_by_name: dict[str, NodeSpec], *, registry: Any | None) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for name, spec in nodes_by_name.items():
        if spec.status == STATUS_PLANNED:
            kinds[name] = spec.flow_kind
            continue
        if spec.node_type in LOOP_NODE_TYPES:
            kinds[name] = FLOW_KIND_PREDEFINED
            continue
        if spec.node_type.startswith("nodeset."):
            kinds[name] = FLOW_KIND_PREDEFINED
            continue
        if registry is None:
            kinds[name] = ""
            continue
        node_cls = registry.get(spec.node_type)
        info = getattr(node_cls, "NODE_INFO", None)
        kinds[name] = str(getattr(info, "flow_kind", ""))
    return kinds
