from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class NodeConfigSpec:
    schema: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    defaults: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": {str(key): dict(value) for key, value in self.schema.items()},
            "defaults": dict(self.defaults),
        }


@dataclass(frozen=True)
class NodeConfigError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


def normalize_node_config_spec(schema: Mapping[str, Any], defaults: Mapping[str, Any]) -> NodeConfigSpec:
    if not isinstance(schema, Mapping):
        raise NodeConfigError("node config schema must be an object")
    if not isinstance(defaults, Mapping):
        raise NodeConfigError("node config defaults must be an object")
    normalized_schema = _normalize_schema(schema)
    normalized_defaults = {str(key): value for key, value in defaults.items()}
    missing_defaults = sorted(set(normalized_schema) - set(normalized_defaults))
    extra_defaults = sorted(set(normalized_defaults) - set(normalized_schema))
    if missing_defaults:
        raise NodeConfigError(f"node config defaults missing keys: {missing_defaults}")
    if extra_defaults:
        raise NodeConfigError(f"node config defaults contain undeclared keys: {extra_defaults}")
    for key, value in normalized_defaults.items():
        _assert_json_snapshot(value, object_id=f"defaults.{key}")
        _assert_schema_value(key, value, normalized_schema[key])
    return NodeConfigSpec(schema=normalized_schema, defaults=normalized_defaults)


def merge_node_config(spec: NodeConfigSpec, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, Mapping):
        raise NodeConfigError("node config overrides must be an object")
    normalized_overrides = {str(key): value for key, value in overrides.items()}
    unknown = sorted(set(normalized_overrides) - set(spec.schema))
    if unknown:
        raise NodeConfigError(f"node config overrides contain undeclared keys: {unknown}")
    merged = {**dict(spec.defaults), **normalized_overrides}
    for key, value in merged.items():
        _assert_json_snapshot(value, object_id=key)
        _assert_schema_value(key, value, spec.schema[key])
    return merged


def node_config_from_call_params(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_config = params.get("config", {})
    if raw_config in (None, {}):
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise NodeConfigError("node config field must be an object")
    reserved = {"config", "node_configs"}
    inline = {str(key): value for key, value in params.items() if key not in reserved}
    return {**{str(key): value for key, value in raw_config.items()}, **inline}


def _normalize_schema(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for key, value in schema.items():
        text_key = str(key).strip()
        if not text_key:
            raise NodeConfigError("node config schema keys must be non-empty strings")
        if not isinstance(value, Mapping):
            raise NodeConfigError(f"node config schema for '{text_key}' must be an object")
        if "type" not in value:
            raise NodeConfigError(f"node config schema for '{text_key}' must declare type")
        out[text_key] = dict(value)
    return out


def _assert_schema_value(key: str, value: Any, schema: Mapping[str, Any]) -> None:
    expected = schema.get("type")
    if expected == "any" or _schema_type_matches(expected, value):
        return
    raise NodeConfigError(f"node config '{key}' must match schema type '{expected}'")


def _schema_type_matches(expected: object, value: Any) -> bool:
    validators = {
        "number": _is_number,
        "integer": _is_integer,
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, Mapping),
        "array": lambda item: isinstance(item, list),
        "null": lambda item: item is None,
    }
    validator = validators.get(expected)
    return bool(validator and validator(value))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _assert_json_snapshot(value: Any, *, object_id: str) -> None:
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise NodeConfigError(f"node config '{object_id}' must be JSON snapshot safe: {exc}") from exc
