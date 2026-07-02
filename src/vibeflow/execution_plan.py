from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .compiler import CompiledGraph
from .graph_config import EdgeSpec, GraphConfig, NodeSpec
from .node import FLOW_KIND_PREDEFINED, PureNode
from .registry import NodeRegistry
from .runtime_config import effective_node_params, nested_node_config_overrides, normalize_node_config_overrides


@dataclass(frozen=True)
class NodeFrame:
    name: str
    node_type: str
    node: PureNode | None
    requires: tuple[str, ...]
    provides: tuple[str, ...]
    params: Mapping[str, object]
    incoming: tuple[EdgeSpec, ...]
    outgoing: tuple[EdgeSpec, ...]
    flow_kind: str
    is_terminal: bool
    is_nodeset: bool
    nodeset_name: str = ""
    exports: tuple[str, ...] = ()
    async_mode: str = ""
    result_key: str = ""
    subplan: "ExecutionPlan | None" = None


@dataclass(frozen=True)
class ExecutionPlan:
    graph: GraphConfig
    compiled: CompiledGraph
    frames: Mapping[str, NodeFrame]
    order: tuple[str, ...]
    max_steps: int

    def frame(self, name: str) -> NodeFrame:
        return self.frames[name]


def build_execution_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: NodeRegistry,
    node_config_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> ExecutionPlan:
    overrides = normalize_node_config_overrides(node_config_overrides or {})
    frames = {
        spec.name: _frame_for(spec, graph=graph, compiled=compiled, registry=registry, overrides=overrides)
        for spec in graph.nodes
    }
    return ExecutionPlan(graph=graph, compiled=compiled, frames=frames, order=tuple(node.name for node in graph.nodes), max_steps=graph.max_steps)


def _frame_for(
    spec: NodeSpec,
    *,
    graph: GraphConfig,
    compiled: CompiledGraph,
    registry: NodeRegistry,
    overrides: Mapping[str, Mapping[str, Any]],
) -> NodeFrame:
    incoming = tuple(edge for edge in compiled.effective_edges if edge.target == spec.name)
    outgoing = tuple(edge for edge in compiled.effective_edges if edge.source == spec.name)
    is_nodeset = spec.node_type.startswith("nodeset.")
    nodeset_name = spec.node_type.removeprefix("nodeset.") if is_nodeset else ""
    flow_kind = compiled.flow_kinds.get(spec.name, "")
    if is_nodeset:
        nodeset = graph.nodesets[nodeset_name]
        nested_overrides = nested_node_config_overrides(spec, overrides)
        subcompiled = _compile_nodeset(nodeset.graph, registry=registry)
        return NodeFrame(
            name=spec.name,
            node_type=spec.node_type,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            flow_kind=flow_kind or FLOW_KIND_PREDEFINED,
            is_terminal=False,
            is_nodeset=True,
            nodeset_name=nodeset_name,
            exports=nodeset.exports,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            subplan=build_execution_plan(nodeset.graph, subcompiled, registry=registry, node_config_overrides=nested_overrides),
        )
    node_cls = registry.get(spec.node_type)
    node = node_cls()
    return NodeFrame(
        name=spec.name,
        node_type=spec.node_type,
        node=node,
        requires=spec.requires,
        provides=spec.provides,
        params=registry.merge_config(spec.node_type, effective_node_params(spec, overrides)),
        incoming=incoming,
        outgoing=outgoing,
        flow_kind=flow_kind,
        is_terminal=flow_kind == "terminal",
        is_nodeset=False,
        async_mode=spec.async_mode,
        result_key=spec.result_key,
    )


def _compile_nodeset(graph: GraphConfig, *, registry: NodeRegistry) -> CompiledGraph:
    from .compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry)
