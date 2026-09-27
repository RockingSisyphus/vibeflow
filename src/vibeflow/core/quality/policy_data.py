"""Shared numeric quality policy, with no source-language dependencies."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


COMMON_POLICY_DATA: dict[str, dict[str, Any]] = {
    "node_source": {"max_lines": 500, "max_bytes": 60000, "warn_lines": 450, "warn_bytes": 54000},
    "complexity": {
        "max_functions": None,
        "max_branches": None,
        "max_nesting_depth": None,
        "max_params": None,
        "max_contract_keys": None,
    },
    "maintainability": {
        "warn_call_chain_length": 4,
        "max_call_chain_length": 4,
        "warn_dependency_chain_length": 4,
        "max_dependency_chain_length": 6,
    },
}


def merge_policy_data(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    """Merge validated policy values while appending existing rule exceptions."""

    append_paths = {("rules", "downgrades"), ("rules", "exemptions")}

    def visit(target: dict[str, Any], update: Mapping[str, Any], path: tuple[str, ...]) -> None:
        for raw_key, value in update.items():
            key = str(raw_key)
            next_path = (*path, key)
            if next_path in append_paths and isinstance(value, list):
                existing = target.get(key)
                if not isinstance(existing, list):
                    target[key] = []
                target[key].extend(deepcopy(value))
            elif isinstance(value, Mapping) and isinstance(target.get(key), dict):
                visit(target[key], value, next_path)
            else:
                target[key] = deepcopy(value)

    visit(base, override, ())


__all__ = ["COMMON_POLICY_DATA", "merge_policy_data"]
