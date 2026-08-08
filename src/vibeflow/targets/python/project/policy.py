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
from vibeflow.targets.python.project.plugins import PluginRegistry, plugin_error
from vibeflow.targets.python.quality.source_analysis.types import BANNED_IMPORT_ROOTS, PurityPolicy


DEFAULT_POLICY_DATA: dict[str, Any] = {
    "node_source": {"max_lines": 500, "max_bytes": 60000, "warn_lines": 450, "warn_bytes": 54000},
    "complexity": {
        "max_functions": None,
        "max_branches": None,
        "max_nesting_depth": None,
        "max_params": None,
        "max_contract_keys": None,
    },
    "imports": {
        "allowed_roots": [],
        "banned_roots": sorted(BANNED_IMPORT_ROOTS),
        "allowed_modules": ["urllib.parse", "vibeflow"],
        "banned_modules": ["urllib.request"],
    },
    "base_lib": {"allowed_paths": [], "allowed_modules": [], "banned_modules": []},
    "maintainability": {
        "warn_call_chain_length": 4,
        "max_call_chain_length": 4,
        "warn_dependency_chain_length": 4,
        "max_dependency_chain_length": 6,
    },
    "rules": {
        "downgrades": [],
        "exemptions": [],
        "downgradeable": ["GRAPH.DATA.UNCONSUMED_PROVIDER", "GRAPH.SMELL.CONFUSING_NODE_NAME", "GRAPH.SMELL.DUPLICATE_LOGIC", "NODESET.SMELL.TOO_WIDE"],
    },
}


_ABSOLUTE_FINDING_RULES = frozenset({"BASE_LIB.BANNED_IMPORT", "BASE_LIB.FORBIDDEN_PROJECT_IMPORT", "BASE_LIB.GLOBAL_STATE", "BASE_LIB.SIDE_EFFECT_CALL", "BASE_LIB.TOP_LEVEL_SIDE_EFFECT", "NODE.BASE_LIB.INDIRECT_VIOLATION"})
_ADVISORY_EFFECT_RULES = frozenset(
    {"NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"}
)


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
        base_lib = self.data.get("base_lib", {})
        maintainability = self.data.get("maintainability", {})
        default_source = DEFAULT_POLICY_DATA["node_source"]
        default_imports = DEFAULT_POLICY_DATA["imports"]
        default_maintainability = DEFAULT_POLICY_DATA["maintainability"]
        return PurityPolicy(
            max_source_lines=int(node_source.get("max_lines", default_source["max_lines"])),
            max_source_bytes=int(node_source.get("max_bytes", default_source["max_bytes"])),
            warn_source_lines=node_source.get("warn_lines", default_source["warn_lines"]),
            warn_source_bytes=node_source.get("warn_bytes", default_source["warn_bytes"]),
            allowed_import_roots=tuple(imports.get("allowed_roots", ())),
            banned_import_roots=tuple(imports.get("banned_roots", default_imports["banned_roots"])),
            allowed_import_modules=tuple(imports.get("allowed_modules", default_imports["allowed_modules"])),
            banned_import_modules=tuple(imports.get("banned_modules", default_imports["banned_modules"])),
            max_functions=complexity.get("max_functions"),
            max_branches=complexity.get("max_branches"),
            max_nesting_depth=complexity.get("max_nesting_depth"),
            max_params=complexity.get("max_params"),
            max_contract_keys=complexity.get("max_contract_keys"),
            allowed_base_lib_paths=tuple(base_lib.get("allowed_paths", ())),
            allowed_base_lib_modules=tuple(base_lib.get("allowed_modules", ())),
            banned_base_lib_modules=tuple(base_lib.get("banned_modules", ())),
            warn_call_chain_length=int(maintainability.get("warn_call_chain_length", default_maintainability["warn_call_chain_length"])),
            max_call_chain_length=int(maintainability.get("max_call_chain_length", default_maintainability["max_call_chain_length"])),
            warn_dependency_chain_length=int(maintainability.get("warn_dependency_chain_length", default_maintainability["warn_dependency_chain_length"])),
            max_dependency_chain_length=int(maintainability.get("max_dependency_chain_length", default_maintainability["max_dependency_chain_length"])),
        )


@dataclass(frozen=True)
class PolicyResolveResult:
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...] = ()


def apply_policy_to_findings(
    errors: tuple[HealthFinding, ...] | list[HealthFinding],
    warnings: tuple[HealthFinding, ...] | list[HealthFinding],
    policy: EffectivePolicy,
) -> tuple[tuple[HealthFinding, ...], tuple[HealthFinding, ...], tuple[HealthFinding, ...]]:
    rules = policy.data.get("rules", {})
    exemptions = [item for item in rules.get("exemptions", ()) if isinstance(item, Mapping)] if isinstance(rules, Mapping) else []
    downgrades = [item for item in rules.get("downgrades", ()) if isinstance(item, Mapping)] if isinstance(rules, Mapping) else []
    next_errors: list[HealthFinding] = []
    next_warnings: list[HealthFinding] = []
    skipped: list[HealthFinding] = []
    for finding in (*errors, *warnings):
        bucket, adjusted = _policy_bucket(finding, exemptions, downgrades)
        if bucket == "skipped":
            skipped.append(adjusted)
        elif bucket == "error":
            next_errors.append(adjusted)
        else:
            next_warnings.append(adjusted)
    return tuple(next_errors), tuple(next_warnings), tuple(skipped)


def default_effective_policy() -> EffectivePolicy:
    return EffectivePolicy(deepcopy(DEFAULT_POLICY_DATA), ("kernel.default_policy",))


def merge_policy(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    """Merge an already-validated policy update into an effective policy."""

    append_paths = {("rules", "downgrades"), ("rules", "exemptions")}
    _deep_merge(base, override, path=(), append_paths=append_paths)


PolicySchemaValidator = Callable[..., tuple[HealthFinding, ...] | list[HealthFinding]]


def apply_policy_plugins(
    effective: dict[str, Any],
    sources: list[str],
    findings: list[HealthFinding],
    plugin_registry: PluginRegistry,
    *,
    collect_schema_findings: PolicySchemaValidator,
) -> None:
    """Apply registered policy hooks without performing discovery or file IO."""

    for plugin in plugin_registry.policy_plugins():
        if not callable(getattr(plugin, "extend_policy", None)):
            continue
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        before = deepcopy(effective)
        try:
            result = plugin.extend_policy(deepcopy(effective))
        except Exception as exc:
            finding = plugin_error(
                "PLUGIN.EXECUTION",
                f"PolicyPlugin.extend_policy failed: {exc}",
                plugin_name,
            )
            findings.append(finding)
            continue
        if result is None:
            continue
        if not isinstance(result, Mapping):
            finding = plugin_error(
                "PLUGIN.POLICY.SHAPE",
                "PolicyPlugin.extend_policy must return an object or None",
                plugin_name,
            )
            findings.append(finding)
            continue
        policy_update = result.get("policy", result)
        relaxations = result.get("relaxations", ())
        if not isinstance(policy_update, Mapping):
            finding = plugin_error(
                "PLUGIN.POLICY.SHAPE",
                "plugin policy update must be an object",
                plugin_name,
            )
            findings.append(finding)
            continue
        schema_findings = collect_schema_findings(
            policy_update,
            object_prefix=f"plugin:{plugin_name}",
            rule_source=f"plugin.policy:{plugin_name}",
        )
        if schema_findings:
            findings.extend(schema_findings)
            continue
        relaxation_errors = validate_plugin_relaxations(
            before,
            policy_update,
            relaxations,
            plugin_name=plugin_name,
        )
        if relaxation_errors:
            findings.extend(relaxation_errors)
            continue
        merge_policy(effective, policy_update)
        sources.append(f"plugin.policy:{plugin_name}")


def validate_plugin_relaxations(
    current: Mapping[str, Any],
    update: Mapping[str, Any],
    relaxations: object,
    *,
    plugin_name: str,
) -> tuple[HealthFinding, ...]:
    required = _relaxed_rule_ids(current, update)
    if not required:
        return ()
    if not isinstance(relaxations, list):
        return (
            plugin_error(
                "PLUGIN.POLICY.RELAXATION_REQUIRED",
                "plugin policy relaxation must include relaxations list with rule_id, scope, reason, and source",
                plugin_name,
                details={"required_rule_ids": sorted(required)},
            ),
        )
    downgradeable = set(current.get("rules", {}).get("downgradeable", ()))
    findings: list[HealthFinding] = []
    declared: set[str] = set()
    for index, item in enumerate(relaxations):
        if not isinstance(item, Mapping):
            finding = plugin_error(
                "PLUGIN.POLICY.RELAXATION_SHAPE",
                "plugin relaxation must be an object",
                f"{plugin_name}.relaxations[{index}]",
            )
            findings.append(finding)
            continue
        rule_id = str(item.get("rule_id", "")).strip()
        declared.add(rule_id)
        if (
            not rule_id
            or not isinstance(item.get("scope"), Mapping)
            or not str(item.get("reason", "")).strip()
            or not str(item.get("source", "")).strip()
        ):
            finding = plugin_error(
                "PLUGIN.POLICY.RELAXATION_SHAPE",
                "plugin relaxation requires rule_id, scope, reason, and source",
                f"{plugin_name}.relaxations[{index}]",
            )
            findings.append(finding)
        if rule_id not in downgradeable:
            finding = plugin_error(
                "PLUGIN.POLICY.ABSOLUTE_RULE",
                f"plugin cannot relax non-downgradeable rule: {rule_id}",
                f"{plugin_name}.relaxations[{index}]",
            )
            findings.append(finding)
    missing = required - declared
    if missing:
        finding = plugin_error(
            "PLUGIN.POLICY.RELAXATION_REQUIRED",
            "plugin did not declare all relaxed rule ids",
            plugin_name,
            details={"missing_rule_ids": sorted(missing)},
        )
        findings.append(finding)
    return tuple(findings)


def _policy_bucket(finding: HealthFinding, exemptions: list[Mapping[str, Any]], downgrades: list[Mapping[str, Any]]) -> tuple[str, HealthFinding]:
    if (
        finding.rule_id.startswith("NODE.EFFECT.")
        and finding.rule_id not in _ADVISORY_EFFECT_RULES
    ) or finding.rule_id in _ABSOLUTE_FINDING_RULES:
        return "error", finding
    exemption = _matching_rule_override(finding, exemptions)
    if exemption is not None:
        return "skipped", _policy_adjusted_finding(finding, "skipped", exemption)
    downgrade = _matching_rule_override(finding, downgrades)
    if downgrade is None:
        return finding.severity, finding
    target = str(downgrade.get("to", "warning"))
    if target == "skip":
        return "skipped", _policy_adjusted_finding(finding, "skipped", downgrade)
    if target in {"warning", "info"}:
        return "warning", _policy_adjusted_finding(finding, "warning", downgrade)
    return finding.severity, finding


def _matching_rule_override(finding: HealthFinding, overrides: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for item in overrides:
        if str(item.get("rule_id", "")) == finding.rule_id and _scope_matches(finding, item.get("scope")):
            return item
    return None


def _scope_matches(finding: HealthFinding, scope: object) -> bool:
    if not isinstance(scope, Mapping) or not scope:
        return True
    checks = {
        "object_id": finding.object_id,
        "object_type": finding.object_type,
        "node": finding.object_id,
        "layer": finding.failure_layer,
    }
    return all(str(checks.get(str(key), "")) == str(value) for key, value in scope.items())


def _policy_adjusted_finding(finding: HealthFinding, severity: str, rule: Mapping[str, Any]) -> HealthFinding:
    details = dict(finding.details)
    details["policy_override"] = {
        "reason": rule.get("reason", ""),
        "expires": rule.get("expires", ""),
    }
    return HealthFinding(
        rule_id=finding.rule_id,
        severity=severity,
        object_type=finding.object_type,
        object_id=finding.object_id,
        source_location=finding.source_location,
        rule_source=finding.rule_source,
        failure_layer=finding.failure_layer,
        message=finding.message,
        suggested_fix_type=finding.suggested_fix_type,
        details=details,
        root_id=finding.root_id,
        root_path=finding.root_path,
        source_path=finding.source_path,
    )


def _relaxed_rule_ids(current: Mapping[str, Any], update: Mapping[str, Any]) -> set[str]:
    return {
        *_relaxed_node_source_rule_ids(current, update),
        *_relaxed_import_rule_ids(current, update),
        *_relaxed_policy_rule_ids(update),
    }


def _relaxed_node_source_rule_ids(current: Mapping[str, Any], update: Mapping[str, Any]) -> set[str]:
    node_source = update.get("node_source")
    if not isinstance(node_source, Mapping):
        return set()
    current_source = current.get("node_source", {})
    relaxed: set[str] = set()
    for field, rule_id in (
        ("max_lines", "NODE.SOURCE.MAX_LINES"),
        ("max_bytes", "NODE.SOURCE.MAX_BYTES"),
    ):
        if field in node_source and int(node_source[field]) > int(current_source.get(field, 0)):
            relaxed.add(rule_id)
    return relaxed


def _relaxed_import_rule_ids(current: Mapping[str, Any], update: Mapping[str, Any]) -> set[str]:
    imports = update.get("imports")
    if not isinstance(imports, Mapping):
        return set()
    current_imports = current.get("imports", {})
    relaxed: set[str] = set()
    if set(imports.get("allowed_roots", ())) - set(
        current_imports.get("allowed_roots", ())
    ):
        relaxed.add("NODE.IMPORT.ALLOWED_ROOTS")
    if set(imports.get("allowed_modules", ())) - set(
        current_imports.get("allowed_modules", ())
    ):
        relaxed.add("NODE.IMPORT.ALLOWED_MODULES")
    if set(current_imports.get("banned_roots", ())) - set(
        imports.get("banned_roots", current_imports.get("banned_roots", ()))
    ):
        relaxed.add("NODE.IMPORT.BANNED_ROOTS")
    if set(current_imports.get("banned_modules", ())) - set(
        imports.get("banned_modules", current_imports.get("banned_modules", ()))
    ):
        relaxed.add("NODE.IMPORT.BANNED_MODULES")
    return relaxed


def _relaxed_policy_rule_ids(update: Mapping[str, Any]) -> set[str]:
    rules = update.get("rules")
    if not isinstance(rules, Mapping):
        return set()
    relaxed: set[str] = set()
    for item in (*rules.get("downgrades", ()), *rules.get("exemptions", ())):
        if isinstance(item, Mapping) and item.get("rule_id"):
            relaxed.add(str(item["rule_id"]))
    return relaxed


def _deep_merge(
    base: dict[str, Any],
    override: Mapping[str, Any],
    *,
    path: tuple[str, ...],
    append_paths: set[tuple[str, ...]],
) -> None:
    for key, value in override.items():
        key = str(key)
        next_path = (*path, key)
        if next_path in append_paths and isinstance(value, list):
            existing = base.get(key)
            if not isinstance(existing, list):
                base[key] = []
            base[key].extend(deepcopy(value))
        elif isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _deep_merge(
                base[key], value, path=next_path, append_paths=append_paths
            )
        else:
            base[key] = deepcopy(value)

__all__ = [
    "DEFAULT_POLICY_DATA",
    "EffectivePolicy",
    "PolicyResolveResult",
    "apply_policy_plugins",
    "apply_policy_to_findings",
    "default_effective_policy",
    "merge_policy",
    "validate_plugin_relaxations",
]
