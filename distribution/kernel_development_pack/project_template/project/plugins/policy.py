from __future__ import annotations

from vibeflow import PluginInfo


class PolicyPlugin:
    PLUGIN_INFO = PluginInfo(
        name="project_policy",
        plugin_type="policy",
        display_name="Project Policy",
        category="policy",
        description="Template project policy extension point.",
        version="0.1.0",
    )
    name = "project_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "base_lib": {
                    "allowed_paths": ["base_lib"],
                    "allowed_modules": ["base_lib"],
                }
            }
        }
