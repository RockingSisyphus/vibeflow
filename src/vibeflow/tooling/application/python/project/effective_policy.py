"""Python policy adapter over shared discovery and merge semantics.

Python plugin extensions and base_lib declarations are applied after the
shared policy layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.application.python.project.resources import config_base_lib_policy
from vibeflow.tooling.project.config_schema import collect_policy_schema_findings
from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.policy import (
    DEFAULT_POLICY_DATA,
    EffectivePolicy,
    PolicyResolveResult,
    default_effective_policy,
)
from vibeflow.tooling.project.quality_policy import resolve_shared_quality_policy


def resolve_effective_policy(
    config_data: Mapping[str, Any],
    *,
    config_path: Path,
    explicit_policy_path: Path | None = None,
    plugin_registry: PluginRegistry | None = None,
) -> PolicyResolveResult:
    effective, resolved_sources, resolved_findings = resolve_shared_quality_policy(
        config_data,
        config_path=config_path,
        explicit_policy_path=explicit_policy_path,
        defaults=DEFAULT_POLICY_DATA,
    )
    sources = list(resolved_sources)
    findings = list(resolved_findings)


    _apply_config_base_lib_declarations(
        effective,
        sources,
        config_data,
        config_path=config_path,
    )

    return PolicyResolveResult(
        EffectivePolicy(effective, tuple(sources)),
        tuple(findings),
    )


def _apply_config_base_lib_declarations(
    effective: dict[str, Any],
    sources: list[str],
    config_data: Mapping[str, Any],
    *,
    config_path: Path,
) -> None:
    values = config_base_lib_policy(config_data, base_path=config_path.parent)
    if not values:
        return
    base_lib = effective.setdefault("base_lib", {})
    if not isinstance(base_lib, dict):
        effective["base_lib"] = {}
        base_lib = effective["base_lib"]
    base_lib["allowed_paths"] = list(values.get("allowed_paths", ()))
    base_lib["allowed_modules"] = list(values.get("allowed_modules", ()))
    sources.append("config.base_lib")


__all__ = [
    "DEFAULT_POLICY_DATA",
    "EffectivePolicy",
    "PolicyResolveResult",
    "default_effective_policy",
    "resolve_effective_policy",
]
