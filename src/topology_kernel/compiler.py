from __future__ import annotations

from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import Any

from .graph_config import EdgeSpec, GraphConfig, LoopSpec, NodeSpec
from .plugin import PluginRegistry


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    acyclic_order: tuple[str, ...]
    explicit_edges: tuple[EdgeSpec, ...]
    data_edges: tuple[EdgeSpec, ...]
    effective_edges: tuple[EdgeSpec, ...]
    loop_edges: tuple[EdgeSpec, ...]
    loops: tuple[LoopSpec, ...]
    loop_orders: dict[str, tuple[str, ...]]
    edge_execution_limits: dict[tuple[str, str], int]
    providers: dict[str, str]
    consumers: dict[str, tuple[str, ...]]


@dataclass
class GraphCompileError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Graph compile error: {self.detail}"


class GraphCompiler:
    def compile(
        self,
        graph: GraphConfig,
        *,
        registry: Any | None = None,
        known_nodesets: set[str] | None = None,
        plugin_registry: PluginRegistry | None = None,
    ) -> CompiledGraph:
        _call_compiler_plugins(plugin_registry, "before_compile", graph)
        nodes_by_name = {node.name: node for node in graph.nodes}
        _validate_node_types(graph.nodes, registry=registry, nodesets=known_nodesets or set(graph.nodesets))
        providers = _collect_providers(graph.nodes)
        consumers = _collect_consumers(graph.nodes)
        boundary_inputs = set(graph.boundary.provides) if graph.boundary else set()
        data_edges = _derive_data_edges(graph.nodes, providers, available_inputs=set(graph.inputs) | boundary_inputs)
        effective_edges = _merge_edges((*graph.edges, *data_edges), loops=graph.loops)
        _validate_loop_until_keys(graph.loops, providers=providers, available_inputs=set(graph.inputs) | boundary_inputs)
        _validate_all_cycles_declared(nodes_by_name.keys(), effective_edges, graph.loops)
        loop_edges = tuple(edge for edge in effective_edges if edge.loop)
        acyclic_edges = tuple(edge for edge in effective_edges if not edge.loop)
        acyclic_order = _topological_order(nodes_by_name.keys(), acyclic_edges)
        loop_orders = _derive_loop_orders(nodes_by_name.keys(), effective_edges, graph.loops)
        edge_execution_limits = {edge.pair: edge.max_executions for edge in effective_edges}
        compiled = CompiledGraph(
            order=acyclic_order,
            acyclic_order=acyclic_order,
            explicit_edges=graph.edges,
            data_edges=data_edges,
            effective_edges=effective_edges,
            loop_edges=loop_edges,
            loops=graph.loops,
            loop_orders=loop_orders,
            edge_execution_limits=edge_execution_limits,
            providers=providers,
            consumers=consumers,
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
        if node.node_type.startswith("nodeset."):
            nodeset_name = node.node_type.removeprefix("nodeset.")
            if nodeset_name not in nodesets:
                raise GraphCompileError(f"node '{node.name}' references unknown nodeset '{nodeset_name}'")
            continue
        try:
            registry.get(node.node_type)
        except Exception as exc:
            raise GraphCompileError(f"node '{node.name}' has unknown type '{node.node_type}'") from exc


def _collect_providers(nodes: tuple[NodeSpec, ...]) -> dict[str, str]:
    providers: dict[str, str] = {}
    for node in nodes:
        for key in node.provides:
            if key in providers:
                raise GraphCompileError(f"key '{key}' provided by both '{providers[key]}' and '{node.name}'")
            providers[key] = node.name
    return providers


def _collect_consumers(nodes: tuple[NodeSpec, ...]) -> dict[str, tuple[str, ...]]:
    consumers: dict[str, list[str]] = {}
    for node in nodes:
        for key in node.requires:
            consumers.setdefault(key, []).append(node.name)
    return {key: tuple(values) for key, values in consumers.items()}


def _derive_data_edges(
    nodes: tuple[NodeSpec, ...],
    providers: dict[str, str],
    *,
    available_inputs: set[str],
) -> tuple[EdgeSpec, ...]:
    edges: list[EdgeSpec] = []
    for node in nodes:
        for key in node.requires:
            provider = providers.get(key)
            if provider is None:
                if key in available_inputs:
                    continue
                raise GraphCompileError(f"node '{node.name}' requires missing key '{key}'")
            if provider != node.name:
                edges.append(EdgeSpec(source=provider, target=node.name, max_executions=1))
    return tuple(edges)


def _merge_edges(edges: tuple[EdgeSpec, ...], *, loops: tuple[LoopSpec, ...]) -> tuple[EdgeSpec, ...]:
    loop_edge_to_name: dict[tuple[str, str], str] = {}
    loop_edge_to_limit: dict[tuple[str, str], int] = {}
    loop_internal_limit: dict[tuple[str, str], int] = {}
    for loop in loops:
        loop_nodes = set(loop.nodes) if loop.nodes else {name for pair in loop.edges for name in pair}
        for pair in loop.edges:
            loop_edge_to_name[pair] = loop.name
            loop_edge_to_limit[pair] = loop.max_iterations
        for source in loop_nodes:
            for target in loop_nodes:
                if source != target:
                    loop_internal_limit[(source, target)] = max(
                        loop_internal_limit.get((source, target), 1),
                        loop.max_iterations + 1,
                    )

    merged: dict[tuple[str, str], EdgeSpec] = {}
    for edge in edges:
        pair = edge.pair
        loop_name = edge.loop or loop_edge_to_name.get(pair, "")
        if pair in loop_edge_to_limit and not edge.max_executions_declared:
            limit = loop_edge_to_limit[pair]
        elif pair in loop_internal_limit and not edge.max_executions_declared:
            limit = loop_internal_limit[pair]
        else:
            limit = edge.max_executions
        existing = merged.get(pair)
        if existing is None:
            merged[pair] = EdgeSpec(edge.source, edge.target, limit, loop_name, edge.max_executions_declared)
        else:
            merged_limit = max(existing.max_executions, limit)
            merged[pair] = EdgeSpec(
                edge.source,
                edge.target,
                merged_limit,
                existing.loop or loop_name,
                existing.max_executions_declared or edge.max_executions_declared,
            )
    return tuple(merged.values())


def _validate_loop_until_keys(
    loops: tuple[LoopSpec, ...],
    *,
    providers: dict[str, str],
    available_inputs: set[str],
) -> None:
    known_keys = set(providers) | available_inputs
    for loop in loops:
        if loop.until and loop.until not in known_keys:
            raise GraphCompileError(f"loop '{loop.name}' until key is not resolvable: {loop.until}")


def _validate_all_cycles_declared(
    names: set[str] | list[str] | tuple[str, ...],
    edges: tuple[EdgeSpec, ...],
    loops: tuple[LoopSpec, ...],
) -> None:
    loop_pairs = {pair for loop in loops for pair in loop.edges}
    loop_names: set[str] = set()
    for loop in loops:
        if loop.name in loop_names:
            raise GraphCompileError(f"duplicate loop name: {loop.name}")
        loop_names.add(loop.name)
        loop_node_set = set(loop.nodes)
        edge_nodes = {name for pair in loop.edges for name in pair}
        if loop_node_set and not edge_nodes <= loop_node_set:
            missing = sorted(edge_nodes - loop_node_set)
            raise GraphCompileError(f"loop '{loop.name}' nodes must include loop edge endpoints: {missing}")
    for edge in edges:
        if edge.loop and edge.pair not in loop_pairs:
            raise GraphCompileError(f"edge {edge.source}->{edge.target} declares unknown loop '{edge.loop}'")
        if edge.loop and edge.max_executions < 1:
            raise GraphCompileError(f"loop edge {edge.source}->{edge.target} must have max_executions >= 1")

    try:
        _topological_order(names, tuple(edge for edge in edges if edge.pair not in loop_pairs))
    except GraphCompileError as exc:
        raise GraphCompileError(f"undeclared cycle detected after removing declared loop edges: {exc.detail}") from exc

    for loop in loops:
        if not loop.edges:
            raise GraphCompileError(f"loop '{loop.name}' must declare edges")
        for pair in loop.edges:
            if pair not in {edge.pair for edge in edges}:
                raise GraphCompileError(f"loop '{loop.name}' references missing edge {pair[0]}->{pair[1]}")


def _derive_loop_orders(
    names: set[str] | list[str] | tuple[str, ...],
    edges: tuple[EdgeSpec, ...],
    loops: tuple[LoopSpec, ...],
) -> dict[str, tuple[str, ...]]:
    all_names = {str(name) for name in names}
    orders: dict[str, tuple[str, ...]] = {}
    for loop in loops:
        loop_pairs = set(loop.edges)
        loop_nodes = tuple(loop.nodes) if loop.nodes else tuple(dict.fromkeys(name for pair in loop.edges for name in pair))
        for node in loop_nodes:
            if node not in all_names:
                raise GraphCompileError(f"loop '{loop.name}' references unknown node: {node}")
        loop_node_set = set(loop_nodes)
        internal_acyclic_edges = tuple(
            edge
            for edge in edges
            if edge.source in loop_node_set and edge.target in loop_node_set and edge.pair not in loop_pairs
        )
        orders[loop.name] = _topological_order(loop_nodes, internal_acyclic_edges)
    return orders


def _topological_order(names: set[str] | list[str] | tuple[str, ...], edges: tuple[EdgeSpec, ...]) -> tuple[str, ...]:
    predecessors: dict[str, set[str]] = {str(name): set() for name in names}
    for edge in edges:
        predecessors[edge.target].add(edge.source)
    sorter = TopologicalSorter()
    for name in sorted(predecessors):
        sorter.add(name, *sorted(predecessors[name]))
    try:
        return tuple(sorter.static_order())
    except CycleError as exc:
        raise GraphCompileError("cycle detected: " + _format_cycle(exc)) from exc


def _format_cycle(error: CycleError) -> str:
    if len(error.args) >= 2 and isinstance(error.args[1], (list, tuple)):
        cycle = [str(item) for item in error.args[1]]
        if cycle and cycle[0] != cycle[-1]:
            cycle.append(cycle[0])
        return " -> ".join(cycle)
    return "unknown"
