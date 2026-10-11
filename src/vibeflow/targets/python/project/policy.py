"""Pure Python Target policy calculation.

The functions in this module operate only on in-memory values.  Policy file
discovery, JSONC loading and workspace path handling belong to the outer
loading layer.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.shared.quality_support.policy_data import COMMON_POLICY_DATA, merge_policy_data
from vibeflow.targets.python.rules.node.policy import PurityPolicy


DEFAULT_POLICY_DATA: dict[str, Any] = {
    **deepcopy(COMMON_POLICY_DATA),
    "imports": {},
}


@dataclass(frozen=True)
class EffectivePolicy:
    data: dict[str, Any]
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = deepcopy(self.data)
        payload["sources"] = list(self.sources)
        return payload

    def to_purity_policy(self) -> PurityPolicy:
        node_source = self.data.get("node_source", {})
        complexity = self.data.get("complexity", {})
        imports = self.data.get("imports", {})
        maintainability = self.data.get("maintainability", {})
        default_source = DEFAULT_POLICY_DATA["node_source"]
        default_maintainability = DEFAULT_POLICY_DATA["maintainability"]
        return PurityPolicy(
            max_source_lines=int(node_source.get("max_lines", default_source["max_lines"])),
            max_source_bytes=int(node_source.get("max_bytes", default_source["max_bytes"])),
            warn_source_lines=node_source.get("warn_lines", default_source["warn_lines"]),
            warn_source_bytes=node_source.get("warn_bytes", default_source["warn_bytes"]),
            configured_import_fields=frozenset(imports),
            allowed_import_roots=tuple(imports.get("allowed_roots", ())),
            banned_import_roots=tuple(imports.get("banned_roots", ())),
            allowed_import_modules=tuple(imports.get("allowed_modules", ())),
            banned_import_modules=tuple(imports.get("banned_modules", ())),
            max_functions=complexity.get("max_functions"),
            max_branches=complexity.get("max_branches"),
            max_nesting_depth=complexity.get("max_nesting_depth"),
            max_params=complexity.get("max_params"),
            max_contract_keys=complexity.get("max_contract_keys"),
            warn_call_chain_length=int(maintainability.get("warn_call_chain_length", default_maintainability["warn_call_chain_length"])),
            max_call_chain_length=int(maintainability.get("max_call_chain_length", default_maintainability["max_call_chain_length"])),
            warn_dependency_chain_length=int(maintainability.get("warn_dependency_chain_length", default_maintainability["warn_dependency_chain_length"])),
            max_dependency_chain_length=int(maintainability.get("max_dependency_chain_length", default_maintainability["max_dependency_chain_length"])),
        )


@dataclass(frozen=True)
class PolicyResolveResult:
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...] = ()


def default_effective_policy() -> EffectivePolicy:
    return EffectivePolicy(deepcopy(DEFAULT_POLICY_DATA), ("kernel.default_policy",))


def merge_policy(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    merge_policy_data(base, override)

__all__ = ["DEFAULT_POLICY_DATA", "EffectivePolicy", "PolicyResolveResult", "default_effective_policy", "merge_policy"]
