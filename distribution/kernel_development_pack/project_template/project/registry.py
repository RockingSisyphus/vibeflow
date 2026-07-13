from __future__ import annotations

from vibeflow import BaseLibRegistry, NodeRegistry, PluginResourceRegistry

from nodes.math_nodes import AddNode, EndNode, OutputNode, SeedNode, StartNode


def build_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("demo.start", StartNode, config_schema={}, config_defaults={})
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
    registry.register("demo.output", OutputNode, config_schema={}, config_defaults={})
    registry.register("demo.end", EndNode, config_schema={}, config_defaults={})
    return registry


def build_base_lib_registry() -> BaseLibRegistry:
    registry = BaseLibRegistry()
    registry.register(
        "math_tools",
        module="base_lib.math_tools",
        display_name="Math Tools",
        category="demo",
        description="Pure arithmetic helpers used by the template workflow.",
        version="0.1.0",
    )
    return registry


def build_plugin_registry() -> PluginResourceRegistry:
    registry = PluginResourceRegistry()
    registry.register(
        "project_policy",
        module="plugins.policy",
        class_name="PolicyPlugin",
        plugin_type="policy",
        display_name="Project Policy",
        category="demo",
        description="Template project policy extension for health checks.",
        version="0.1.0",
    )
    return registry
