from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from vibeflow.graph_config.types import GraphConfig, LOOP_NODE_TYPES, NodeSpec


@dataclass(frozen=True)
class NodesetDependency:
    owner: str
    node_id: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "owner": self.owner,
            "node_id": self.node_id,
            "target": self.target,
            "kind": self.kind,
        }


NodesetPath = tuple[tuple[str, ...], tuple[NodesetDependency, ...]]


@dataclass(frozen=True)
class NodesetDependencyGraph:
    pipeline: tuple[NodesetDependency, ...]
    nodesets: Mapping[str, tuple[NodesetDependency, ...]]


@dataclass(frozen=True)
class NodesetDepthViolation:
    limit: int
    chain: tuple[str, ...]
    calls: tuple[NodesetDependency, ...]
    owner: str

    @property
    def actual_depth(self) -> int:
        return len(self.chain)

    def to_details(self) -> dict[str, object]:
        return {
            "limit": self.limit,
            "actual_depth": self.actual_depth,
            "chain": self.chain,
            "calls": tuple(call.to_dict() for call in self.calls),
            "owner": self.owner,
        }


def analyze_nodeset_dependencies(graph: GraphConfig) -> NodesetDependencyGraph:
    return NodesetDependencyGraph(
        pipeline=_dependencies_for_nodes(graph.nodes, graph=graph, owner="pipeline"),
        nodesets={
            name: _dependencies_for_nodes(nodeset.graph.nodes, graph=graph, owner=f"nodeset:{name}")
            for name, nodeset in sorted(graph.nodesets.items())
        },
    )


def nodeset_dependency_cycles(dependencies: NodesetDependencyGraph) -> tuple[tuple[str, ...], ...]:
    adjacency = _adjacency(dependencies)
    state: dict[str, int] = {}
    cycles: set[tuple[str, ...]] = set()

    for root in sorted(adjacency):
        if state.get(root, 0) != 0:
            continue
        cycles.update(_cycles_from_root(root, adjacency=adjacency, state=state))

    return tuple(sorted(cycles))


def nodeset_depth_violations(graph: GraphConfig, *, max_depth: int) -> tuple[NodesetDepthViolation, ...]:
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth <= 0:
        raise ValueError("nodeset max depth must be a positive integer")
    dependencies = analyze_nodeset_dependencies(graph)
    cycles = nodeset_dependency_cycles(dependencies)
    cyclic_nodes = {name for cycle in cycles for name in cycle[:-1]}
    longest = _longest_acyclic_paths(dependencies, cyclic_nodes=cyclic_nodes)
    reachable = _reachable_from_pipeline(dependencies)
    roots: list[tuple[str, NodesetDependency | None, str]] = [
        (dependency.target, dependency, "pipeline")
        for dependency in dependencies.pipeline
        if dependency.target not in cyclic_nodes
    ]

    remaining = set(dependencies.nodesets) - reachable - cyclic_nodes
    incoming = {name: 0 for name in remaining}
    for source in remaining:
        for dependency in dependencies.nodesets.get(source, ()):
            if dependency.target in remaining:
                incoming[dependency.target] += 1
    roots.extend(
        (name, None, f"nodeset:{name}")
        for name in sorted(remaining)
        if incoming[name] == 0
    )

    violations: list[NodesetDepthViolation] = []
    seen_chains: set[tuple[str, ...]] = set()
    for root, entry, owner in roots:
        path = longest.get(root)
        if path is None:
            continue
        chain, calls = path
        if len(chain) <= max_depth or chain in seen_chains:
            continue
        seen_chains.add(chain)
        violations.append(
            NodesetDepthViolation(
                limit=max_depth,
                chain=chain,
                calls=((entry,) if entry is not None else ()) + calls,
                owner=owner,
            )
        )
    return tuple(violations)


def _dependencies_for_nodes(
    nodes: tuple[NodeSpec, ...],
    *,
    graph: GraphConfig,
    owner: str,
) -> tuple[NodesetDependency, ...]:
    dependencies: list[NodesetDependency] = []
    for node in nodes:
        if node.type_used in LOOP_NODE_TYPES and node.loop.body:
            dependencies.append(NodesetDependency(owner, node.id, node.loop.body, "loop_body"))
        elif node.type_used in graph.nodesets:
            dependencies.append(NodesetDependency(owner, node.id, node.type_used, "nodeset"))
    return tuple(sorted(dependencies, key=_dependency_key))


def _adjacency(dependencies: NodesetDependencyGraph) -> dict[str, tuple[str, ...]]:
    return {
        name: tuple(sorted({dependency.target for dependency in items if dependency.target in dependencies.nodesets}))
        for name, items in dependencies.nodesets.items()
    }


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    body = cycle[:-1]
    if not body:
        return cycle
    rotations = [body[index:] + body[:index] for index in range(len(body))]
    canonical = min(rotations)
    return (*canonical, canonical[0])


def _cycles_from_root(
    root: str,
    *,
    adjacency: Mapping[str, tuple[str, ...]],
    state: dict[str, int],
) -> set[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()
    path: list[str] = []
    positions: dict[str, int] = {}
    stack: list[tuple[str, int]] = [(root, 0)]
    while stack:
        name, child_index = stack[-1]
        _start_cycle_node(name, state=state, path=path, positions=positions)
        children = adjacency.get(name, ())
        if child_index >= len(children):
            _finish_cycle_node(name, state=state, path=path, positions=positions, stack=stack)
            continue
        child = children[child_index]
        stack[-1] = (name, child_index + 1)
        cycle = _visit_cycle_child(child, state=state, path=path, positions=positions, stack=stack)
        if cycle is not None:
            cycles.add(cycle)
    return cycles


def _start_cycle_node(name: str, *, state: dict[str, int], path: list[str], positions: dict[str, int]) -> None:
    if state.get(name, 0) != 0:
        return
    state[name] = 1
    positions[name] = len(path)
    path.append(name)


def _finish_cycle_node(
    name: str,
    *,
    state: dict[str, int],
    path: list[str],
    positions: dict[str, int],
    stack: list[tuple[str, int]],
) -> None:
    stack.pop()
    state[name] = 2
    positions.pop(name, None)
    path.pop()


def _visit_cycle_child(
    child: str,
    *,
    state: Mapping[str, int],
    path: list[str],
    positions: Mapping[str, int],
    stack: list[tuple[str, int]],
) -> tuple[str, ...] | None:
    child_state = state.get(child, 0)
    if child_state == 0:
        stack.append((child, 0))
        return None
    if child_state == 1:
        return _canonical_cycle(tuple((*path[positions[child] :], child)))
    return None


def _longest_acyclic_paths(
    dependencies: NodesetDependencyGraph,
    *,
    cyclic_nodes: set[str],
) -> dict[str, NodesetPath]:
    memo: dict[str, NodesetPath] = {}
    for root in sorted(dependencies.nodesets):
        if root in cyclic_nodes or root in memo:
            continue
        _populate_longest_paths(root, dependencies=dependencies, cyclic_nodes=cyclic_nodes, memo=memo)
    return memo


def _populate_longest_paths(
    root: str,
    *,
    dependencies: NodesetDependencyGraph,
    cyclic_nodes: set[str],
    memo: dict[str, NodesetPath],
) -> None:
    stack: list[tuple[str, bool]] = [(root, False)]
    while stack:
        name, expanded = stack.pop()
        if name in memo or name in cyclic_nodes:
            continue
        children = _acyclic_children(name, dependencies=dependencies, cyclic_nodes=cyclic_nodes)
        if not expanded:
            _queue_longest_path_children(name, children=children, memo=memo, stack=stack)
            continue
        memo[name] = _select_longest_path(name, children=children, memo=memo)


def _acyclic_children(
    name: str,
    *,
    dependencies: NodesetDependencyGraph,
    cyclic_nodes: set[str],
) -> tuple[NodesetDependency, ...]:
    return tuple(
        dependency
        for dependency in dependencies.nodesets.get(name, ())
        if dependency.target in dependencies.nodesets and dependency.target not in cyclic_nodes
    )


def _queue_longest_path_children(
    name: str,
    *,
    children: tuple[NodesetDependency, ...],
    memo: Mapping[str, NodesetPath],
    stack: list[tuple[str, bool]],
) -> None:
    stack.append((name, True))
    for dependency in reversed(children):
        if dependency.target not in memo:
            stack.append((dependency.target, False))


def _select_longest_path(
    name: str,
    *,
    children: tuple[NodesetDependency, ...],
    memo: Mapping[str, NodesetPath],
) -> NodesetPath:
    best: NodesetPath = ((name,), ())
    for dependency in children:
        child_path = memo.get(dependency.target)
        if child_path is None:
            continue
        candidate = ((name, *child_path[0]), (dependency, *child_path[1]))
        if _path_key(candidate) > _path_key(best):
            best = candidate
    return best


def _reachable_from_pipeline(dependencies: NodesetDependencyGraph) -> set[str]:
    reachable: set[str] = set()
    stack = [dependency.target for dependency in reversed(dependencies.pipeline)]
    while stack:
        name = stack.pop()
        if name in reachable or name not in dependencies.nodesets:
            continue
        reachable.add(name)
        stack.extend(dependency.target for dependency in reversed(dependencies.nodesets.get(name, ())))
    return reachable


def _dependency_key(dependency: NodesetDependency) -> tuple[str, str, str, str]:
    return dependency.target, dependency.kind, dependency.node_id, dependency.owner


def _path_key(path: NodesetPath) -> tuple[object, ...]:
    chain, calls = path
    return len(chain), tuple(reversed(chain)), tuple(reversed(tuple(_dependency_key(call) for call in calls)))
