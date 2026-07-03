from __future__ import annotations

from vibeflow import HealthFinding, PluginInfo


class PolicyPlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_policy",
        plugin_type="policy",
        display_name="Sandbox Policy",
        category="policy",
        description="Adds sandbox base_lib and maintainability policy.",
        version="0.1.0",
    )
    name = "sandbox_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "base_lib": {
                    "allowed_paths": ["../base_lib"],
                    "allowed_modules": ["base_lib"],
                },
                "maintainability": {
                    "warn_call_chain_length": 4,
                    "max_call_chain_length": 4,
                    "warn_dependency_chain_length": 4,
                    "max_dependency_chain_length": 6,
                },
            }
        }


class FindingPlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_finding",
        plugin_type="policy",
        display_name="Sandbox Finding",
        category="policy",
        description="Adds sandbox graph and node findings.",
        version="0.1.0",
    )
    name = "sandbox_finding"
    priority = 20

    def validate_node(self, spec, node_cls, metrics):
        if spec.name == "add":
            return [
                HealthFinding(
                    rule_id="SANDBOX.PLUGIN.NODE_WARNING",
                    severity="warning",
                    object_type="node",
                    object_id=spec.name,
                    failure_layer="plugin",
                    message="sandbox plugin warning",
                    suggested_fix_type="fix_node",
                )
            ]
        return []

    def validate_graph(self, graph, compiled):
        return [
            HealthFinding(
                rule_id="SANDBOX.PLUGIN.GRAPH_WARNING",
                severity="warning",
                object_type="pipeline",
                object_id="pipeline",
                failure_layer="plugin",
                message="sandbox graph plugin warning",
                suggested_fix_type="fix_config",
            )
        ]
