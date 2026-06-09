from __future__ import annotations

from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

from .graph_config import EdgeSpec, GraphConfig, LoopSpec, NodeSpec


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    acyclic_order: tuple[str, ...]
    explicit_edges: tuple[EdgeSpec, ...]
    data_edges: tuple[EdgeSpec, ...]
    effective_edges: tuple[EdgeSpec, ...]
    loop_edges: tuple[EdgeSpec, ...]
    loops: tuple[LoopSpec, ...]
    providers: dict[str, str]
    consumers: dict[str, tuple[str, ...]]


@dataclass
class GraphCompileError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Graph compile error: {self.detail}"


class GraphCompiler:
    def compile(self, graph: GraphConfig) -> CompiledGraph:
        nodes_by_name = {node.name: node for node in graph.nodes}
        providers = _collect_providers(graph.nodes)
        consumers = _collect_consumers(graph.nodes)
        data_edges = _derive_data_edges(graph.nodes, providers, available_inputs=set(graph.inputs))
        effective_edges = _merge_edges((*graph.edges, *data_edges), loops=graph.loops)
        _validate_all_cycles_declared(nodes_by_name.keys(), effective_edges, graph.loops)
        loop_edges = tuple(edge for edge in effective_edges if edge.loop)
        acyclic_edges = tuple(edge for edge in effective_edges if not edge.loop)
        acyclic_order = _topological_order(nodes_by_name.keys(), acyclic_edges)
        return CompiledGraph(
            order=acyclic_order,
            acyclic_order=acyclic_order,
            explicit_edges=graph.edges,
            data_edges=data_edges,
            effective_edges=effective_edges,
            loop_edges=loop_edges,
            loops=graph.loops,
            providers=providers,
            consumers=consumers,
        )


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
    for loop in loops:
        for pair in loop.edges:
            loop_edge_to_name[pair] = loop.name
            loop_edge_to_limit[pair] = loop.max_iterations

    merged: dict[tuple[str, str], EdgeSpec] = {}
    for edge in edges:
        pair = edge.pair
        loop_name = edge.loop or loop_edge_to_name.get(pair, "")
        limit = max(edge.max_executions, loop_edge_to_limit.get(pair, edge.max_executions))
        existing = merged.get(pair)
        if existing is None:
            merged[pair] = EdgeSpec(edge.source, edge.target, limit, loop_name)
        else:
            merged[pair] = EdgeSpec(
                edge.source,
                edge.target,
                max(existing.max_executions, limit),
                existing.loop or loop_name,
            )
    return tuple(merged.values())


def _validate_all_cycles_declared(
    names: set[str] | list[str] | tuple[str, ...],
    edges: tuple[EdgeSpec, ...],
    loops: tuple[LoopSpec, ...],
) -> None:
    loop_pairs = {pair for loop in loops for pair in loop.edges}
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
