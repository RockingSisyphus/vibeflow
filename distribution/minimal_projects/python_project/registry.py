from __future__ import annotations

from vibeflow.targets.python.project import NodeRegistry

from nodes.workflow_nodes import EndNode, InputBoundaryNode, OutputBoundaryNode, ProcessPayloadNode, StartNode


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("minimal.start", StartNode, config_schema={}, config_defaults={})
    registry.register("minimal.input_boundary", InputBoundaryNode, config_schema={}, config_defaults={})
    registry.register("minimal.process_payload", ProcessPayloadNode, config_schema={}, config_defaults={})
    registry.register("minimal.output_boundary", OutputBoundaryNode, config_schema={}, config_defaults={})
    registry.register("minimal.end", EndNode, config_schema={}, config_defaults={})
    return registry
