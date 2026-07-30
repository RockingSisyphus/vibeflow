from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

from vibeflow.compiler import CompiledGraph
from vibeflow.graph_config import GraphConfig, IO_NODE_TYPE, LOOP_NODE_TYPES, LoopSpec, NodeSpec
from vibeflow.graph_config.planned_behavior import effective_planned_behavior
from vibeflow.portable.model import (
    WORKFLOW_ABI_VERSION,
    BlockPlan,
    ConditionPlan,
    DataProviderPlan,
    DataRequirementPlan,
    LoopCarryPlan,
    LoopCollectPlan,
    LoopOutputPlan,
    LoopPlan,
    NodeCallPlan,
    PipelineInputSpec,
    PipelineOutputSpec,
    PortablePlanError,
    RoutePlan,
    SourceRef,
    TaskPlan,
    WorkflowPlan,
    freeze_json_object,
)

if TYPE_CHECKING:
    from vibeflow.runtime.planning import ExecutionPlan, NodeFrame


def normalize_condition(expression: str) -> ConditionPlan | None:
    """Normalize exactly the condition grammar accepted by GraphConfig."""

    text = str(expression).strip()
    if not text:
        return None
    operators = [operator for operator in ("==", "!=") if operator in text]
    if len(operators) != 1:
        raise PortablePlanError(f"condition must use exactly one == or != operator: {expression}")
    operator = operators[0]
    key, literal_text = (part.strip() for part in text.split(operator, 1))
    if not key or not literal_text:
        raise PortablePlanError(f"condition must compare a key to a literal: {expression}")
    if literal_text in {"true", "false"}:
        literal: bool | str = literal_text == "true"
    elif (
        len(literal_text) >= 2
        and literal_text[0] == literal_text[-1]
        and literal_text[0] in {"'", '"'}
    ):
        literal = literal_text[1:-1]
    else:
        raise PortablePlanError(f"condition literal must be true, false, or a quoted string: {expression}")
    return ConditionPlan(key=key, operator=operator, literal=literal)


def build_workflow_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    execution_plan: "ExecutionPlan | None" = None,
    workflow_id: str | None = None,
    source_by_type: Mapping[str, SourceRef] | None = None,
    compiled_by_path: Mapping[tuple[str, ...], CompiledGraph] | None = None,
    params_by_path: Mapping[tuple[str, ...], Mapping[str, object]] | None = None,
    pipeline_inputs: Sequence[PipelineInputSpec] | None = None,
    pipeline_outputs: Sequence[PipelineOutputSpec] | None = None,
) -> WorkflowPlan:
    """Build portable IR from a compiled graph, optionally using bound effective parameters."""

    if execution_plan is not None:
        if execution_plan.graph is not graph or execution_plan.compiled is not compiled:
            raise PortablePlanError("execution plan must have been built from the supplied graph and compiled graph")
        return workflow_plan_from_execution_plan(
            execution_plan,
            workflow_id=workflow_id,
            source_by_type=source_by_type,
            pipeline_inputs=pipeline_inputs,
            pipeline_outputs=pipeline_outputs,
        )
    resolved_inputs = _root_inputs(graph, pipeline_inputs)
    resolved_outputs = _root_outputs(graph, pipeline_outputs)
    state = _PlannerState(
        source_by_type,
        compiled_by_path=compiled_by_path,
        params_by_path=params_by_path,
    )
    root_id = _block_id(())
    state.add_graph_block(graph, compiled, path=(), kind="workflow", loop=None, active_nodesets=())
    return WorkflowPlan(
        abi_version=WORKFLOW_ABI_VERSION,
        workflow_id=_workflow_id(graph, workflow_id),
        source=_graph_source(graph, _workflow_id(graph, workflow_id)),
        entry_block=root_id,
        inputs=resolved_inputs,
        outputs=resolved_outputs,
        blocks=tuple(state.blocks),
        max_steps=graph.max_steps,
        entry_mode=graph.entry_mode,
    )


def workflow_plan_from_execution_plan(
    execution_plan: "ExecutionPlan",
    *,
    workflow_id: str | None = None,
    source_by_type: Mapping[str, SourceRef] | None = None,
    pipeline_inputs: Sequence[PipelineInputSpec] | None = None,
    pipeline_outputs: Sequence[PipelineOutputSpec] | None = None,
) -> WorkflowPlan:
    """Adapt an existing Python execution plan without retaining any Python binding."""

    graph = execution_plan.graph
    resolved_inputs = _root_inputs(graph, pipeline_inputs)
    resolved_outputs = _root_outputs(graph, pipeline_outputs)
    state = _PlannerState(source_by_type)
    root_id = _block_id(())
    state.add_execution_block(execution_plan, path=(), kind="workflow", loop=None)
    resolved_workflow_id = _workflow_id(graph, workflow_id)
    return WorkflowPlan(
        abi_version=WORKFLOW_ABI_VERSION,
        workflow_id=resolved_workflow_id,
        source=_graph_source(graph, resolved_workflow_id),
        entry_block=root_id,
        inputs=resolved_inputs,
        outputs=resolved_outputs,
        blocks=tuple(state.blocks),
        max_steps=execution_plan.max_steps,
        entry_mode=graph.entry_mode,
    )


class _PlannerState:
    def __init__(
        self,
        source_by_type: Mapping[str, SourceRef] | None,
        *,
        compiled_by_path: Mapping[tuple[str, ...], CompiledGraph] | None = None,
        params_by_path: Mapping[tuple[str, ...], Mapping[str, object]] | None = None,
    ) -> None:
        self.source_by_type = dict(source_by_type or {})
        self.compiled_by_path = dict(compiled_by_path or {})
        self.params_by_path = {
            tuple(path): dict(params)
            for path, params in (params_by_path or {}).items()
        }
        self.blocks: list[BlockPlan] = []

    def add_execution_block(
        self,
        execution_plan: "ExecutionPlan",
        *,
        path: tuple[str, ...],
        kind: str,
        loop: LoopPlan | None,
    ) -> None:
        graph = execution_plan.graph
        child_specs: list[tuple[NodeSpec, "NodeFrame", tuple[str, ...], str, LoopPlan | None]] = []
        nodes: list[NodeCallPlan] = []
        for spec in graph.nodes:
            frame = execution_plan.frames[spec.id]
            child_path = (*path, spec.id)
            child_block = _block_id(child_path) if frame.subplan is not None else ""
            nodes.append(self._execution_node(spec, frame, child_block=child_block))
            if frame.subplan is not None:
                child_kind = "loop" if frame.is_loop else "nodeset"
                child_loop = _loop_plan(spec.loop) if frame.is_loop else None
                child_specs.append((spec, frame, child_path, child_kind, child_loop))
        self.blocks.append(
            _block(
                graph,
                execution_plan.compiled,
                path=path,
                kind=kind,
                loop=loop,
                nodes=tuple(nodes),
            )
        )
        for _spec, frame, child_path, child_kind, child_loop in child_specs:
            if frame.subplan is None:
                continue
            self.add_execution_block(
                frame.subplan,
                path=child_path,
                kind=child_kind,
                loop=child_loop,
            )

    def add_graph_block(
        self,
        graph: GraphConfig,
        compiled: CompiledGraph,
        *,
        path: tuple[str, ...],
        kind: str,
        loop: LoopPlan | None,
        active_nodesets: tuple[str, ...],
    ) -> None:
        children: list[tuple[GraphConfig, CompiledGraph, tuple[str, ...], str, LoopPlan | None, tuple[str, ...]]] = []
        nodes: list[NodeCallPlan] = []
        for spec in graph.nodes:
            is_loop = spec.type_used in LOOP_NODE_TYPES
            is_nodeset = spec.type_used in graph.nodesets and not is_loop
            nodeset = graph.nodesets.get(spec.loop.body if is_loop else spec.type_used) if (is_loop or is_nodeset) else None
            behavior = effective_planned_behavior(spec, nodeset)
            has_child = nodeset is not None and behavior.kind != "python_stub"
            child_path = (*path, spec.id)
            child_block = _block_id(child_path) if has_child else ""
            nodes.append(
                self._graph_node(
                    spec,
                    compiled=compiled,
                    nodeset=nodeset,
                    is_loop=is_loop,
                    is_nodeset=is_nodeset,
                    child_block=child_block,
                    planned_behavior=behavior.kind,
                    call_path=child_path,
                )
            )
            if not has_child or nodeset is None:
                continue
            if nodeset.type_key in active_nodesets:
                chain = " -> ".join((*active_nodesets, nodeset.type_key))
                raise PortablePlanError(f"recursive nodeset reference cannot be represented as finite blocks: {chain}")
            child_compiled = self.compiled_by_path.get(child_path)
            if child_compiled is None:
                raise PortablePlanError(
                    f"nested block {_block_id(child_path)} requires an execution plan or compiled_by_path entry"
                )
            child_kind = "loop" if is_loop else "nodeset"
            child_loop = _loop_plan(spec.loop) if is_loop else None
            children.append(
                (
                    nodeset.graph,
                    child_compiled,
                    child_path,
                    child_kind,
                    child_loop,
                    (*active_nodesets, nodeset.type_key),
                )
            )
        self.blocks.append(_block(graph, compiled, path=path, kind=kind, loop=loop, nodes=tuple(nodes)))
        for child_graph, child_compiled, child_path, child_kind, child_loop, child_active in children:
            self.add_graph_block(
                child_graph,
                child_compiled,
                path=child_path,
                kind=child_kind,
                loop=child_loop,
                active_nodesets=child_active,
            )

    def _execution_node(self, spec: NodeSpec, frame: "NodeFrame", *, child_block: str) -> NodeCallPlan:
        return NodeCallPlan(
            id=spec.id,
            type_used=spec.type_used,
            implementation=self._source(spec.type_used),
            requires=_requirements(frame.requires),
            provides=_providers(frame.provides),
            params=freeze_json_object(frame.params, path=f"node[{spec.id}].params"),
            config_overrides=freeze_json_object(
                spec.node_config_overrides,
                path=f"node[{spec.id}].node_config_overrides",
            ),
            flow_kind=frame.flow_kind,
            join_policy=frame.join_policy,
            status=spec.status,
            planned_behavior=frame.planned_behavior.kind,
            async_mode=frame.async_mode,
            result_key=frame.result_key,
            is_terminal=frame.is_terminal,
            is_nodeset=frame.is_nodeset,
            is_loop=frame.is_loop,
            nodeset_type_key=frame.nodeset_type_key,
            child_block=child_block,
            exports=_providers(frame.exports),
            allow_config_override=spec.allow_config_override,
            display_name=spec.metadata.display_name,
            description=spec.metadata.description,
            completion=(
                "suspend"
                if spec.type_used == IO_NODE_TYPE
                and spec.io.operation == "receive"
                else "immediate"
            ),
            schedule=_schedule(frame.async_mode),
            executor=(
                "event_loop"
                if spec.type_used == IO_NODE_TYPE
                and spec.io.operation == "receive"
                else _executor(frame.async_mode)
            ),
            io_operation=spec.io.operation,
            io_port=spec.io.port if spec.io.operation else "",
        )

    def _graph_node(
        self,
        spec: NodeSpec,
        *,
        compiled: CompiledGraph,
        nodeset: object | None,
        is_loop: bool,
        is_nodeset: bool,
        child_block: str,
        planned_behavior: str,
        call_path: tuple[str, ...],
    ) -> NodeCallPlan:
        exports = tuple(getattr(nodeset, "provides", ())) if nodeset is not None else ()
        nodeset_type_key = str(getattr(nodeset, "type_key", ""))
        flow_kind = compiled.flow_kinds.get(spec.id, spec.flow_kind)
        return NodeCallPlan(
            id=spec.id,
            type_used=spec.type_used,
            implementation=self._source(spec.type_used),
            requires=_requirements(spec.requires),
            provides=_providers(spec.provides),
            params=freeze_json_object(
                self.params_by_path.get(call_path, spec.params),
                path=f"node[{'.'.join(call_path)}].params",
            ),
            config_overrides=freeze_json_object(
                spec.node_config_overrides,
                path=f"node[{spec.id}].node_config_overrides",
            ),
            flow_kind=flow_kind,
            join_policy=spec.join_policy,
            status=spec.status,
            planned_behavior=planned_behavior,
            async_mode=spec.async_mode,
            result_key=spec.result_key,
            is_terminal=(
                flow_kind == "terminal"
                or spec.type_used == IO_NODE_TYPE
            ),
            is_nodeset=is_nodeset,
            is_loop=is_loop,
            nodeset_type_key=nodeset_type_key,
            child_block=child_block,
            exports=_providers(exports),
            allow_config_override=spec.allow_config_override,
            display_name=spec.metadata.display_name,
            description=spec.metadata.description,
            completion=(
                "suspend"
                if spec.type_used == IO_NODE_TYPE
                and spec.io.operation == "receive"
                else "immediate"
            ),
            schedule=_schedule(spec.async_mode),
            executor=(
                "event_loop"
                if spec.type_used == IO_NODE_TYPE
                and spec.io.operation == "receive"
                else _executor(spec.async_mode)
            ),
            io_operation=spec.io.operation,
            io_port=spec.io.port if spec.io.operation else "",
        )

    def _source(self, type_used: str) -> SourceRef:
        return self.source_by_type.get(type_used, SourceRef(kind="catalog", ref=type_used))


def _block(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    path: tuple[str, ...],
    kind: str,
    loop: LoopPlan | None,
    nodes: tuple[NodeCallPlan, ...],
) -> BlockPlan:
    routes = _routes(compiled)
    incoming = {route.target for route in routes if route.schedule}
    outgoing = {route.source for route in routes if route.schedule}
    terminal_by_id = {node.id: node.is_terminal for node in nodes}
    entries = tuple(node_id for node_id in compiled.order if node_id not in incoming and terminal_by_id.get(node_id, False))
    exits = tuple(node_id for node_id in compiled.order if node_id not in outgoing and terminal_by_id.get(node_id, False))
    return BlockPlan(
        id=_block_id(path),
        kind=kind,
        path=path,
        source=_graph_source(graph, _block_id(path)),
        inputs=_legacy_inputs(graph),
        outputs=_legacy_outputs(graph),
        nodes=nodes,
        routes=routes,
        order=compiled.order,
        entries=entries,
        exits=exits,
        max_steps=graph.max_steps,
        tasks=tuple(
            TaskPlan(
                id=f"{_block_id(path)}:task:{node.id}",
                node_id=node.id,
                schedule=node.schedule,
                executor=node.executor,
                result_key=node.result_key,
            )
            for node in nodes
            if node.schedule != "inline"
        ),
        loop=loop,
    )


def _routes(compiled: CompiledGraph) -> tuple[RoutePlan, ...]:
    schedule_edges = compiled.resolved_schedule_edges
    transfer_edges = compiled.resolved_transfer_edges
    schedule_pairs = {edge.pair for edge in schedule_edges}
    transfer_pairs = {edge.pair for edge in transfer_edges}
    explicit_pairs = {edge.pair for edge in compiled.explicit_edges}
    mainline_pairs = {edge.pair for edge in compiled.mainline_edges}
    bypass_pairs = {edge.pair for edge in compiled.data_bypass_edges}
    async_pairs = {edge.pair for edge in compiled.async_edges}
    return tuple(
        RoutePlan(
            source=edge.source,
            target=edge.target,
            condition=normalize_condition(edge.when),
            schedule=edge.pair in schedule_pairs,
            transfer=edge.pair in transfer_pairs,
            explicit=edge.pair in explicit_pairs,
            mainline=edge.pair in mainline_pairs,
            data_bypass=edge.pair in bypass_pairs,
            asynchronous=edge.pair in async_pairs,
        )
        for edge in compiled.effective_edges
    )


def _loop_plan(spec: LoopSpec) -> LoopPlan:
    stop_when = (
        ConditionPlan(key=spec.stop_when.source, operator="==", literal=spec.stop_when.equals)
        if spec.stop_when.source
        else None
    )
    return LoopPlan(
        body_type_key=spec.body,
        max_iterations=spec.max_iterations,
        stop_after=spec.stop_after or None,
        stop_when=stop_when,
        carry=tuple(LoopCarryPlan(item.source, item.target, item.update) for item in spec.carry),
        collect=tuple(LoopCollectPlan(item.source, item.target, item.mode) for item in spec.collect),
        outputs=tuple(LoopOutputPlan(item.source, item.target) for item in spec.outputs),
    )


def _schedule(async_mode: str) -> str:
    if async_mode == "result_key":
        return "deferred"
    if async_mode == "detached":
        return "detached"
    return "inline"


def _executor(async_mode: str) -> str:
    return "thread" if async_mode else "current"


def _providers(items: Sequence[object]) -> tuple[DataProviderPlan, ...]:
    return tuple(
        DataProviderPlan(
            key=str(getattr(item, "key", "")),
            type=str(getattr(item, "type", "")),
            display_name=str(getattr(item, "display_name", "")),
        )
        for item in items
    )


def _requirements(items: Sequence[object]) -> tuple[DataRequirementPlan, ...]:
    return tuple(
        DataRequirementPlan(
            type=str(getattr(item, "type", "")),
            cardinality=str(getattr(item, "cardinality", "")),
            display_name=str(getattr(item, "display_name", "")),
        )
        for item in items
    )


def _legacy_inputs(graph: GraphConfig) -> tuple[PipelineInputSpec, ...]:
    return tuple(
        PipelineInputSpec(
            key=item.key,
            type=item.type,
            required=getattr(item, "required", None),
            display_name=item.display_name,
        )
        for item in graph.inputs
    )


def _legacy_outputs(graph: GraphConfig) -> tuple[PipelineOutputSpec, ...]:
    return tuple(
        PipelineOutputSpec(
            type=item.type,
            cardinality=item.cardinality,
            as_key=str(getattr(item, "public_name", "") or getattr(item, "alias", "") or item.type),
            display_name=item.display_name,
        )
        for item in graph.outputs
    )


def _root_inputs(
    graph: GraphConfig,
    supplied: Sequence[PipelineInputSpec] | None,
) -> tuple[PipelineInputSpec, ...]:
    values = tuple(supplied) if supplied is not None else _legacy_inputs(graph)
    expected = tuple((item.key, item.type) for item in graph.inputs)
    actual = tuple((item.key, item.type) for item in values)
    if actual != expected:
        raise PortablePlanError("portable pipeline inputs must match GraphConfig input key/type order")
    return values


def _root_outputs(
    graph: GraphConfig,
    supplied: Sequence[PipelineOutputSpec] | None,
) -> tuple[PipelineOutputSpec, ...]:
    values = tuple(supplied) if supplied is not None else _legacy_outputs(graph)
    expected = tuple((item.type, item.cardinality) for item in graph.outputs)
    actual = tuple((item.type, item.cardinality) for item in values)
    if actual != expected:
        raise PortablePlanError("portable pipeline outputs must match GraphConfig output type/cardinality order")
    return values


def _workflow_id(graph: GraphConfig, supplied: str | None) -> str:
    if supplied is not None and supplied.strip():
        return supplied.strip()
    if graph.source_path:
        return Path(graph.source_path).stem
    return graph.root_id or "workflow"


def _graph_source(graph: GraphConfig, fallback: str) -> SourceRef:
    if graph.source_path:
        return SourceRef(kind="config", ref=graph.source_path)
    if graph.root_path:
        return SourceRef(kind="config_root", ref=graph.root_path)
    return SourceRef(kind="graph", ref=fallback)


def _block_id(path: tuple[str, ...]) -> str:
    if not path:
        return "block:/"
    escaped = (part.replace("~", "~0").replace("/", "~1") for part in path)
    return "block:/" + "/".join(escaped)
