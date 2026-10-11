from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.shared.quality_support.workflow_rules.schema_findings import schema_finding
from vibeflow.targets.python.project.policy import (
    DEFAULT_POLICY_DATA,
    EffectivePolicy,
    PolicyResolveResult,
    merge_policy,
)
from vibeflow.tooling.project.config_schema import (
    collect_policy_schema_findings,
)


def resolve_workspace_effective_policy(
    workspace_policy: object,
    *,
    workspace_path: Path,
    base_effective: EffectivePolicy | None = None,
) -> PolicyResolveResult:
    effective = deepcopy(DEFAULT_POLICY_DATA if base_effective is None else base_effective.data)
    sources: list[str] = ["kernel.default_policy"] if base_effective is None else list(base_effective.sources)
    findings: list[HealthFinding] = []
    if workspace_policy is not None:
        if not isinstance(workspace_policy, Mapping):
            findings.append(
                schema_finding(
                    "CONFIG.SCHEMA.POLICY_ROOT",
                    "workspace policy must be an object",
                    str(workspace_path),
                    object_type="policy",
                    suggested_fix_type="fix_policy",
                    rule_source=f"workspace.policy:{workspace_path}",
                )
            )
        else:
            schema_findings = collect_policy_schema_findings(
                workspace_policy,
                object_prefix="policy",
                rule_source=f"workspace.policy:{workspace_path}",
            )
            if schema_findings:
                findings.extend(schema_findings)
            else:
                merge_policy(effective, workspace_policy)
                sources.append(f"workspace.policy:{workspace_path}")
    return PolicyResolveResult(EffectivePolicy(effective, tuple(sources)), tuple(findings))


__all__ = ["resolve_workspace_effective_policy"]
