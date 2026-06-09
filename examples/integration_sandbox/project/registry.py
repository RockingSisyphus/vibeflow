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
    registry.register("sandbox.constant", ConstantNode)
    registry.register("sandbox.add", AddNode)
    registry.register("sandbox.add_out", AddOutNode)
    registry.register("sandbox.multiply", MultiplyNode)
    registry.register("sandbox.branch_left", BranchLeftNode)
    registry.register("sandbox.branch_right", BranchRightNode)
    registry.register("sandbox.sum_pair", SumPairNode)
    registry.register("sandbox.add_three", AddThreeNode)
    registry.register("sandbox.increment", IncrementNode)
    registry.register("sandbox.copy_back", CopyBackNode)
    registry.register("sandbox.done_check", DoneCheckNode)
    registry.register("sandbox.effect_request", EffectRequestNode)
    registry.register("sandbox.boundary_result_add", BoundaryResultAddNode)
    registry.register("sandbox.boundary_result_input", BoundaryResultInputNode)
    return registry


def build_boundary_registry() -> BoundaryRegistry:
    registry = BoundaryRegistry()
    registry.register("sandbox.demo_boundary", DemoBoundary)
    return registry
