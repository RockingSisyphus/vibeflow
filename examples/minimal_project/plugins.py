from __future__ import annotations


class Plugin:
    name = "minimal_project_policy"
    priority = 10

    def extend_policy(self, policy):
        return {
            "policy": {
                "base_lib": {
                    "allowed_paths": ["base_lib"],
                    "allowed_modules": ["base_lib.math_tools"],
                },
                "maintainability": {
                    "warn_call_chain_length": 4,
                    "max_call_chain_length": 4,
                    "warn_dependency_chain_length": 4,
                    "max_dependency_chain_length": 6,
                },
            }
        }
