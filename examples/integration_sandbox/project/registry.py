from __future__ import annotations

from topology_kernel import BoundaryRegistry, NodeRegistry

from boundaries import DemoBoundary
from nodes.legal_boundary_nodes import BoundaryResultAddNode, BoundaryResultInputNode, EffectRequestNode
from nodes.legal_loop_nodes import CopyBackNode, DoneCheckNode, IncrementNode
from nodes.legal_math_nodes import (
    AddNode,
    AddOutNode,
    AddThreeNode,
    BranchLeftNode,
    BranchRightNode,
    ConstantNode,
    MultiplyNode,
    SumPairNode,
)


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("sandbox.constant", ConstantNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.add", AddNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.add_out", AddOutNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.multiply", MultiplyNode, config_schema={"factor": {"type": "number"}}, config_defaults={"factor": 2})
    registry.register("sandbox.branch_left", BranchLeftNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.branch_right", BranchRightNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.sum_pair", SumPairNode, config_schema={}, config_defaults={})
    registry.register("sandbox.add_three", AddThreeNode, config_schema={}, config_defaults={})
    registry.register("sandbox.increment", IncrementNode, config_schema={}, config_defaults={})
    registry.register("sandbox.copy_back", CopyBackNode, config_schema={}, config_defaults={})
    registry.register("sandbox.done_check", DoneCheckNode, config_schema={"target": {"type": "number"}}, config_defaults={"target": 3})
    registry.register("sandbox.effect_request", EffectRequestNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})
    registry.register("sandbox.boundary_result_add", BoundaryResultAddNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    registry.register("sandbox.boundary_result_input", BoundaryResultInputNode, config_schema={"delta": {"type": "number"}}, config_defaults={"delta": 1})
    return registry


def build_boundary_registry() -> BoundaryRegistry:
    registry = BoundaryRegistry()
    registry.register("sandbox.demo_boundary", DemoBoundary)
    return registry
