"""Project a Python ExecutionPlan into the language-neutral BlockPlan IR."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from dataclasses import replace

from vibeflow.block_compiler.compiler import _normalize_source_map, _root_inputs, _root_outputs, _workflow_id
from vibeflow.block_compiler.model import PipelineInputSpec, PipelineOutputSpec, PortablePlanError, SourceRef, WorkflowPlan, freeze_json_object


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


__all__ = ["workflow_plan_from_execution_plan"]
