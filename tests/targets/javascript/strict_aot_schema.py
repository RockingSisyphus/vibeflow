from __future__ import annotations

import re

import pytest

from vibeflow.targets.javascript.frontend.schema import (
    JAVASCRIPT_SAFE_INTEGER_MAX,
    JavascriptJsonValueError,
    PortableSchemaError,
    validate_javascript_json_value,
    validate_portable_json_schema,
)
from vibeflow.targets.javascript.frontend.emitter import schema_to_typescript


def test_portable_schema_accepts_the_runtime_validation_subset() -> None:
    validate_portable_json_schema(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "^[A-Z]",
                },
                "scores": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        }
    )


@pytest.mark.parametrize(
    ("schema", "keyword"),
    [
        ({"type": "number", "not": {"const": 3}}, "not"),
        ({"$ref": "#/$defs/value"}, "$ref"),
        (
            {
                "type": "object",
                "dependentRequired": {"name": ["id"]},
            },
            "dependentRequired",
        ),
        ({"type": "number", "multipleOf": 2}, "multipleOf"),
    ],
)
def test_portable_schema_rejects_unsupported_assertions(
    schema: object,
    keyword: str,
) -> None:
    with pytest.raises(PortableSchemaError, match=re.escape(keyword)):
        validate_portable_json_schema(schema)


def test_portable_schema_rejects_nested_boolean_schema() -> None:
    with pytest.raises(
        PortableSchemaError,
        match="boolean and non-object schemas",
    ):
        validate_portable_json_schema(
            {
                "type": "object",
                "properties": {"secret": False},
            }
        )


@pytest.mark.parametrize(
    "pattern",
    [
        "[",
        r"(?P<name>value)",
        r"\Avalue",
        r"(?i)value",
        r"\p{Letter}",
    ],
)
def test_portable_schema_rejects_invalid_or_nonportable_patterns(
    pattern: str,
) -> None:
    with pytest.raises(PortableSchemaError, match="pattern"):
        validate_portable_json_schema(
            {
                "type": "string",
                "pattern": pattern,
            }
        )


@pytest.mark.parametrize(
    "value",
    [
        JAVASCRIPT_SAFE_INTEGER_MAX + 1,
        -(JAVASCRIPT_SAFE_INTEGER_MAX + 1),
        {"nested": [JAVASCRIPT_SAFE_INTEGER_MAX + 1]},
    ],
)
def test_javascript_json_values_reject_lossy_integers(value: object) -> None:
    with pytest.raises(JavascriptJsonValueError) as captured:
        validate_javascript_json_value(value)

    assert captured.value.code == "VF_AOT_NUMBER_RANGE"


def test_javascript_json_values_accept_safe_integer_boundaries() -> None:
    validate_javascript_json_value(
        [
            -JAVASCRIPT_SAFE_INTEGER_MAX,
            JAVASCRIPT_SAFE_INTEGER_MAX,
        ]
    )


def test_typescript_literals_preserve_json_object_and_array_shape() -> None:
    assert schema_to_typescript(
        {
            "const": {
                "kind": "x",
                "values": [1, True, None],
            }
        }
    ) == (
        '{ readonly "kind": "x"; '
        'readonly "values": readonly [1, true, null] }'
    )
    assert schema_to_typescript(
        {"enum": [["a", 1], {"ok": True}]}
    ) == (
        'readonly ["a", 1] | { readonly "ok": true }'
    )


def test_typescript_empty_closed_object_is_not_the_wide_empty_type() -> None:
    assert schema_to_typescript(
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    ) == "Readonly<Record<string, never>>"
