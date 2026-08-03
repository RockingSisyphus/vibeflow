from __future__ import annotations

from dataclasses import dataclass, field
from vibeflow.core.algorithms import strongly_connected_components
from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    FLOW_KIND_DECISION,
    FLOW_KIND_GLOBAL_STATE,
    FLOW_KIND_IO,
    FLOW_KIND_PREDEFINED,
    TARGET_FEATURE_EXECUTION_LOCKS,
    TARGET_FEATURE_GLOBAL_STATE,
)
from vibeflow.core.contracts import provider_keys
from vibeflow.core.flow import (
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    STATUS_PLANNED,
    EdgeSpec,
    GraphConfig,
    NodeSpec,
    NodesetSpec,
)
from vibeflow.core.mainline import analyze_mainline
from vibeflow.core.models import (
    CoreCompilation,
    CoreCompileRequest,
    ImplementationFacts,
    TargetFeatureSet,
    ValidatedWorkflow,
)


@dataclass(frozen=True)
class CompiledGraph:
    order: tuple[str, ...]
    explicit_edges: tuple[EdgeSpec, ...]
    data_edges: tuple[EdgeSpec, ...]
    effective_edges: tuple[EdgeSpec, ...]
    providers: dict[str, str]
    consumers: dict[str, tuple[str, ...]]
    flow_kinds: dict[str, str]
    effect_scopes: dict[str, str] = field(default_factory=dict)
    contains_global_state: bool = False
    root_exclusive: bool = False
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
        implementation_facts: ImplementationFacts | None = None,
        target_features: TargetFeatureSet | None = None,
        known_nodesets: set[str] | None = None,
        owner: str = "pipeline",
    ) -> CompiledGraph:
        return compile_core(
            CoreCompileRequest(
                graph=graph,
                implementation_facts=implementation_facts or ImplementationFacts(),
                target_features=target_features or TargetFeatureSet(),
                known_nodesets=frozenset(
                    known_nodesets if known_nodesets is not None else graph.nodesets
                ),
                owner=owner,
            )
        ).compiled_graph


def compile_core(request: CoreCompileRequest) -> CoreCompilation:
    """Compile an in-memory workflow without Target or Tooling side effects."""

    graph = request.graph
    implementations = request.implementation_facts
    nodesets = set(request.known_nodesets or graph.nodesets)
    nodes_by_name = {node.id: node for node in graph.nodes}
    _validate_node_types(
        graph.nodes,
        implementations=implementations,
        nodesets=nodesets,
    )
    providers = _collect_providers(
        graph,
        input_keys=set(provider_keys(graph.inputs)),
    )
    consumers = _collect_consumers(graph)
    effective_edges = _merge_edges(graph.edges)
    flow_kinds = _node_flow_kinds(
        nodes_by_name,
        implementations=implementations,
        nodesets=nodesets,
    )
    effect_scopes = {
        node_id: (
            EFFECT_SCOPE_GLOBAL_STATE
            if flow_kind == FLOW_KIND_GLOBAL_STATE
            else EFFECT_SCOPE_NONE
        )
        for node_id, flow_kind in flow_kinds.items()
    }
    implemented_global_state_nodes = _implemented_global_state_paths(
        graph,
        implementations=implementations,
        known_nodesets=nodesets,
    )
    implemented_execution_lock_nodes = _implemented_execution_lock_paths(
        graph,
        known_nodesets=nodesets,
    )
    contains_global_state = bool(implemented_global_state_nodes)
    _validate_execution_lock_nesting(
        graph,
        known_nodesets=nodesets,
        owner=request.owner,
    )
    _validate_target_features(
        graph,
        target_features=request.target_features,
        implemented_global_state_nodes=implemented_global_state_nodes,
        implemented_execution_lock_nodes=implemented_execution_lock_nodes,
    )
    mainline = analyze_mainline(
        graph,
        effective_edges,
        flow_kinds,
        owner=request.owner,
    )
    _validate_effective_edge_roles(
        effective_edges,
        schedule_edges=mainline.schedule_edges,
        transfer_edges=mainline.transfer_edges,
    )
    _validate_async_result_routes(
        graph,
        effective_edges=effective_edges,
        schedule_edges=mainline.schedule_edges,
    )
    _validate_protected_async_scope(
        graph,
        schedule_edges=mainline.schedule_edges,
        protect_entire_graph=(
            contains_global_state or graph.execution_lock is not None
        ),
        owner=request.owner,
        implementations=implementations,
        known_nodesets=nodesets,
    )
    _validate_no_explicit_cycles(
        nodes_by_name,
        mainline.schedule_edges,
        owner=request.owner,
        role="schedule",
    )
    _validate_no_explicit_cycles(
        nodes_by_name,
        mainline.transfer_edges,
        owner=request.owner,
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
        effect_scopes=effect_scopes,
        contains_global_state=contains_global_state,
        root_exclusive=(
            contains_global_state or graph.execution_lock is not None
        ),
        mainline_edges=mainline.mainline_edges,
        data_bypass_edges=mainline.data_bypass_edges,
        async_edges=mainline.async_edges,
        schedule_edges=mainline.schedule_edges,
        transfer_edges=mainline.transfer_edges,
        edge_roles_resolved=True,
    )
    return CoreCompilation(
        workflow=ValidatedWorkflow(
            graph=graph,
            implementation_facts=implementations,
            target_features=request.target_features,
        ),
        compiled_graph=compiled,
        findings=tuple(mainline.findings),
    )


def _validate_target_features(
    graph: GraphConfig,
    *,
    target_features: TargetFeatureSet,
    implemented_global_state_nodes: frozenset[str],
    implemented_execution_lock_nodes: frozenset[str],
) -> None:
    if (
        implemented_global_state_nodes
        and not target_features.supports(TARGET_FEATURE_GLOBAL_STATE)
    ):
        raise GraphCompileError(
            (
                f"target '{target_features.target}' does not support feature "
                f"'{TARGET_FEATURE_GLOBAL_STATE}' required by implemented "
                "global_state nodes"
            ),
            "TARGET.FEATURE.UNSUPPORTED",
            details={
                "target": target_features.target,
                "feature": TARGET_FEATURE_GLOBAL_STATE,
                "nodes": sorted(implemented_global_state_nodes),
            },
        )
    if (
        (graph.execution_lock is not None or implemented_execution_lock_nodes)
        and not target_features.supports(TARGET_FEATURE_EXECUTION_LOCKS)
    ):
        raise GraphCompileError(
            (
                f"target '{target_features.target}' does not support feature "
                f"'{TARGET_FEATURE_EXECUTION_LOCKS}' required by execution_lock"
            ),
            "TARGET.FEATURE.UNSUPPORTED",
            details={
                "target": target_features.target,
                "feature": TARGET_FEATURE_EXECUTION_LOCKS,
                "root": graph.execution_lock is not None,
                "nodes": sorted(implemented_execution_lock_nodes),
            },
        )


def _validate_node_types(
    nodes: tuple[NodeSpec, ...],
    *,
    implementations: ImplementationFacts,
    nodesets: set[str],
) -> None:
    if implementations.strict:
        for type_key in nodesets:
            if implementations.get(type_key) is None:
                continue
            raise GraphCompileError(
                f"type_key '{type_key}' is defined by both a Python node and a nodeset",
                "NODE.TYPE.CONFLICT",
                details={"type_key": type_key, "sources": ["python_node", "nodeset"]},
            )
    if not implementations.strict:
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
        if implementations.get(node.type_used) is None:
            raise GraphCompileError(
                f"node '{node.id}' has unknown type_used '{node.type_used}'"
            )


def _collect_providers(
    graph: GraphConfig,
    *,
    input_keys: set[str] | None = None,
) -> dict[str, str]:
    input_keys = input_keys or set()
    providers: dict[str, str] = {}
    for node in graph.nodes:
        if not _node_is_executable(node, graph):
            continue
        for provider_spec in node.provides:
            key = provider_spec.key
            if key in input_keys:
                raise GraphCompileError(f"key '{key}' is declared by pipeline.inputs and provided by node '{node.id}'")
            if key in providers:
                raise GraphCompileError(f"key '{key}' provided by both '{providers[key]}' and '{node.id}'")
            providers[key] = node.id
    return providers


def _collect_consumers(graph: GraphConfig) -> dict[str, tuple[str, ...]]:
    consumers: dict[str, list[str]] = {}
    for node in graph.nodes:
        if not _node_is_executable(node, graph):
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
    graph: GraphConfig,
    *,
    effective_edges: tuple[EdgeSpec, ...],
    schedule_edges: tuple[EdgeSpec, ...],
) -> None:
    outgoing_sources = {edge.source for edge in effective_edges}
    scheduled_sources = {edge.source for edge in schedule_edges}
    for node in graph.nodes:
        if not _node_is_executable(node, graph):
            continue
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


def _validate_protected_async_scope(
    graph: GraphConfig,
    *,
    schedule_edges: tuple[EdgeSpec, ...],
    protect_entire_graph: bool,
    owner: str,
    implementations: ImplementationFacts,
    known_nodesets: set[str],
    nodeset_registry: dict[str, NodesetSpec] | None = None,
    active_nodesets: frozenset[str] = frozenset(),
) -> None:
    local_registry = dict(nodeset_registry or {})
    local_registry.update(graph.nodesets)
    available_nodesets = set(known_nodesets) | set(local_registry)
    protected = {
        node.id
        for node in graph.nodes
        if protect_entire_graph or node.execution_lock is not None
    }
    for node in graph.nodes:
        if not _node_is_executable(
            node,
            graph,
            nodeset_registry=local_registry,
        ):
            continue
        if (
            node.id in protected
            and node.async_mode == "detached"
        ):
            raise GraphCompileError(
                (
                    f"{owner} is protected by global_state or execution_lock; "
                    f"node '{node.id}' cannot use async='detached'"
                ),
                "GRAPH.EXECUTION_LOCK.DETACHED_FORBIDDEN",
                details={
                    "owner": owner,
                    "node": node.id,
                    "async": node.async_mode,
                },
            )
        if (
            node.id in protected
            and node.async_mode == "result_key"
            and not _has_static_result_consumer(
                graph,
                node,
                schedule_edges=schedule_edges,
            )
        ):
            raise GraphCompileError(
                (
                    f"{owner} is protected by global_state or execution_lock; "
                    f"async result_key node '{node.id}' has no statically "
                    "provable scheduled consumer path"
                ),
                "GRAPH.EXECUTION_LOCK.RESULT_UNJOINABLE",
                details={
                    "owner": owner,
                    "node": node.id,
                    "async": node.async_mode,
                    "result_key": node.result_key,
                },
            )
        target = _executed_nodeset_target(node, local_registry)
        if not target or target in active_nodesets:
            continue
        nodeset = local_registry.get(target)
        if nodeset is None or nodeset.status == STATUS_PLANNED:
            continue
        child_graph = nodeset.graph
        child_effective_edges = _merge_edges(child_graph.edges)
        child_flow_kinds = _node_flow_kinds(
            {child.id: child for child in child_graph.nodes},
            implementations=implementations,
            nodesets=available_nodesets,
        )
        child_mainline = analyze_mainline(
            child_graph,
            child_effective_edges,
            child_flow_kinds,
            owner=f"{owner}.{node.id}",
        )
        _validate_protected_async_scope(
            child_graph,
            schedule_edges=child_mainline.schedule_edges,
            protect_entire_graph=(
                protect_entire_graph
                or node.execution_lock is not None
                or child_graph.execution_lock is not None
            ),
            owner=f"{owner}.{node.id}",
            implementations=implementations,
            known_nodesets=available_nodesets,
            nodeset_registry=local_registry,
            active_nodesets=active_nodesets | {target},
        )


def _has_static_result_consumer(
    graph: GraphConfig,
    source: NodeSpec,
    *,
    schedule_edges: tuple[EdgeSpec, ...],
) -> bool:
    result_provider = next(
        (item for item in source.provides if item.key == source.result_key),
        None,
    )
    if result_provider is None:
        return False
    adjacency: dict[str, set[str]] = {}
    for edge in schedule_edges:
        if not edge.when:
            adjacency.setdefault(edge.source, set()).add(edge.target)
    nodes_by_id = {node.id: node for node in graph.nodes}
    pending = list(sorted(adjacency.get(source.id, ())))
    seen: set[str] = set()
    while pending:
        node_id = pending.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        candidate = nodes_by_id.get(node_id)
        if candidate is not None and any(
            requirement.type == result_provider.type
            for requirement in candidate.requires
        ):
            return True
        pending.extend(
            target
            for target in sorted(adjacency.get(node_id, ()))
            if target not in seen
        )
    return False


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


def _node_flow_kinds(
    nodes_by_name: dict[str, NodeSpec],
    *,
    implementations: ImplementationFacts,
    nodesets: set[str],
) -> dict[str, str]:
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
        implementation = implementations.get(spec.type_used)
        if implementation is None:
            kinds[name] = ""
            continue
        kinds[name] = implementation.flow_kind
    return kinds


def _implemented_global_state_paths(
    graph: GraphConfig,
    *,
    implementations: ImplementationFacts,
    known_nodesets: set[str],
) -> frozenset[str]:
    """Return qualified executable global-state nodes across nested blocks.

    Planned call sites and planned nodeset definitions are architecture-only,
    so their complete descendant trees are excluded from execution facts.
    The active-definition guard keeps malformed recursive nodeset graphs from
    recursing forever; the normal dependency validation still reports cycles.
    """

    return frozenset(
        _collect_implemented_global_state_paths(
            graph,
            implementations=implementations,
            known_nodesets=known_nodesets,
            nodeset_registry=graph.nodesets,
            path=(),
            active_nodesets=frozenset(),
        )
    )


def _collect_implemented_global_state_paths(
    graph: GraphConfig,
    *,
    implementations: ImplementationFacts,
    known_nodesets: set[str],
    nodeset_registry: dict[str, NodesetSpec],
    path: tuple[str, ...],
    active_nodesets: frozenset[str],
) -> set[str]:
    local_registry = dict(nodeset_registry)
    local_registry.update(graph.nodesets)
    available_nodesets = set(known_nodesets) | set(local_registry)
    flow_kinds = _node_flow_kinds(
        {node.id: node for node in graph.nodes},
        implementations=implementations,
        nodesets=available_nodesets,
    )
    found: set[str] = set()
    for node in graph.nodes:
        if not _node_is_executable(
            node,
            graph,
            nodeset_registry=local_registry,
        ):
            continue
        node_path = (*path, node.id)
        if flow_kinds.get(node.id) == FLOW_KIND_GLOBAL_STATE:
            found.add(".".join(node_path))
        target = _executed_nodeset_target(node, local_registry)
        if not target or target in active_nodesets:
            continue
        nodeset = local_registry.get(target)
        if nodeset is None or nodeset.status == STATUS_PLANNED:
            continue
        found.update(
            _collect_implemented_global_state_paths(
                nodeset.graph,
                implementations=implementations,
                known_nodesets=available_nodesets,
                nodeset_registry=local_registry,
                path=node_path,
                active_nodesets=active_nodesets | {target},
            )
        )
    return found


def _implemented_execution_lock_paths(
    graph: GraphConfig,
    *,
    known_nodesets: set[str],
) -> frozenset[str]:
    return frozenset(
        _collect_implemented_execution_lock_paths(
            graph,
            known_nodesets=known_nodesets,
            nodeset_registry=graph.nodesets,
            path=(),
            active_nodesets=frozenset(),
        )
    )


def _validate_execution_lock_nesting(
    graph: GraphConfig,
    *,
    known_nodesets: set[str],
    owner: str,
    inherited_key: str = "",
    nodeset_registry: dict[str, NodesetSpec] | None = None,
    path: tuple[str, ...] = (),
    active_nodesets: frozenset[str] = frozenset(),
) -> None:
    """Require nested lock scopes to reuse their active ancestor key."""

    local_registry = dict(nodeset_registry or {})
    local_registry.update(graph.nodesets)
    available_nodesets = set(known_nodesets) | set(local_registry)
    graph_key = graph.execution_lock.key if graph.execution_lock is not None else ""
    active_key = _nested_execution_lock_key(
        inherited_key,
        graph_key,
        subject=(owner if not path else f"block '{'.'.join(path)}'"),
    )
    for node in graph.nodes:
        if not _node_is_executable(
            node,
            graph,
            nodeset_registry=local_registry,
        ):
            continue
        node_path = (*path, node.id)
        node_key = (
            node.execution_lock.key if node.execution_lock is not None else ""
        )
        nested_key = _nested_execution_lock_key(
            active_key,
            node_key,
            subject=f"node '{'.'.join(node_path)}'",
        )
        target = _executed_nodeset_target(node, local_registry)
        if not target or target in active_nodesets:
            continue
        nodeset = local_registry.get(target)
        if nodeset is None or nodeset.status == STATUS_PLANNED:
            continue
        _validate_execution_lock_nesting(
            nodeset.graph,
            known_nodesets=available_nodesets,
            owner=owner,
            inherited_key=nested_key,
            nodeset_registry=local_registry,
            path=node_path,
            active_nodesets=active_nodesets | {target},
        )


def _nested_execution_lock_key(
    current: str,
    requested: str,
    *,
    subject: str,
) -> str:
    if current and requested and current != requested:
        raise GraphCompileError(
            (
                f"{subject} nests execution_lock key '{requested}' inside "
                f"incompatible key '{current}'; nested locks must reuse one key"
            ),
            "GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT",
            details={
                "subject": subject,
                "parent_key": current,
                "child_key": requested,
            },
        )
    return requested or current


def _collect_implemented_execution_lock_paths(
    graph: GraphConfig,
    *,
    known_nodesets: set[str],
    nodeset_registry: dict[str, NodesetSpec],
    path: tuple[str, ...],
    active_nodesets: frozenset[str],
) -> set[str]:
    local_registry = dict(nodeset_registry)
    local_registry.update(graph.nodesets)
    available_nodesets = set(known_nodesets) | set(local_registry)
    found: set[str] = set()
    for node in graph.nodes:
        if not _node_is_executable(
            node,
            graph,
            nodeset_registry=local_registry,
        ):
            continue
        node_path = (*path, node.id)
        qualified_node = ".".join(node_path)
        if node.execution_lock is not None:
            found.add(qualified_node)
        target = _executed_nodeset_target(node, local_registry)
        if not target or target in active_nodesets:
            continue
        nodeset = local_registry.get(target)
        if nodeset is None or nodeset.status == STATUS_PLANNED:
            continue
        if nodeset.graph.execution_lock is not None:
            found.add(qualified_node)
        found.update(
            _collect_implemented_execution_lock_paths(
                nodeset.graph,
                known_nodesets=available_nodesets,
                nodeset_registry=local_registry,
                path=node_path,
                active_nodesets=active_nodesets | {target},
            )
        )
    return found


def _executed_nodeset_target(
    node: NodeSpec,
    nodeset_registry: dict[str, NodesetSpec],
) -> str:
    if node.type_used in nodeset_registry:
        return node.type_used
    if node.type_used in LOOP_NODE_TYPES:
        return node.loop.body
    return ""


def _node_is_executable(
    node: NodeSpec,
    graph: GraphConfig,
    *,
    nodeset_registry: dict[str, NodesetSpec] | None = None,
) -> bool:
    if node.status == STATUS_PLANNED:
        return False
    local_registry = dict(nodeset_registry or {})
    local_registry.update(graph.nodesets)
    target = _executed_nodeset_target(node, local_registry)
    if not target:
        return True
    nodeset = local_registry.get(target)
    return nodeset is None or nodeset.status != STATUS_PLANNED


__all__ = [
    "CompiledGraph",
    "GraphCompileError",
    "GraphCompiler",
    "compile_core",
    "explicit_flow_cycles",
]
