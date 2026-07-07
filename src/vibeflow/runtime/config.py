from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.graph_config import NodeSpec
from vibeflow.runtime.errors import PipelineRuntimeError

ALLOW_CONFIG_OVERRIDE_FIELD = "allow_config_override"
OVERRIDE_CHILD_CONFIG_FIELD = "override_child_config"
CONFIG_VALUES_FIELD = "config"
VALUES_FIELD = "values"
SCOPED_CONFIG_RESERVED_FIELDS = frozenset(
    {
        ALLOW_CONFIG_OVERRIDE_FIELD,
        OVERRIDE_CHILD_CONFIG_FIELD,
        CONFIG_VALUES_FIELD,
        VALUES_FIELD,
    }
)


@dataclass(frozen=True)
class ConfigScope:
    values: Mapping[str, object] = field(default_factory=dict)
    allow_config_override: bool = False


def effective_node_params(spec: NodeSpec, overrides: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    return {**dict(spec.params), **dict(overrides.get(spec.id, {}))}


def attach_global_config(params: Mapping[str, object], global_config: Mapping[str, Any] | None) -> dict[str, object]:
    if global_config is None:
        return dict(params)
    return {**dict(params), "_global": dict(global_config)}


def normalize_config_scope(raw: Mapping[str, Any] | ConfigScope | None) -> ConfigScope:
    if raw is None:
        return ConfigScope()
    if isinstance(raw, ConfigScope):
        return raw
    allow = _bool_field(raw.get(ALLOW_CONFIG_OVERRIDE_FIELD, raw.get(OVERRIDE_CHILD_CONFIG_FIELD, False)))
    values = _scope_values(raw)
    return ConfigScope(values=values, allow_config_override=allow)


def node_invocation_scope(values: Mapping[str, Any], *, allow_config_override: bool) -> ConfigScope:
    return ConfigScope(values={str(key): value for key, value in values.items()}, allow_config_override=bool(allow_config_override))


def merge_config_scopes(base: ConfigScope, override: ConfigScope) -> ConfigScope:
    if not override.values:
        return base
    return ConfigScope(values={**dict(base.values), **dict(override.values)}, allow_config_override=override.allow_config_override)


def scoped_node_params(
    local_params: Mapping[str, Any],
    scope: ConfigScope,
    *,
    declared_keys: set[str] | frozenset[str],
) -> dict[str, object]:
    scoped = {key: value for key, value in scope.values.items() if key in declared_keys}
    return {**dict(local_params), **scoped}


def config_override_conflicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    conflicts: dict[str, dict[str, object]] = {}
    for key, value in override.items():
        if key not in base:
            continue
        current = base[key]
        if _same_value(current, value):
            continue
        conflicts[str(key)] = {"from": current, "to": value}
    return conflicts


def nested_node_config_overrides(
    spec: NodeSpec,
    parent_overrides: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    nested = _copy_overrides(spec.node_config_overrides)
    for path, value in parent_overrides.items():
        prefix = f"{spec.id}."
        if path.startswith(prefix):
            stripped = path.removeprefix(prefix)
            nested[stripped] = {**nested.get(stripped, {}), **dict(value)}
    return nested


def normalize_node_config_overrides(value: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key, item in value.items():
        if not isinstance(item, Mapping):
            raise PipelineRuntimeError(f"node config override for '{key}' must be an object")
        out[str(key)] = dict(item)
    return out


def _copy_overrides(value: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    return {str(key): dict(item) for key, item in value.items()}


def _scope_values(raw: Mapping[str, Any]) -> dict[str, object]:
    selected: dict[str, object] = {}
    nested = raw.get(CONFIG_VALUES_FIELD, raw.get(VALUES_FIELD, None))
    if isinstance(nested, Mapping):
        selected.update({str(key): value for key, value in nested.items()})
    elif nested is None:
        selected.update({str(key): value for key, value in raw.items() if str(key) not in SCOPED_CONFIG_RESERVED_FIELDS})
    else:
        selected.update({str(key): value for key, value in raw.items() if str(key) not in SCOPED_CONFIG_RESERVED_FIELDS})
    for key, value in raw.items():
        text_key = str(key)
        if text_key not in SCOPED_CONFIG_RESERVED_FIELDS:
            selected.setdefault(text_key, value)
    return selected


def _bool_field(value: object) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _same_value(left: object, right: object) -> bool:
    try:
        return bool(left == right)
    except Exception:
        return False
