from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping

from vibeflow.config.schema import collect_policy_schema_findings
from vibeflow.health.types import HealthFinding
from vibeflow.policy import DEFAULT_POLICY_DATA, EffectivePolicy, PolicyResolveResult, _merge_policy
from vibeflow.health.schema_findings import schema_finding


def resolve_workspace_effective_policy(
    workspace_policy: object,
    *,
    workspace_path: Path,
    base_lib_policies: tuple[Mapping[str, tuple[str, ...]], ...] = (),
) -> PolicyResolveResult:
    effective = deepcopy(DEFAULT_POLICY_DATA)
    sources: list[str] = ["kernel.default_policy"]
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
                _merge_policy(effective, workspace_policy)
                sources.append(f"workspace.policy:{workspace_path}")
    _apply_workspace_base_lib_declarations(effective, sources, base_lib_policies)
    return PolicyResolveResult(EffectivePolicy(effective, tuple(sources)), tuple(findings))


def _apply_workspace_base_lib_declarations(
    effective: dict[str, object],
    sources: list[str],
    base_lib_policies: tuple[Mapping[str, tuple[str, ...]], ...],
) -> None:
    paths: list[str] = []
    modules: list[str] = []
    for values in base_lib_policies:
        paths.extend(values.get("allowed_paths", ()))
        modules.extend(values.get("allowed_modules", ()))
    if not paths and not modules:
        return
    base_lib = effective.setdefault("base_lib", {})
    if not isinstance(base_lib, dict):
        effective["base_lib"] = {}
        base_lib = effective["base_lib"]
    base_lib["allowed_paths"] = list(dict.fromkeys(paths))
    base_lib["allowed_modules"] = list(dict.fromkeys(modules))
    sources.append("workspace.project_base_lib")
