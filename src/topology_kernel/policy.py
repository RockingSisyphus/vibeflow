from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config_schema import collect_policy_schema_findings
from .config_loader import ConfigLoadError, load_config_document
from .health import HealthFinding
from .plugin import PluginRegistry, plugin_error
from .purity import BANNED_IMPORT_ROOTS, PurityPolicy


DEFAULT_POLICY_DATA: dict[str, Any] = {
    "node_source": {
        "max_lines": 500,
        "max_bytes": 60000,
        "warn_lines": 450,
        "warn_bytes": 54000,
    },
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
    },
    "base_lib": {
        "allowed_paths": [],
        "allowed_modules": [],
        "banned_modules": [],
    },
    "maintainability": {
        "warn_call_chain_length": 4,
        "max_call_chain_length": 4,
        "warn_dependency_chain_length": 4,
        "max_dependency_chain_length": 6,
    },
    "rules": {
        "downgrades": [],
        "exemptions": [],
        "downgradeable": [
            "GRAPH.OUTPUT.UNCONSUMED",
            "GRAPH.SMELL.CONFUSING_NODE_NAME",
            "GRAPH.SMELL.DUPLICATE_LOGIC",
            "NODESET.SMELL.TOO_WIDE",
        ],
    },
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
        base_lib = self.data.get("base_lib", {})
        maintainability = self.data.get("maintainability", {})
        return PurityPolicy(
            max_source_lines=int(node_source.get("max_lines", DEFAULT_POLICY_DATA["node_source"]["max_lines"])),
            max_source_bytes=int(node_source.get("max_bytes", DEFAULT_POLICY_DATA["node_source"]["max_bytes"])),
            warn_source_lines=node_source.get("warn_lines", DEFAULT_POLICY_DATA["node_source"]["warn_lines"]),
            warn_source_bytes=node_source.get("warn_bytes", DEFAULT_POLICY_DATA["node_source"]["warn_bytes"]),
            allowed_import_roots=tuple(imports.get("allowed_roots", ())),
            banned_import_roots=tuple(imports.get("banned_roots", DEFAULT_POLICY_DATA["imports"]["banned_roots"])),
            max_functions=complexity.get("max_functions"),
            max_branches=complexity.get("max_branches"),
            max_nesting_depth=complexity.get("max_nesting_depth"),
            max_params=complexity.get("max_params"),
            max_contract_keys=complexity.get("max_contract_keys"),
            allowed_base_lib_paths=tuple(base_lib.get("allowed_paths", ())),
            allowed_base_lib_modules=tuple(base_lib.get("allowed_modules", ())),
            banned_base_lib_modules=tuple(base_lib.get("banned_modules", ())),
            warn_call_chain_length=int(maintainability.get("warn_call_chain_length", DEFAULT_POLICY_DATA["maintainability"]["warn_call_chain_length"])),
            max_call_chain_length=int(maintainability.get("max_call_chain_length", DEFAULT_POLICY_DATA["maintainability"]["max_call_chain_length"])),
            warn_dependency_chain_length=int(maintainability.get("warn_dependency_chain_length", DEFAULT_POLICY_DATA["maintainability"]["warn_dependency_chain_length"])),
            max_dependency_chain_length=int(maintainability.get("max_dependency_chain_length", DEFAULT_POLICY_DATA["maintainability"]["max_dependency_chain_length"])),
        )


@dataclass(frozen=True)
class PolicyResolveResult:
    effective_policy: EffectivePolicy
    findings: tuple[HealthFinding, ...] = ()


def default_effective_policy() -> EffectivePolicy:
    return EffectivePolicy(deepcopy(DEFAULT_POLICY_DATA), ("kernel.default_policy",))


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
            findings.append(_policy_schema_finding("CONFIG.SCHEMA.POLICY_ROOT", "policy must be an object", "policy"))
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

    return PolicyResolveResult(EffectivePolicy(effective, tuple(sources)), tuple(findings))


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
            _policy_schema_finding(
                "CONFIG.SCHEMA.POLICY_ROOT",
                "policy file root must be a policy object or contain object field 'policy'",
                str(path),
                rule_source=f"project.policy:{path}",
            )
        )
        return
    schema_findings = collect_policy_schema_findings(payload, object_prefix=str(path), rule_source=f"project.policy:{path}")
    if schema_findings:
        findings.extend(schema_findings)
        return
    _merge_policy(effective, payload)
    sources.append(f"project.policy:{path}")


def _merge_policy(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    append_paths = {("rules", "downgrades"), ("rules", "exemptions")}
    _deep_merge(base, override, path=(), append_paths=append_paths)


def _apply_policy_plugins(
    effective: dict[str, Any],
    sources: list[str],
    findings: list[HealthFinding],
    plugin_registry: PluginRegistry,
) -> None:
    for plugin in plugin_registry.policy_plugins():
        if not callable(getattr(plugin, "extend_policy", None)):
            continue
        plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
        before = deepcopy(effective)
        try:
            result = plugin.extend_policy(deepcopy(effective))
        except Exception as exc:
            findings.append(plugin_error("PLUGIN.EXECUTION", f"PolicyPlugin.extend_policy failed: {exc}", plugin_name))
            continue
        if result is None:
            continue
        if not isinstance(result, Mapping):
            findings.append(plugin_error("PLUGIN.POLICY.SHAPE", "PolicyPlugin.extend_policy must return an object or None", plugin_name))
            continue
        policy_update = result.get("policy", result)
        relaxations = result.get("relaxations", ())
        if not isinstance(policy_update, Mapping):
            findings.append(plugin_error("PLUGIN.POLICY.SHAPE", "plugin policy update must be an object", plugin_name))
            continue
        schema_findings = collect_policy_schema_findings(
            policy_update,
            object_prefix=f"plugin:{plugin_name}",
            rule_source=f"plugin.policy:{plugin_name}",
        )
        if schema_findings:
            findings.extend(schema_findings)
            continue
        relaxation_errors = _validate_plugin_relaxations(before, policy_update, relaxations, plugin_name=plugin_name)
        if relaxation_errors:
            findings.extend(relaxation_errors)
            continue
        _merge_policy(effective, policy_update)
        sources.append(f"plugin.policy:{plugin_name}")


def _validate_plugin_relaxations(
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
            findings.append(plugin_error("PLUGIN.POLICY.RELAXATION_SHAPE", "plugin relaxation must be an object", f"{plugin_name}.relaxations[{index}]"))
            continue
        rule_id = str(item.get("rule_id", "")).strip()
        declared.add(rule_id)
        if not rule_id or not isinstance(item.get("scope"), Mapping) or not str(item.get("reason", "")).strip() or not str(item.get("source", "")).strip():
            findings.append(
                plugin_error(
                    "PLUGIN.POLICY.RELAXATION_SHAPE",
                    "plugin relaxation requires rule_id, scope, reason, and source",
                    f"{plugin_name}.relaxations[{index}]",
                )
            )
        if rule_id not in downgradeable:
            findings.append(
                plugin_error(
                    "PLUGIN.POLICY.ABSOLUTE_RULE",
                    f"plugin cannot relax non-downgradeable rule: {rule_id}",
                    f"{plugin_name}.relaxations[{index}]",
                )
            )
    missing = required - declared
    if missing:
        findings.append(
            plugin_error(
                "PLUGIN.POLICY.RELAXATION_REQUIRED",
                "plugin did not declare all relaxed rule ids",
                plugin_name,
                details={"missing_rule_ids": sorted(missing)},
            )
        )
    return tuple(findings)


def _relaxed_rule_ids(current: Mapping[str, Any], update: Mapping[str, Any]) -> set[str]:
    relaxed: set[str] = set()
    node_source = update.get("node_source")
    if isinstance(node_source, Mapping):
        current_source = current.get("node_source", {})
        for field, rule_id in (("max_lines", "NODE.SOURCE.MAX_LINES"), ("max_bytes", "NODE.SOURCE.MAX_BYTES")):
            if field in node_source and int(node_source[field]) > int(current_source.get(field, 0)):
                relaxed.add(rule_id)
    imports = update.get("imports")
    if isinstance(imports, Mapping):
        current_imports = current.get("imports", {})
        if set(imports.get("allowed_roots", ())) - set(current_imports.get("allowed_roots", ())):
            relaxed.add("NODE.IMPORT.ALLOWED_ROOTS")
        if set(current_imports.get("banned_roots", ())) - set(imports.get("banned_roots", current_imports.get("banned_roots", ()))):
            relaxed.add("NODE.IMPORT.BANNED_ROOTS")
    rules = update.get("rules")
    if isinstance(rules, Mapping) and (rules.get("downgrades") or rules.get("exemptions")):
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
            _deep_merge(base[key], value, path=next_path, append_paths=append_paths)
        else:
            base[key] = deepcopy(value)


def _policy_schema_finding(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    rule_source: str = "config.inline_policy",
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="policy",
        object_id=object_id,
        failure_layer="schema",
        message=message,
        suggested_fix_type="fix_policy",
        rule_source=rule_source,
    )
