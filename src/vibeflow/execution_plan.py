from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .block_compiler import CompiledBlock, compile_blocks
from .compiler import CompiledGraph
from .data_contract import DataProvider, DataRequirement, provider_keys, requirement_types
from .graph_config import EdgeSpec, GraphConfig, LOOP_NODE_TYPES, LoopSpec, NodeSpec
from .node import FLOW_KIND_PREDEFINED, PureNode
from .planned_behavior import (
    PLANNED_BEHAVIOR_PYTHON_STUB,
    PlannedBehavior,
    blocking_planned_behavior,
    effective_planned_behavior,
    hash_file,
    resolve_stub_module_path,
)
from .registry import NodeRegistry
from .runtime_config import (
    ConfigScope,
    attach_global_config,
    merge_config_scopes,
    nested_node_config_overrides,
    node_invocation_scope,
    normalize_config_scope,
    normalize_node_config_overrides,
    scoped_node_params,
)


@dataclass(frozen=True)
class NodeFrame:
    id: str
    type_used: str
    node: PureNode | None
    requires: tuple[DataRequirement, ...]
    provides: tuple[DataProvider, ...]
    params: Mapping[str, object]
    incoming: tuple[EdgeSpec, ...]
    outgoing: tuple[EdgeSpec, ...]
    flow_kind: str
    is_terminal: bool
    is_nodeset: bool
    transfer_incoming: tuple[EdgeSpec, ...] = ()
    transfer_outgoing: tuple[EdgeSpec, ...] = ()
    is_loop: bool = False
    join_policy: str = ""
    nodeset_type_key: str = ""
    exports: tuple[DataProvider, ...] = ()
    loop_spec: LoopSpec = field(default_factory=LoopSpec)
    async_mode: str = ""
    result_key: str = ""
    subplan: "ExecutionPlan | None" = None
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)
    planned_stub_module: str = ""
    planned_stub_path: str = ""
    planned_stub_hash: str = ""

    @property
    def name(self) -> str:
        return self.id

    @property
    def node_type(self) -> str:
        return self.type_used

    @property
    def nodeset_name(self) -> str:
        return self.nodeset_type_key

    @property
    def is_planned_stub(self) -> bool:
        return self.planned_behavior.kind == PLANNED_BEHAVIOR_PYTHON_STUB

    @property
    def require_types(self) -> tuple[str, ...]:
        return requirement_types(self.requires)

    @property
    def provide_keys(self) -> tuple[str, ...]:
        return provider_keys(self.provides)

    @property
    def export_keys(self) -> tuple[str, ...]:
        return provider_keys(self.exports)


@dataclass(frozen=True)
class ExecutionPlan:
    graph: GraphConfig
    compiled: CompiledGraph
    frames: Mapping[str, NodeFrame]
    order: tuple[str, ...]
    max_steps: int
    blocks: tuple[CompiledBlock, ...] = ()
    block_by_entry: Mapping[str, CompiledBlock] | None = None
    compiled_blocks: tuple[CompiledBlock, ...] = ()
    compiled_block_by_entry: Mapping[str, CompiledBlock] | None = None
    compiled_node_to_block: Mapping[str, CompiledBlock] | None = None

    def frame(self, name: str) -> NodeFrame:
        return self.frames[name]

    def block_for(self, name: str) -> CompiledBlock | None:
        return (self.compiled_block_by_entry or self.block_by_entry or {}).get(name)


def build_execution_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    registry: NodeRegistry,
    node_config_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    global_config: Mapping[str, Any] | ConfigScope | None = None,
    runtime_options: object | None = None,
) -> ExecutionPlan:
    overrides = normalize_node_config_overrides(node_config_overrides or {})
    scope = normalize_config_scope(global_config)
    frames = {
        spec.id: _frame_for(spec, graph=graph, compiled=compiled, registry=registry, overrides=overrides, global_scope=scope, runtime_options=runtime_options)
        for spec in graph.nodes
    }
    order = tuple(node.id for node in graph.nodes)
    plan = ExecutionPlan(graph=graph, compiled=compiled, frames=frames, order=order, max_steps=graph.max_steps)
    blocks = compile_blocks(plan, runtime_options=runtime_options)
    block_by_entry = {block.entry: block for block in blocks}
    node_to_block = {node: block for block in blocks for node in block.nodes}
    return ExecutionPlan(
        graph=graph,
        compiled=compiled,
        frames=frames,
        order=order,
        max_steps=graph.max_steps,
        blocks=blocks,
        block_by_entry=block_by_entry,
        compiled_blocks=blocks,
        compiled_block_by_entry=block_by_entry,
        compiled_node_to_block=node_to_block,
    )


def _frame_for(
    spec: NodeSpec,
    *,
    graph: GraphConfig,
    compiled: CompiledGraph,
    registry: NodeRegistry,
    overrides: Mapping[str, Mapping[str, Any]],
    global_scope: ConfigScope,
    runtime_options: object | None,
) -> NodeFrame:
    schedule_edges = compiled.schedule_edges or compiled.effective_edges
    transfer_edges = compiled.transfer_edges or compiled.effective_edges
    incoming = tuple(edge for edge in schedule_edges if edge.target == spec.id)
    outgoing = tuple(edge for edge in schedule_edges if edge.source == spec.id)
    transfer_incoming = tuple(edge for edge in transfer_edges if edge.target == spec.id)
    transfer_outgoing = tuple(edge for edge in transfer_edges if edge.source == spec.id)
    is_loop = spec.type_used in LOOP_NODE_TYPES
    is_nodeset = spec.type_used in graph.nodesets and not is_loop
    nodeset_type_key = spec.type_used if is_nodeset else ""
    nodeset = graph.nodesets.get(nodeset_type_key) if is_nodeset else None
    flow_kind = compiled.flow_kinds.get(spec.id, "")
    planned_behavior = effective_planned_behavior(spec, nodeset)
    if planned_behavior.kind == PLANNED_BEHAVIOR_PYTHON_STUB:
        return _planned_stub_frame(
            spec,
            graph=graph,
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or (nodeset.flow_kind if nodeset is not None else ""),
            nodeset=nodeset,
            nodeset_type_key=nodeset_type_key,
            behavior=planned_behavior,
            overrides=overrides,
            global_scope=global_scope,
        )
    if is_loop:
        nodeset = graph.nodesets[spec.loop.body]
        nested_overrides = nested_node_config_overrides(spec, overrides)
        subcompiled = _compile_nodeset(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.type_key}")
        caller_values = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
        caller_scope = node_invocation_scope(caller_values, allow_config_override=spec.allow_config_override)
        child_scope = merge_config_scopes(normalize_config_scope(nodeset.global_config), caller_scope)
        return NodeFrame(
            id=spec.id,
            type_used=spec.type_used,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or FLOW_KIND_PREDEFINED,
            is_terminal=False,
            is_nodeset=False,
            is_loop=True,
            join_policy=spec.join_policy,
            nodeset_type_key=nodeset.type_key,
            exports=nodeset.provides,
            loop_spec=spec.loop,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            subplan=build_execution_plan(nodeset.graph, subcompiled, registry=registry, node_config_overrides=nested_overrides, global_config=child_scope, runtime_options=runtime_options),
        )
    if is_nodeset:
        nodeset = graph.nodesets[nodeset_type_key]
        nested_overrides = nested_node_config_overrides(spec, overrides)
        subcompiled = _compile_nodeset(nodeset.graph, registry=registry, owner=f"nodeset:{nodeset.type_key}")
        caller_values = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
        caller_scope = node_invocation_scope(caller_values, allow_config_override=spec.allow_config_override)
        child_scope = merge_config_scopes(normalize_config_scope(nodeset.global_config), caller_scope)
        return NodeFrame(
            id=spec.id,
            type_used=spec.type_used,
            node=None,
            requires=spec.requires,
            provides=spec.provides,
            params={},
            incoming=incoming,
            outgoing=outgoing,
            transfer_incoming=transfer_incoming,
            transfer_outgoing=transfer_outgoing,
            flow_kind=flow_kind or FLOW_KIND_PREDEFINED,
            is_terminal=False,
            is_nodeset=True,
            join_policy=spec.join_policy,
            nodeset_type_key=nodeset_type_key,
            exports=nodeset.provides,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            subplan=build_execution_plan(nodeset.graph, subcompiled, registry=registry, node_config_overrides=nested_overrides, global_config=child_scope, runtime_options=runtime_options),
        )
    node_cls = registry.get(spec.type_used)
    node = node_cls()
    config_spec = registry.get_config_spec(spec.type_used)
    scoped_params = scoped_node_params(spec.params, global_scope, declared_keys=set(config_spec.schema))
    node_params = registry.merge_config(spec.type_used, {**scoped_params, **dict(overrides.get(spec.id, {}))})
    return NodeFrame(
        id=spec.id,
        type_used=spec.type_used,
        node=node,
        requires=spec.requires,
        provides=spec.provides,
        params=attach_global_config(node_params, global_scope.values),
        incoming=incoming,
        outgoing=outgoing,
        transfer_incoming=transfer_incoming,
        transfer_outgoing=transfer_outgoing,
        flow_kind=flow_kind,
        is_terminal=flow_kind == "terminal",
        is_nodeset=False,
        join_policy=spec.join_policy,
        async_mode=spec.async_mode,
        result_key=spec.result_key,
    )


def _planned_stub_frame(
    spec: NodeSpec,
    *,
    graph: GraphConfig,
    incoming: tuple[EdgeSpec, ...],
    outgoing: tuple[EdgeSpec, ...],
    transfer_incoming: tuple[EdgeSpec, ...],
    transfer_outgoing: tuple[EdgeSpec, ...],
    flow_kind: str,
    nodeset: object | None,
    nodeset_type_key: str,
    behavior: PlannedBehavior,
    overrides: Mapping[str, Mapping[str, Any]],
    global_scope: ConfigScope,
) -> NodeFrame:
    params = {**dict(spec.params), **dict(global_scope.values), **dict(overrides.get(spec.id, {}))}
    stub_path = ""
    stub_hash = ""
    try:
        path = resolve_stub_module_path(behavior.stub_module, graph.project_root)
        stub_path = str(path)
        if path.is_file():
            stub_hash = hash_file(path)
    except Exception:
        stub_path = behavior.stub_module
    exports = tuple(getattr(nodeset, "provides", ())) if nodeset is not None else ()
    return NodeFrame(
        id=spec.id,
        type_used=spec.type_used,
        node=None,
        requires=spec.requires,
        provides=spec.provides,
        params=attach_global_config(params, global_scope.values),
        incoming=incoming,
        outgoing=outgoing,
        transfer_incoming=transfer_incoming,
        transfer_outgoing=transfer_outgoing,
        flow_kind=flow_kind,
        is_terminal=flow_kind == "terminal",
        is_nodeset=nodeset is not None,
        join_policy=spec.join_policy,
        nodeset_type_key=nodeset_type_key,
        exports=exports,
        async_mode=spec.async_mode,
        result_key=spec.result_key,
        planned_behavior=behavior,
        planned_stub_module=behavior.stub_module,
        planned_stub_path=stub_path,
        planned_stub_hash=stub_hash,
    )


def _compile_nodeset(graph: GraphConfig, *, registry: NodeRegistry, owner: str) -> CompiledGraph:
    from .compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry, owner=owner)
