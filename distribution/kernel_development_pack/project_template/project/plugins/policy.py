from __future__ import annotations


class PolicyPlugin:
    name = "project_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "base_lib": {
                    "allowed_paths": ["../base_lib"],
                    "allowed_modules": ["base_lib"],
                }
            }
        }

