from __future__ import annotations

from typing import Any, Mapping

from .health_types import HealthFinding
from .schema_findings import schema_finding

def _validate_node_configs(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_CONFIGS_OBJECT", f"{prefix} must be an object", prefix))
        return
    for key, item in value.items():
        if not _non_empty_string(key):
            findings.append(_error("CONFIG.SCHEMA.NODE_CONFIGS_KEY", f"{prefix} keys must be non-empty strings", prefix))
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODE_CONFIG_OBJECT", f"{prefix}.{key} must be an object", f"{prefix}.{key}"))

def _validate_string_list(
    value: Any,
    object_id: str,
    findings: list[HealthFinding],
    rule_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> None:
    if not isinstance(value, list) or any(not _non_empty_string(item) for item in value):
        findings.append(_error(rule_id, f"{object_id} must be a list of non-empty strings", object_id, rule_source=rule_source))

def _validate_provider_list(value: Any, object_id: str, findings: list[HealthFinding], rule_id: str) -> None:
    if not isinstance(value, list):
        findings.append(_error(rule_id, f"{object_id} must be a list of provider objects", object_id))
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_id = f"{object_id}[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error(rule_id, f"{item_id} must be an object with key and type", item_id))
            continue
        if set(item) - {"key", "type", "display_name"}:
            findings.append(_error(rule_id, f"{item_id} must only contain key, type, and display_name", item_id))
        key = str(item.get("key", "")).strip()
        data_type = str(item.get("type", "")).strip()
        display_name = str(item.get("display_name", "")).strip()
        if not key or not data_type or not display_name:
            findings.append(_error(rule_id, f"{item_id} must declare non-empty key, type, and display_name", item_id))
        if key in seen:
            findings.append(_error(rule_id, f"{object_id} contains duplicate provider key: {key}", item_id))
        seen.add(key)

def _validate_requirement_list(value: Any, object_id: str, findings: list[HealthFinding], rule_id: str) -> None:
    if not isinstance(value, list):
        findings.append(_error(rule_id, f"{object_id} must be a list of requirement objects", object_id))
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_id = f"{object_id}[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error(rule_id, f"{item_id} must be an object with type and cardinality", item_id))
            continue
        if set(item) - {"type", "cardinality", "display_name"}:
            findings.append(_error(rule_id, f"{item_id} must only contain type, cardinality, and display_name", item_id))
        data_type = str(item.get("type", "")).strip()
        cardinality = str(item.get("cardinality", "")).strip()
        display_name = str(item.get("display_name", "")).strip()
        if not data_type or cardinality not in {"exactly_one", "optional_one", "all"} or not display_name:
            findings.append(_error(rule_id, f"{item_id} must declare non-empty type, display_name, and valid cardinality", item_id))
        if data_type in seen:
            findings.append(_error(rule_id, f"{object_id} contains duplicate requirement type: {data_type}", item_id))
        seen.add(data_type)

def _provider_keys(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item.get("key", "")).strip() for item in value if isinstance(item, Mapping) and _non_empty_string(item.get("key"))}

def _string_items(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if _non_empty_string(item)}

def _validate_positive_int(
    value: Any,
    object_id: str,
    findings: list[HealthFinding],
    rule_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        findings.append(_error(rule_id, f"{object_id} must be an integer >= 1", object_id, rule_source=rule_source))

def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _error(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> HealthFinding:
    return schema_finding(
        rule_id=rule_id,
        message=message,
        object_id=object_id,
        object_type="config",
        suggested_fix_type="fix_config",
        rule_source=rule_source,
    )
