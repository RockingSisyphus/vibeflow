"""Project a Python ExecutionPlan into the language-neutral BlockPlan IR."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from vibeflow.block_compiler.compiler import (
    _block,
    _block_id,
    _executor,
    _graph_source,
    _loop_plan,
    _normalize_source_map,
    _providers,
    _requirements,
    _root_inputs,
    _root_outputs,
    _schedule,
    _workflow_id,
    compile_graph_plan,
)
from vibeflow.block_compiler.model import (
    WORKFLOW_ABI_VERSION,
    LoopPlan,
    NodeCallPlan,
    PipelineInputSpec,
    PipelineOutputSpec,
    PortablePlanError,
    SourceRef,
    WorkflowPlan,
    freeze_json_object,
)
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import IO_NODE_TYPE, GraphConfig, NodeSpec


def build_workflow_plan(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    execution_plan: Any | None = None,
    workflow_id: str | None = None,
    source_by_type: Mapping[str, SourceRef] | None = None,
    compiled_by_path: Mapping[tuple[str, ...], CompiledGraph] | None = None,
    params_by_path: Mapping[tuple[str, ...], Mapping[str, object]] | None = None,
    pipeline_inputs: Sequence[PipelineInputSpec] | None = None,
    pipeline_outputs: Sequence[PipelineOutputSpec] | None = None,
) -> WorkflowPlan:
    """Preserve the historical graph/ExecutionPlan planning interface."""

    if execution_plan is not None:
        if execution_plan.graph is not graph or execution_plan.compiled is not compiled:
            raise PortablePlanError(
                "execution plan must have been built from the supplied graph "
                "and compiled graph"
            )
        return workflow_plan_from_execution_plan(
            execution_plan,
            workflow_id=workflow_id,
            source_by_type=source_by_type,
            pipeline_inputs=pipeline_inputs,
            pipeline_outputs=pipeline_outputs,
        )
    return compile_graph_plan(
        graph,
        compiled,
        workflow_id=workflow_id,
        source_by_type=source_by_type,
        compiled_by_path=compiled_by_path,
        params_by_path=params_by_path,
        pipeline_inputs=pipeline_inputs,
        pipeline_outputs=pipeline_outputs,
    )


def workflow_plan_from_execution_plan(
    execution_plan: Any,
    *,
    workflow_id: str | None = None,
    source_by_type: Mapping[str, SourceRef] | None = None,
    pipeline_inputs: Sequence[PipelineInputSpec] | None = None,
    pipeline_outputs: Sequence[PipelineOutputSpec] | None = None,
) -> WorkflowPlan:
    """Project an ExecutionPlan without retaining Python live objects."""

    graph = execution_plan.graph
    resolved_inputs = _root_inputs(graph, pipeline_inputs)
    resolved_outputs = _root_outputs(graph, pipeline_outputs)
    adapter = _ExecutionPlanAdapter(source_by_type)
    adapter.add_block(execution_plan, path=(), kind="workflow", loop=None)
    resolved_workflow_id = _workflow_id(graph, workflow_id)
    return WorkflowPlan(
        abi_version=WORKFLOW_ABI_VERSION,
        workflow_id=resolved_workflow_id,
        source=_graph_source(graph, resolved_workflow_id),
        entry_block=_block_id(()),
        inputs=resolved_inputs,
        outputs=resolved_outputs,
        blocks=tuple(adapter.blocks),
        max_steps=execution_plan.max_steps,
        entry_mode=graph.entry_mode,
    )


class _ExecutionPlanAdapter:
    def __init__(
        self,
        source_by_type: Mapping[str, SourceRef] | None,
    ) -> None:
        self.source_by_type = _normalize_source_map(source_by_type)
        self.blocks = []

    def add_block(
        self,
        execution_plan: Any,
        *,
        path: tuple[str, ...],
        kind: str,
        loop: LoopPlan | None,
    ) -> None:
        graph = execution_plan.graph
        children: list[
            tuple[Any, tuple[str, ...], str, LoopPlan | None]
        ] = []
        nodes: list[NodeCallPlan] = []
        for spec in graph.nodes:
            frame = execution_plan.frames[spec.id]
            child_path = (*path, spec.id)
            child_block = (
                _block_id(child_path) if frame.subplan is not None else ""
            )
            nodes.append(self._node(spec, frame, child_block=child_block))
            if frame.subplan is not None:
                child_kind = "loop" if frame.is_loop else "nodeset"
                child_loop = _loop_plan(spec.loop) if frame.is_loop else None
                children.append(
                    (frame.subplan, child_path, child_kind, child_loop)
                )
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
        for subplan, child_path, child_kind, child_loop in children:
            self.add_block(
                subplan,
                path=child_path,
                kind=child_kind,
                loop=child_loop,
            )

    def _node(
        self,
        spec: NodeSpec,
        frame: Any,
        *,
        child_block: str,
    ) -> NodeCallPlan:
        is_receive = (
            spec.type_used == IO_NODE_TYPE
            and spec.io.operation == "receive"
        )
        return NodeCallPlan(
            id=spec.id,
            type_used=spec.type_used,
            implementation=self.source_by_type.get(
                spec.type_used,
                SourceRef(kind="catalog", ref=spec.type_used),
            ),
            requires=_requirements(frame.requires),
            provides=_providers(frame.provides),
            params=freeze_json_object(
                frame.params,
                path=f"node[{spec.id}].params",
            ),
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
            completion="suspend" if is_receive else "immediate",
            schedule=_schedule(frame.async_mode),
            executor=(
                "event_loop" if is_receive else _executor(frame.async_mode)
            ),
            io_operation=spec.io.operation,
            io_port=spec.io.port if spec.io.operation else "",
        )


__all__ = ["build_workflow_plan", "workflow_plan_from_execution_plan"]
