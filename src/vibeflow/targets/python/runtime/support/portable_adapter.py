"""Project a Python ExecutionPlan into the language-neutral BlockPlan IR."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from dataclasses import replace

from vibeflow.block_compiler.compiler import _normalize_source_map, _root_inputs, _root_outputs, _workflow_id, compile_graph_plan
from vibeflow.block_compiler.model import PipelineInputSpec, PipelineOutputSpec, PortablePlanError, SourceRef, WorkflowPlan, freeze_json_object
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig


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
    """Expose the common plan, adding the native call parameters on request."""
    from vibeflow.block_compiler import workflow_subplan
    original = execution_plan.workflow_plan
    if original is None:
        raise PortablePlanError("execution plan has no prepared workflow")
    original = workflow_subplan(original, execution_plan.python_bindings.block_id)
    sources = _normalize_source_map(source_by_type)
    frames_by_path = {}
    def collect(native, block_id):
        block = original.block(block_id)
        for call in block.nodes:
            frame = native.frames[call.id]
            frames_by_path[(*block.path,call.id)] = frame
            if call.child_block:
                collect(frame.subplan,call.child_block)
    collect(execution_plan, original.entry_block)
    blocks = []
    for block in original.blocks:
        calls = []
        for call in block.nodes:
            frame = frames_by_path[(*block.path,call.id)]
            calls.append(replace(call, implementation=sources.get(call.type_used,call.implementation),
                params=freeze_json_object(frame.params,path=f"node[{call.id}].params")))
        blocks.append(replace(block,nodes=tuple(calls)))
    graph = execution_plan.graph
    return replace(original,workflow_id=_workflow_id(graph,workflow_id),blocks=tuple(blocks),
        inputs=_root_inputs(graph,pipeline_inputs),outputs=_root_outputs(graph,pipeline_outputs),entry_mode=graph.entry_mode)


def execution_plan_effect_scope(frame: Any) -> str:
    return str(getattr(frame, "effect_scope", "unconstrained"))


__all__ = ["build_workflow_plan", "workflow_plan_from_execution_plan"]
