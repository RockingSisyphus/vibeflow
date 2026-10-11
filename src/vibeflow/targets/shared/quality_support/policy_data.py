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
    """Merge validated numeric defaults used as Rule parameters."""

    def visit(target: dict[str, Any], update: Mapping[str, Any]) -> None:
        for raw_key, value in update.items():
            key = str(raw_key)
            if isinstance(value, Mapping) and isinstance(target.get(key), dict):
                visit(target[key], value)
            else:
                target[key] = deepcopy(value)

    visit(base, override)


__all__ = ["COMMON_POLICY_DATA", "merge_policy_data"]
