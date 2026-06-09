from __future__ import annotations

from topology_kernel import BoundaryRegistry, NodeRegistry

from boundaries import DemoBoundary
from nodes.math_nodes import AddNode, SeedNode


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register(
        "demo.seed",
        SeedNode,
        config_schema={"value": {"type": "number"}},
        config_defaults={"value": 1},
    )
    registry.register(
        "demo.add",
        AddNode,
        config_schema={"delta": {"type": "number"}},
        config_defaults={"delta": 1},
    )
    return registry


def build_boundary_registry() -> BoundaryRegistry:
    registry = BoundaryRegistry()
    registry.register("demo.boundary", DemoBoundary)
    return registry

