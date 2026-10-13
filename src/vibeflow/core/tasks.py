"""Finite task-call declarations, independent of executors and live handles."""
from dataclasses import replace
from vibeflow.core.flow import GraphConfig, NodeSpec
from vibeflow.core.contracts import PipelineInputSpec


def call_specs(nodes):
    """Visit declarations, including explicitly owned task targets."""
    for node in nodes:
        yield node
        yield from call_specs(node.task_targets.values())


def task_graph(parent: GraphConfig, target: NodeSpec) -> GraphConfig:
    return replace(parent, nodes=(target,), edges=(), outputs=(),
                   inputs=tuple(PipelineInputSpec(key=r.type, type=r.type,
                       required=r.cardinality == "exactly_one") for r in target.requires),
                   execution_lock=None, task_entry=target.id)
