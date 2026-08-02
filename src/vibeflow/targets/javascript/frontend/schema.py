from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


JAVASCRIPT_SAFE_INTEGER_MAX = (1 << 53) - 1

# The generated runtime intentionally implements a deterministic, dependency-free
# subset of JSON Schema 2020-12.  Every keyword not listed here is rejected at
# build time; silently treating an unsupported assertion as successful would make
# the public workflow ABI unsafe.
PORTABLE_SCHEMA_ASSERTIONS = frozenset(
    {
        "type",
        "enum",
        "const",
        "allOf",
        "anyOf",
        "oneOf",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "items",
        "properties",
        "required",
        "additionalProperties",
    }
)
PORTABLE_SCHEMA_ANNOTATIONS = frozenset(
    {
        "$schema",
        "$id",
        "$comment",
        "title",
        "description",
        "default",
        "deprecated",
        "readOnly",
        "writeOnly",
        "examples",
    }
)
PORTABLE_SCHEMA_KEYWORDS = (
    PORTABLE_SCHEMA_ASSERTIONS | PORTABLE_SCHEMA_ANNOTATIONS
)
JSON_TYPES = frozenset(
    {"null", "boolean", "object", "array", "number", "integer", "string"}
)


class PortableSchemaError(ValueError):
    """A JSON Schema cannot be enforced by the dependency-free AOT runtime."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


class JavascriptJsonValueError(ValueError):
    """A value cannot cross the JSON boundary into JavaScript losslessly."""

    def __init__(
        self,
        path: str,
        reason: str,
        *,
        code: str = "VF_AOT_JSON_VALUE",
    ) -> None:
        self.path = path
        self.reason = reason
        self.code = code
        super().__init__(f"{path}: {reason}")


def validate_javascript_json_value(
    value: object,
    *,
    path: str = "$",
) -> None:
    """Validate the lossless JSON subset accepted by generated JS artifacts."""

    _validate_json_value(value, path=path, ancestors=set())


def validate_portable_json_schema(
    schema: object,
    *,
    path: str = "$",
) -> None:
    """Fail closed unless ``schema`` is fully enforceable by the JS runtime."""

    validate_javascript_json_value(schema, path=path)
    _validate_schema(schema, path=path)


def _validate_schema(schema: object, *, path: str) -> None:
    if not isinstance(schema, Mapping):
        raise PortableSchemaError(
            path,
            "boolean and non-object schemas are not supported",
        )
    unknown = sorted(str(key) for key in schema if key not in PORTABLE_SCHEMA_KEYWORDS)
    if unknown:
        raise PortableSchemaError(
            path,
            f"unsupported JSON Schema keywords: {unknown}",
        )

    raw_type = schema.get("type")
    if raw_type is not None:
        values = (
            tuple(raw_type)
            if _is_sequence(raw_type)
            else (raw_type,)
        )
        if not values or any(
            not isinstance(item, str) or item not in JSON_TYPES
            for item in values
        ):
            raise PortableSchemaError(
                f"{path}.type",
                f"expected a JSON type or non-empty list from {sorted(JSON_TYPES)}",
            )
        if len(set(values)) != len(values):
            raise PortableSchemaError(
                f"{path}.type",
                "type alternatives must be unique",
            )

    if "enum" in schema:
        enum = schema["enum"]
        if not _is_sequence(enum) or not enum:
            raise PortableSchemaError(
                f"{path}.enum",
                "enum must be a non-empty array",
            )

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword not in schema:
            continue
        children = schema[keyword]
        if not _is_sequence(children) or not children:
            raise PortableSchemaError(
                f"{path}.{keyword}",
                f"{keyword} must be a non-empty array of schemas",
            )
        for index, child in enumerate(children):
            _validate_schema(child, path=f"{path}.{keyword}[{index}]")

    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        if keyword not in schema:
            continue
        value = schema[keyword]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PortableSchemaError(
                f"{path}.{keyword}",
                f"{keyword} must be a non-negative integer",
            )

    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise PortableSchemaError(
                f"{path}.pattern",
                "pattern must be a string",
            )
        _validate_portable_pattern(pattern, path=f"{path}.pattern")

    for keyword in ("minimum", "maximum"):
        if keyword not in schema:
            continue
        value = schema[keyword]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise PortableSchemaError(
                f"{path}.{keyword}",
                f"{keyword} must be a finite number",
            )

    if "items" in schema:
        _validate_schema(schema["items"], path=f"{path}.items")

    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, Mapping):
            raise PortableSchemaError(
                f"{path}.properties",
                "properties must be an object of schemas",
            )
        for key, child in properties.items():
            if not isinstance(key, str):
                raise PortableSchemaError(
                    f"{path}.properties",
                    "property names must be strings",
                )
            _validate_schema(
                child,
                path=f"{path}.properties[{key!r}]",
            )

    required = schema.get("required")
    if required is not None:
        if (
            not _is_sequence(required)
            or any(not isinstance(item, str) or not item for item in required)
            or len(set(required)) != len(required)
        ):
            raise PortableSchemaError(
                f"{path}.required",
                "required must be an array of unique non-empty strings",
            )

    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        _validate_schema(
            additional,
            path=f"{path}.additionalProperties",
        )


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _validate_json_value(
    value: object,
    *,
    path: str,
    ancestors: set[int],
) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > JAVASCRIPT_SAFE_INTEGER_MAX:
            raise JavascriptJsonValueError(
                path,
                (
                    f"integer {value} is outside JavaScript's lossless range "
                    f"[-{JAVASCRIPT_SAFE_INTEGER_MAX}, {JAVASCRIPT_SAFE_INTEGER_MAX}]"
                ),
                code="VF_AOT_NUMBER_RANGE",
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise JavascriptJsonValueError(
                path,
                "non-finite numbers are not valid portable JSON values",
            )
        return
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in ancestors:
            raise JavascriptJsonValueError(path, "cyclic JSON objects are not supported")
        ancestors.add(identity)
        try:
            for key, child in value.items():
                if not isinstance(key, str):
                    raise JavascriptJsonValueError(
                        path,
                        f"JSON object key {key!r} is not a string",
                    )
                _validate_json_value(
                    child,
                    path=f"{path}[{key!r}]",
                    ancestors=ancestors,
                )
        finally:
            ancestors.remove(identity)
        return
    if _is_sequence(value):
        identity = id(value)
        if identity in ancestors:
            raise JavascriptJsonValueError(path, "cyclic JSON arrays are not supported")
        ancestors.add(identity)
        try:
            for index, child in enumerate(value):
                _validate_json_value(
                    child,
                    path=f"{path}[{index}]",
                    ancestors=ancestors,
                )
        finally:
            ancestors.remove(identity)
        return
    raise JavascriptJsonValueError(
        path,
        f"{type(value).__name__} is not a portable JSON value",
    )


def _validate_portable_pattern(pattern: str, *, path: str) -> None:
    # The AOT runtime constructs an ECMAScript RegExp without flags.  Reject
    # syntax with known Python/ECMAScript dialect differences, then use Python's
    # parser as a conservative structural validation pass.  This intentionally
    # accepts a small common subset rather than silently changing a contract.
    forbidden = (
        (r"(?P", "Python-style named groups are not portable to ECMAScript"),
        (r"\A", r"\A is not an ECMAScript assertion"),
        (r"\Z", r"\Z is not an ECMAScript assertion"),
        (r"\z", r"\z is not an ECMAScript assertion"),
        (r"\G", r"\G is not supported by the generated runtime"),
        (r"\p{", r"Unicode property escapes require unsupported RegExp flags"),
        (r"\P{", r"Unicode property escapes require unsupported RegExp flags"),
        ("(?#", "inline RegExp comments are not portable to ECMAScript"),
    )
    for token, reason in forbidden:
        if token in pattern:
            raise PortableSchemaError(path, reason)
    if re.search(r"\(\?[aiLmsux-]", pattern):
        raise PortableSchemaError(
            path,
            "inline RegExp flags are not supported by the generated runtime",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise PortableSchemaError(
            path,
            f"invalid portable RegExp pattern: {exc}",
        ) from exc


__all__ = [
    "JAVASCRIPT_SAFE_INTEGER_MAX",
    "JSON_TYPES",
    "JavascriptJsonValueError",
    "PORTABLE_SCHEMA_ANNOTATIONS",
    "PORTABLE_SCHEMA_ASSERTIONS",
    "PORTABLE_SCHEMA_KEYWORDS",
    "PortableSchemaError",
    "validate_javascript_json_value",
    "validate_portable_json_schema",
]
