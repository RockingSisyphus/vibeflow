from __future__ import annotations

from vibeflow import PluginInfo


class Plugin:
    PLUGIN_INFO = PluginInfo(
        name="minimal_project_policy",
        plugin_type="policy",
        display_name="Minimal Project Policy",
        category="policy",
        description="Applies maintainability defaults for the minimal project.",
        version="0.1.0",
    )
    name = "minimal_project_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "maintainability": {
                    "warn_call_chain_length": 4,
                    "max_call_chain_length": 4,
                    "warn_dependency_chain_length": 4,
                    "max_dependency_chain_length": 6,
                },
            }
        }
