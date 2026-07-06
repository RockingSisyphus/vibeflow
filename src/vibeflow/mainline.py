from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .graph_config import EdgeSpec, GraphConfig, JOIN_POLICY_ALL
from .node import FLOW_KIND_DECISION, FLOW_KIND_TERMINAL

EDGE_CLASS_MAINLINE = "mainline"
EDGE_CLASS_DATA_BYPASS = "data_bypass"
EDGE_CLASS_ASYNC = "async"


@dataclass(frozen=True)
class MainlineFinding:
    rule_id: str
    source: str
    target: str
    message: str
    details: Mapping[str, object]


@dataclass(frozen=True)
class MainlineAnalysis:
    owner: str
    mainline_edges: tuple[EdgeSpec, ...]
    data_bypass_edges: tuple[EdgeSpec, ...]
    async_edges: tuple[EdgeSpec, ...]
    schedule_edges: tuple[EdgeSpec, ...]
    transfer_edges: tuple[EdgeSpec, ...]
    mainline_nodes: tuple[str, ...]
    async_nodes: tuple[str, ...]
    findings: tuple[MainlineFinding, ...] = ()

    def edge_class(self, edge: EdgeSpec) -> str:
        pair = edge.pair
        if pair in {item.pair for item in self.async_edges}:
            return EDGE_CLASS_ASYNC
        if pair in {item.pair for item in self.data_bypass_edges}:
            return EDGE_CLASS_DATA_BYPASS
        if pair in {item.pair for item in self.mainline_edges}:
            return EDGE_CLASS_MAINLINE
        return ""

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "mainline_edges": [_edge_summary(edge) for edge in self.mainline_edges],
            "data_bypass_edges": [_edge_summary(edge) for edge in self.data_bypass_edges],
            "async_edges": [_edge_summary(edge) for edge in self.async_edges],
            "schedule_edges": [_edge_summary(edge) for edge in self.schedule_edges],
            "transfer_edges": [_edge_summary(edge) for edge in self.transfer_edges],
            "mainline_nodes": list(self.mainline_nodes),
            "async_nodes": list(self.async_nodes),
            "findings": [
                {
                    "rule_id": finding.rule_id,
                    "source": finding.source,
                    "target": finding.target,
                    "message": finding.message,
                    "details": dict(finding.details),
                }
                for finding in self.findings
            ],
        }


def analyze_mainline(graph: GraphConfig, edges: Sequence[EdgeSpec], flow_kinds: Mapping[str, str], *, owner: str = "pipeline") -> MainlineAnalysis:
    async_nodes = {node.name for node in graph.nodes if node.async_mode}
    all_edges = tuple(edges)
    async_edges = tuple(edge for edge in all_edges if edge.source in async_nodes or edge.target in async_nodes)
    sync_edges = tuple(edge for edge in all_edges if edge.source not in async_nodes and edge.target not in async_nodes)

    data_bypass_edges = tuple(
        edge
        for edge in sync_edges
        if _is_data_bypass_candidate(edge, sync_edges, flow_kinds)
    )
    data_bypass_pairs = {edge.pair for edge in data_bypass_edges}
    mainline_edges = tuple(edge for edge in sync_edges if edge.pair not in data_bypass_pairs)
    schedule_edges = (*mainline_edges, *async_edges)
    transfer_edges = all_edges
    mainline_nodes = tuple(
        node.name
        for node in graph.nodes
        if node.name not in async_nodes and _node_on_mainline(node.name, mainline_edges, flow_kinds)
    )
    findings = _mainline_findings(
        graph,
        sync_edges,
        mainline_edges,
        data_bypass_edges,
        async_nodes=async_nodes,
        flow_kinds=flow_kinds,
        owner=owner,
    )
    return MainlineAnalysis(
        owner=owner,
        mainline_edges=mainline_edges,
        data_bypass_edges=data_bypass_edges,
        async_edges=async_edges,
        schedule_edges=schedule_edges,
        transfer_edges=transfer_edges,
        mainline_nodes=mainline_nodes,
        async_nodes=tuple(sorted(async_nodes)),
        findings=findings,
    )


def _is_data_bypass_candidate(edge: EdgeSpec, sync_edges: tuple[EdgeSpec, ...], flow_kinds: Mapping[str, str]) -> bool:
    if edge.when:
        return False
    if flow_kinds.get(edge.source) == FLOW_KIND_DECISION:
        return False
    return bool(_path_between(edge.source, edge.target, sync_edges, excluded_pair=edge.pair))


def _node_on_mainline(node_name: str, mainline_edges: tuple[EdgeSpec, ...], flow_kinds: Mapping[str, str]) -> bool:
    if flow_kinds.get(node_name) == FLOW_KIND_TERMINAL:
        return True
    return any(edge.source == node_name or edge.target == node_name for edge in mainline_edges)


def _mainline_findings(
    graph: GraphConfig,
    sync_edges: tuple[EdgeSpec, ...],
    mainline_edges: tuple[EdgeSpec, ...],
    data_bypass_edges: tuple[EdgeSpec, ...],
    *,
    async_nodes: set[str],
    flow_kinds: Mapping[str, str],
    owner: str,
) -> tuple[MainlineFinding, ...]:
    findings: list[MainlineFinding] = []
    schedule_outgoing = _outgoing(mainline_edges)
    schedule_incoming = _incoming(mainline_edges)
    starts = _start_nodes(graph, mainline_edges, flow_kinds, async_nodes)
    ends = _end_nodes(graph, mainline_edges, flow_kinds, async_nodes)
    can_reach_end = _reverse_reachable(ends, mainline_edges)
    reachable_from_start = _walk(starts, schedule_outgoing) | starts

    for edge in data_bypass_edges:
        if edge.target in starts:
            continue
        if edge.target in reachable_from_start and schedule_incoming.get(edge.target):
            continue
        path = _path_between(edge.source, edge.target, mainline_edges)
        findings.append(
            _finding(
                "GRAPH.MAINLINE.DATA_BYPASS_WITHOUT_MAINLINE_TRIGGER",
                owner,
                edge,
                "data bypass target has no independent mainline trigger",
                attempted=EDGE_CLASS_DATA_BYPASS,
                mainline_path=path,
                branch_nodes=[edge.target],
                branch_edges=[edge],
                async_nodes_seen=async_nodes,
                suggested_fixes=[
                    f"add a mainline edge into '{edge.target}'",
                    f"remove edge {edge.source}->{edge.target} if the target should not run",
                    f"mark '{edge.target}' or its enclosing nodeset async if it is side work",
                ],
            )
        )

    for node in graph.nodes:
        if node.name in async_nodes:
            continue
        outgoing = schedule_outgoing.get(node.name, ())
        if len(outgoing) <= 1 or flow_kinds.get(node.name) == FLOW_KIND_DECISION:
            continue
        if _fanout_has_explicit_join(outgoing, schedule_outgoing, {item.name: item for item in graph.nodes}):
            continue
        branch_nodes = sorted({target for edge in outgoing for target in _walk({edge.target}, schedule_outgoing)} | {edge.target for edge in outgoing})
        findings.append(
            _finding(
                "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT",
                owner,
                outgoing[0],
                f"sync node '{node.name}' has multiple mainline outgoing edges but is not a decision node",
                attempted=EDGE_CLASS_MAINLINE,
                mainline_path=_first_mainline_path(starts, ends, mainline_edges),
                branch_nodes=branch_nodes,
                branch_edges=list(outgoing),
                async_nodes_seen=async_nodes,
                suggested_fixes=[
                    f"serialize the outgoing work after '{node.name}' into a single mainline chain",
                    "keep only shortcut/data-transfer edges when a downstream mainline path already exists",
                    "mark side-work node or nodeset async='detached' or async='result_key'",
                ],
            )
        )

    for edge in mainline_edges:
        if flow_kinds.get(edge.source) != FLOW_KIND_DECISION:
            continue
        if edge.target in can_reach_end:
            continue
        findings.append(
            _finding(
                "GRAPH.MAINLINE.DECISION_BRANCH_DEAD_END",
                owner,
                edge,
                f"decision branch {edge.source}->{edge.target} cannot reach an end node",
                attempted=EDGE_CLASS_MAINLINE,
                mainline_path=_path_between(edge.target, next(iter(ends), edge.target), mainline_edges),
                branch_nodes=sorted(_walk({edge.target}, schedule_outgoing) | {edge.target}),
                branch_edges=[item for item in mainline_edges if item.source in _walk({edge.target}, schedule_outgoing) | {edge.target}],
                async_nodes_seen=async_nodes,
                suggested_fixes=[
                    f"connect branch '{edge.when or edge.target}' back to a node that reaches an end terminal",
                    f"remove edge {edge.source}->{edge.target} if this branch is not used",
                    f"mark side-work node or nodeset async if the branch is not part of synchronous flow",
                ],
            )
        )

    for node in graph.nodes:
        if node.name in async_nodes or node.name in reachable_from_start:
            continue
        related = tuple(edge for edge in sync_edges if edge.source == node.name or edge.target == node.name)
        if not related:
            continue
        findings.append(
            _finding(
                "GRAPH.MAINLINE.AMBIGUOUS_SIDE_BRANCH",
                owner,
                related[0],
                f"sync node '{node.name}' is not covered by any inferred mainline path",
                attempted=EDGE_CLASS_MAINLINE,
                mainline_path=_first_mainline_path(starts, ends, mainline_edges),
                branch_nodes=[node.name],
                branch_edges=list(related),
                async_nodes_seen=async_nodes,
                suggested_fixes=[
                    f"connect '{node.name}' into the synchronous mainline",
                    f"mark '{node.name}' or its nodeset call async if it is side work",
                    "remove the side branch if it is only an unused data dependency sketch",
                ],
            )
        )
    return tuple(findings)


def _fanout_has_explicit_join(
    outgoing: Sequence[EdgeSpec],
    schedule_outgoing: Mapping[str, Sequence[EdgeSpec]],
    nodes_by_name: Mapping[str, object],
) -> bool:
    branch_reachable = [
        _walk({edge.target}, schedule_outgoing) | {edge.target}
        for edge in outgoing
    ]
    if len(branch_reachable) <= 1:
        return False
    common = set.intersection(*branch_reachable)
    for name in sorted(common):
        node = nodes_by_name.get(name)
        if getattr(node, "join_policy", "") == JOIN_POLICY_ALL:
            return True
    return False


def _start_nodes(graph: GraphConfig, edges: tuple[EdgeSpec, ...], flow_kinds: Mapping[str, str], async_nodes: set[str]) -> set[str]:
    incoming = _incoming(edges)
    starts = {
        node.name
        for node in graph.nodes
        if node.name not in async_nodes and flow_kinds.get(node.name) == FLOW_KIND_TERMINAL and not incoming.get(node.name)
    }
    if starts:
        return starts
    return {node.name for node in graph.nodes[:1] if node.name not in async_nodes}


def _end_nodes(graph: GraphConfig, edges: tuple[EdgeSpec, ...], flow_kinds: Mapping[str, str], async_nodes: set[str]) -> set[str]:
    outgoing = _outgoing(edges)
    ends = {
        node.name
        for node in graph.nodes
        if node.name not in async_nodes and flow_kinds.get(node.name) == FLOW_KIND_TERMINAL and not outgoing.get(node.name)
    }
    if ends:
        return ends
    for node in reversed(graph.nodes):
        if node.name not in async_nodes:
            return {node.name}
    return set()


def _finding(
    rule_id: str,
    owner: str,
    edge: EdgeSpec,
    why_invalid: str,
    *,
    attempted: str,
    mainline_path: Sequence[str],
    branch_nodes: Sequence[str],
    branch_edges: Sequence[EdgeSpec],
    async_nodes_seen: set[str],
    suggested_fixes: Sequence[str],
) -> MainlineFinding:
    details = {
        "owner": owner,
        "source": edge.source,
        "target": edge.target,
        "edge": _edge_summary(edge),
        "edge_classification_attempted": attempted,
        "mainline_path": list(mainline_path),
        "mainline_variant": list(mainline_path),
        "branch_nodes": list(branch_nodes),
        "branch_edges": [_edge_summary(item) for item in branch_edges],
        "async_nodes_seen": sorted(async_nodes_seen),
        "why_invalid": why_invalid,
        "suggested_fixes": list(suggested_fixes),
    }
    return MainlineFinding(rule_id=rule_id, source=edge.source, target=edge.target, message=why_invalid, details=details)


def _edge_summary(edge: EdgeSpec) -> dict[str, str]:
    payload = {"from": edge.source, "to": edge.target}
    if edge.when:
        payload["when"] = edge.when
    return payload


def _outgoing(edges: tuple[EdgeSpec, ...]) -> dict[str, tuple[EdgeSpec, ...]]:
    grouped: dict[str, list[EdgeSpec]] = {}
    for edge in edges:
        grouped.setdefault(edge.source, []).append(edge)
    return {key: tuple(value) for key, value in grouped.items()}


def _incoming(edges: tuple[EdgeSpec, ...]) -> dict[str, tuple[EdgeSpec, ...]]:
    grouped: dict[str, list[EdgeSpec]] = {}
    for edge in edges:
        grouped.setdefault(edge.target, []).append(edge)
    return {key: tuple(value) for key, value in grouped.items()}


def _walk(starts: set[str], outgoing: Mapping[str, Sequence[EdgeSpec]]) -> set[str]:
    seen: set[str] = set()
    pending = list(starts)
    while pending:
        node = pending.pop(0)
        for edge in outgoing.get(node, ()):
            if edge.target in seen:
                continue
            seen.add(edge.target)
            pending.append(edge.target)
    return seen


def _reverse_reachable(ends: set[str], edges: tuple[EdgeSpec, ...]) -> set[str]:
    incoming = _incoming(edges)
    seen: set[str] = set()
    pending = list(ends)
    while pending:
        node = pending.pop(0)
        for edge in incoming.get(node, ()):
            if edge.source in seen:
                continue
            seen.add(edge.source)
            pending.append(edge.source)
    return seen | ends


def _path_between(source: str, target: str, edges: tuple[EdgeSpec, ...], *, excluded_pair: tuple[str, str] | None = None) -> list[str]:
    outgoing = _outgoing(tuple(edge for edge in edges if edge.pair != excluded_pair))
    pending: list[tuple[str, list[str]]] = [(source, [source])]
    seen = {source}
    while pending:
        node, path = pending.pop(0)
        for edge in outgoing.get(node, ()):
            if edge.target == target:
                return [*path, target]
            if edge.target in seen:
                continue
            seen.add(edge.target)
            pending.append((edge.target, [*path, edge.target]))
    return []


def _first_mainline_path(starts: set[str], ends: set[str], edges: tuple[EdgeSpec, ...]) -> list[str]:
    for start in sorted(starts):
        for end in sorted(ends):
            path = _path_between(start, end, edges)
            if path:
                return path
    return sorted(starts)
