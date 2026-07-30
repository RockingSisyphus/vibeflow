from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vibeflow.data_contract import provider_keys
from vibeflow.graph_config.algorithms import strongly_connected_components
from vibeflow.graph_config import EdgeSpec, GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, NodeSpec, STATUS_PLANNED
from vibeflow.node import FLOW_KIND_DECISION, FLOW_KIND_IO, FLOW_KIND_PREDEFINED
from vibeflow.plugin import PluginRegistry


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    explicit_edges: tuple[EdgeSpec, ...]
    data_edges: tuple[EdgeSpec, ...]
    effective_edges: tuple[EdgeSpec, ...]
    providers: dict[str, str]
    consumers: dict[str, tuple[str, ...]]
    flow_kinds: dict[str, str]
    mainline_edges: tuple[EdgeSpec, ...] = ()
    data_bypass_edges: tuple[EdgeSpec, ...] = ()
    async_edges: tuple[EdgeSpec, ...] = ()
    schedule_edges: tuple[EdgeSpec, ...] = ()
    transfer_edges: tuple[EdgeSpec, ...] = ()
    edge_roles_resolved: bool = False

    @property
    def resolved_schedule_edges(self) -> tuple[EdgeSpec, ...]:
        if self.edge_roles_resolved:
            return self.schedule_edges
        return self.effective_edges

    @property
    def resolved_transfer_edges(self) -> tuple[EdgeSpec, ...]:
        if self.edge_roles_resolved:
            return self.transfer_edges
        return self.effective_edges


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
        catalog: Any | None = None,
        known_nodesets: set[str] | None = None,
        plugin_registry: PluginRegistry | None = None,
        owner: str = "pipeline",
    ) -> CompiledGraph:
        if registry is not None and catalog is not None:
            raise GraphCompileError("compile accepts either registry or catalog, not both")
        type_source = catalog if catalog is not None else registry
        _call_compiler_plugins(plugin_registry, "before_compile", graph)
        nodes_by_name = {node.id: node for node in graph.nodes}
        _validate_node_types(graph.nodes, registry=type_source, nodesets=known_nodesets or set(graph.nodesets))
        providers = _collect_providers(graph.nodes, input_keys=set(provider_keys(graph.inputs)))
        consumers = _collect_consumers(graph.nodes)
        effective_edges = _merge_edges(graph.edges)
        flow_kinds = _node_flow_kinds(nodes_by_name, registry=type_source, nodesets=known_nodesets or set(graph.nodesets))
        from vibeflow.graph_config.mainline import analyze_mainline

        mainline = analyze_mainline(graph, effective_edges, flow_kinds, owner=owner)
        _validate_effective_edge_roles(
            effective_edges,
            schedule_edges=mainline.schedule_edges,
            transfer_edges=mainline.transfer_edges,
        )
        _validate_async_result_routes(
            graph.nodes,
            effective_edges=effective_edges,
            schedule_edges=mainline.schedule_edges,
        )
        _validate_no_explicit_cycles(
            nodes_by_name,
            mainline.schedule_edges,
            owner=owner,
            role="schedule",
        )
        _validate_no_explicit_cycles(
            nodes_by_name,
            mainline.transfer_edges,
            owner=owner,
            role="transfer",
        )
        _validate_routing_edge_conditions(graph.edges, flow_kinds=flow_kinds)
        compiled = CompiledGraph(
            order=tuple(node.id for node in graph.nodes),
            explicit_edges=graph.edges,
            data_edges=mainline.data_bypass_edges,
            effective_edges=effective_edges,
            providers=providers,
            consumers=consumers,
            flow_kinds=flow_kinds,
            mainline_edges=mainline.mainline_edges,
            data_bypass_edges=mainline.data_bypass_edges,
            async_edges=mainline.async_edges,
            schedule_edges=mainline.schedule_edges,
            transfer_edges=mainline.transfer_edges,
            edge_roles_resolved=True,
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
    if registry is not None:
        for type_key in nodesets:
            try:
                _require_registered_type(registry, type_key)
            except Exception:
                continue
            raise GraphCompileError(
                f"type_key '{type_key}' is defined by both a Python node and a nodeset",
                "NODE.TYPE.CONFLICT",
                details={"type_key": type_key, "sources": ["python_node", "nodeset"]},
            )
    if registry is None:
        return
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        if node.type_used in LOOP_NODE_TYPES:
            continue
        if node.type_used == IO_NODE_TYPE:
            continue
        if node.type_used in nodesets:
            continue
        try:
            _require_registered_type(registry, node.type_used)
        except Exception as exc:
            raise GraphCompileError(f"node '{node.id}' has unknown type_used '{node.type_used}'") from exc


def _collect_providers(nodes: tuple[NodeSpec, ...], *, input_keys: set[str] | None = None) -> dict[str, str]:
    input_keys = input_keys or set()
    providers: dict[str, str] = {}
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        for provider_spec in node.provides:
            key = provider_spec.key
            if key in input_keys:
                raise GraphCompileError(f"key '{key}' is declared by pipeline.inputs and provided by node '{node.id}'")
            if key in providers:
                raise GraphCompileError(f"key '{key}' provided by both '{providers[key]}' and '{node.id}'")
            providers[key] = node.id
    return providers


def _collect_consumers(nodes: tuple[NodeSpec, ...]) -> dict[str, tuple[str, ...]]:
    consumers: dict[str, list[str]] = {}
    for node in nodes:
        if node.status == STATUS_PLANNED:
            continue
        for requirement in node.requires:
            consumers.setdefault(requirement.type, []).append(node.id)
    return {key: tuple(values) for key, values in consumers.items()}


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
    merged[edge.pair] = EdgeSpec(
        edge.source,
        edge.target,
        existing.when or edge.when,
        _merge_edge_role(existing.schedule, edge.schedule, edge=edge, role="schedule"),
        _merge_edge_role(existing.transfer, edge.transfer, edge=edge, role="transfer"),
    )


def _merge_edge_role(
    existing: bool | None,
    incoming: bool | None,
    *,
    edge: EdgeSpec,
    role: str,
) -> bool | None:
    if existing is None:
        return incoming
    if incoming is None or incoming == existing:
        return existing
    raise GraphCompileError(
        (
            f"duplicate edge {edge.source}->{edge.target} declares conflicting "
            f"{role} roles"
        ),
        "GRAPH.EDGE.ROLE_CONFLICT",
    )


def _validate_effective_edge_roles(
    edges: tuple[EdgeSpec, ...],
    *,
    schedule_edges: tuple[EdgeSpec, ...],
    transfer_edges: tuple[EdgeSpec, ...],
) -> None:
    schedule_pairs = {edge.pair for edge in schedule_edges}
    transfer_pairs = {edge.pair for edge in transfer_edges}
    for edge in edges:
        if edge.pair in schedule_pairs or edge.pair in transfer_pairs:
            continue
        raise GraphCompileError(
            (
                f"edge {edge.source}->{edge.target} must schedule, transfer, "
                "or both after role inference"
            ),
            "GRAPH.EDGE.NO_ROLE",
            details={
                "source": edge.source,
                "target": edge.target,
                "schedule": False,
                "transfer": False,
            },
        )


def _validate_async_result_routes(
    nodes: tuple[NodeSpec, ...],
    *,
    effective_edges: tuple[EdgeSpec, ...],
    schedule_edges: tuple[EdgeSpec, ...],
) -> None:
    outgoing_sources = {edge.source for edge in effective_edges}
    scheduled_sources = {edge.source for edge in schedule_edges}
    for node in nodes:
        if node.async_mode != "result_key":
            continue
        if node.id not in outgoing_sources or node.id in scheduled_sources:
            continue
        raise GraphCompileError(
            (
                f"async result_key node '{node.id}' has no scheduled outgoing "
                "edge to join its result"
            ),
            "GRAPH.ASYNC.RESULT_UNJOINABLE",
            details={
                "node": node.id,
                "async": node.async_mode,
                "result_key": node.result_key,
                "suggestion": (
                    "add a schedule edge to a result consumer or use "
                    "async='detached' for side work"
                ),
            },
        )


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


def _validate_no_explicit_cycles(
    nodes_by_name: dict[str, NodeSpec],
    edges: tuple[EdgeSpec, ...],
    *,
    owner: str,
    role: str,
) -> None:
    cycles = explicit_flow_cycles(nodes_by_name, edges, owner=owner)
    if not cycles:
        return
    first = cycles[0]
    members = [str(item) for item in first.get("members", ())]
    if role == "transfer":
        message = (
            "explicit data transfer cycle is forbidden in ordinary graph: "
            + " -> ".join(members)
            + "; use vibeflow.loop.while carry for iterative data"
        )
        rule_id = "GRAPH.DATA.CYCLE.FORBIDDEN"
    else:
        message = (
            "explicit flow cycle is forbidden in ordinary graph: "
            + " -> ".join(members)
            + "; use vibeflow.loop.while for loops"
        )
        rule_id = "GRAPH.CYCLE.FORBIDDEN"
    raise GraphCompileError(
        message,
        rule_id,
        details={
            "owner": owner,
            "edge_role": role,
            "members": list(first.get("members", ())),
            "edges": list(first.get("edges", ())),
            "cycles": list(cycles),
            "suggestion": (
                "Replace ordinary data cycles with vibeflow.loop.while carry."
                if role == "transfer"
                else "Replace ordinary edge cycles with a vibeflow.loop.while node whose body is a nodeset."
            ),
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


def _node_flow_kinds(nodes_by_name: dict[str, NodeSpec], *, registry: Any | None, nodesets: set[str]) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for name, spec in nodes_by_name.items():
        if spec.status == STATUS_PLANNED:
            kinds[name] = spec.flow_kind
            continue
        if spec.type_used in LOOP_NODE_TYPES:
            kinds[name] = FLOW_KIND_PREDEFINED
            continue
        if spec.type_used == IO_NODE_TYPE:
            kinds[name] = FLOW_KIND_IO
            continue
        if spec.type_used in nodesets:
            kinds[name] = FLOW_KIND_PREDEFINED
            continue
        if registry is None:
            kinds[name] = ""
            continue
        registered = _require_registered_type(registry, spec.type_used)
        direct = str(getattr(registered, "flow_kind", "") or "")
        info = getattr(registered, "NODE_INFO", None)
        kinds[name] = direct or str(getattr(info, "flow_kind", ""))
    return kinds


def _require_registered_type(source: Any, type_key: str) -> Any:
    """Resolve a type from either the legacy Python registry or a descriptor catalog."""

    require = getattr(source, "require", None)
    if callable(require):
        return require(type_key)
    get = getattr(source, "get", None)
    if not callable(get):
        raise KeyError(type_key)
    value = get(type_key)
    if value is None:
        raise KeyError(type_key)
    return value
