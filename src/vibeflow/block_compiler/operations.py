"""Attach fixed workflow operation facts to prepared calls."""
from dataclasses import replace
from .model import freeze_json_object
from vibeflow.core.workflows.operations import operations_by_path


def apply_workflow_operations(plan, graph, descriptor):
    facts = operations_by_path(graph, descriptor)
    return replace(plan, blocks=tuple(replace(block, nodes=tuple(
        replace(call, workflow_operations=freeze_json_object({"actions": facts.get((*block.path, call.id), ())}))
        for call in block.nodes)) for block in plan.blocks))
