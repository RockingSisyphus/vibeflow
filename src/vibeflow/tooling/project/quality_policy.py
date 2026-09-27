"""Shared quality policy discovery, schema validation and merge order."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.policy_data import COMMON_POLICY_DATA, merge_policy_data
from vibeflow.core.quality.workflow_rules.schema_findings import schema_finding
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document
from vibeflow.tooling.project.config_schema import collect_policy_schema_findings


def resolve_shared_quality_policy(
    config_data: Mapping[str, Any],
    *,
    config_path: Path,
    explicit_policy_path: Path | None = None,
    defaults: Mapping[str, Any] = COMMON_POLICY_DATA,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[HealthFinding, ...]]:
    effective = deepcopy(dict(defaults))
    sources = ["kernel.default_policy"]
    findings: list[HealthFinding] = []
    for path in (discover_policy_path(config_path), explicit_policy_path):
        if path is None:
            continue
        try:
            document = load_config_document(path)
        except ConfigLoadError as exc:
            findings.append(HealthFinding(
                rule_id=exc.rule_id,
                severity="error",
                object_type="policy",
                object_id=str(path),
                source_location=exc.source_location,
                failure_layer=exc.failure_layer,
                message=exc.message,
                suggested_fix_type="fix_policy",
                rule_source=f"project.policy:{path}",
            ))
            continue
        payload = document.data.get("policy", document.data)
        if not isinstance(payload, Mapping):
            findings.append(schema_finding(
                "CONFIG.SCHEMA.POLICY_ROOT",
                "policy file root must be a policy object or contain object field 'policy'",
                str(path), object_type="policy", suggested_fix_type="fix_policy",
                rule_source=f"project.policy:{path}",
            ))
            continue
        invalid = collect_policy_schema_findings(
            payload, object_prefix=str(path), rule_source=f"project.policy:{path}",
        )
        if invalid:
            findings.extend(invalid)
        else:
            merge_policy_data(effective, payload)
            sources.append(f"project.policy:{path}")
    inline = config_data.get("policy")
    if inline is not None:
        invalid = collect_policy_schema_findings(
            inline, object_prefix="policy", rule_source="config.inline_policy",
        )
        if invalid:
            findings.extend(invalid)
        else:
            merge_policy_data(effective, inline)
            sources.append("config.inline_policy")
    return effective, tuple(sources), tuple(findings)


def discover_policy_path(config_path: Path) -> Path | None:
    for name in ("kernel_policy.jsonc", "governance.jsonc"):
        candidate = config_path.parent / name
        if candidate.exists():
            return candidate
    return None


__all__ = ["discover_policy_path", "resolve_shared_quality_policy"]
