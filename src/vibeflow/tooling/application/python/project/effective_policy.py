"""Python policy adapter over shared discovery and merge semantics.

Policy is resolved from shared explicit configuration layers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

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
) -> PolicyResolveResult:
    effective, resolved_sources, resolved_findings = resolve_shared_quality_policy(
        config_data,
        config_path=config_path,
        explicit_policy_path=explicit_policy_path,
        defaults=DEFAULT_POLICY_DATA,
    )
    sources = list(resolved_sources)
    findings = list(resolved_findings)


    return PolicyResolveResult(
        EffectivePolicy(effective, tuple(sources)),
        tuple(findings),
    )


__all__ = [
    "DEFAULT_POLICY_DATA",
    "EffectivePolicy",
    "PolicyResolveResult",
    "default_effective_policy",
    "resolve_effective_policy",
]
