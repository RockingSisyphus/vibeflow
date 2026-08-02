"""Compatibility and loading boundary for Python policy configuration.

Pure merge, relaxation and finding-application semantics live in the Python
Target.  This module retains path discovery, JSONC loading and adapters to the
legacy configuration layer.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document
from vibeflow.tooling.project.resources import config_base_lib_policy
from vibeflow.tooling.project.config_schema import collect_policy_schema_findings
from vibeflow.core.quality.workflow_rules.schema_findings import schema_finding
from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.policy import (
    DEFAULT_POLICY_DATA,
    EffectivePolicy,
    PolicyResolveResult,
    apply_policy_plugins as _target_apply_policy_plugins,
    apply_policy_to_findings,
    default_effective_policy,
    merge_policy as _target_merge_policy,
)


def resolve_effective_policy(
    config_data: Mapping[str, Any],
    *,
    config_path: Path,
    explicit_policy_path: Path | None = None,
    plugin_registry: PluginRegistry | None = None,
) -> PolicyResolveResult:
    effective = deepcopy(DEFAULT_POLICY_DATA)
    sources: list[str] = ["kernel.default_policy"]
    findings: list[HealthFinding] = []

    discovered = _discover_policy_path(config_path)
    if discovered is not None:
        _merge_external_policy(effective, sources, findings, discovered)
    if explicit_policy_path is not None:
        _merge_external_policy(effective, sources, findings, explicit_policy_path)
    inline_policy = config_data.get("policy")
    if inline_policy is not None:
        if not isinstance(inline_policy, Mapping):
            findings.append(
                schema_finding(
                    "CONFIG.SCHEMA.POLICY_ROOT",
                    "policy must be an object",
                    "policy",
                    object_type="policy",
                    suggested_fix_type="fix_policy",
                )
            )
        else:
            schema_findings = collect_policy_schema_findings(
                inline_policy,
                object_prefix="policy",
                rule_source="config.inline_policy",
            )
            if schema_findings:
                findings.extend(schema_findings)
            else:
                _merge_policy(effective, inline_policy)
                sources.append("config.inline_policy")

    if plugin_registry is not None:
        _apply_policy_plugins(effective, sources, findings, plugin_registry)

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


def _discover_policy_path(config_path: Path) -> Path | None:
    for name in ("kernel_policy.jsonc", "governance.jsonc"):
        candidate = config_path.parent / name
        if candidate.exists():
            return candidate
    return None


def _merge_external_policy(
    effective: dict[str, Any],
    sources: list[str],
    findings: list[HealthFinding],
    path: Path,
) -> None:
    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        findings.append(
            HealthFinding(
                rule_id=exc.rule_id,
                severity="error",
                object_type="policy",
                object_id=str(path),
                source_location=exc.source_location,
                failure_layer=exc.failure_layer,
                message=exc.message,
                suggested_fix_type="fix_policy",
                rule_source=f"project.policy:{path}",
            )
        )
        return
    payload = document.data.get("policy", document.data)
    if not isinstance(payload, Mapping):
        findings.append(
            schema_finding(
                "CONFIG.SCHEMA.POLICY_ROOT",
                "policy file root must be a policy object or contain object field 'policy'",
                str(path),
                object_type="policy",
                suggested_fix_type="fix_policy",
                rule_source=f"project.policy:{path}",
            )
        )
        return
    schema_findings = collect_policy_schema_findings(
        payload,
        object_prefix=str(path),
        rule_source=f"project.policy:{path}",
    )
    if schema_findings:
        findings.extend(schema_findings)
        return
    _merge_policy(effective, payload)
    sources.append(f"project.policy:{path}")


def _merge_policy(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    _target_merge_policy(base, override)


def _apply_policy_plugins(
    effective: dict[str, Any],
    sources: list[str],
    findings: list[HealthFinding],
    plugin_registry: PluginRegistry,
) -> None:
    _target_apply_policy_plugins(
        effective,
        sources,
        findings,
        plugin_registry,
        collect_schema_findings=collect_policy_schema_findings,
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
    "apply_policy_to_findings",
    "default_effective_policy",
    "resolve_effective_policy",
]
