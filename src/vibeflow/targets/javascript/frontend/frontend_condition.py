"""Condition parsing for the JavaScript workflow frontend."""

from __future__ import annotations

from vibeflow.targets.javascript.frontend.model_types import AotPlanError, ConditionSpec
from vibeflow.targets.javascript.frontend.frontend_validation import as_mapping, required_text


def parse_condition(
    value: object,
    *,
    field_name: str,
) -> ConditionSpec | None:
    if value in (None, "", {}):
        return None
    if isinstance(value, str):
        for operator in ("==", "!="):
            if operator not in value:
                continue
            left, right = (
                part.strip()
                for part in value.split(operator, 1)
            )
            if not left or not right:
                break
            literal: str | bool
            if right in {"true", "false"}:
                literal = right == "true"
            elif (
                len(right) >= 2
                and right[0] == right[-1]
                and right[0] in {"'", '"'}
            ):
                literal = right[1:-1]
            else:
                raise AotPlanError(
                    (
                        f"{field_name} only supports boolean and quoted "
                        "string literals"
                    )
                )
            return ConditionSpec(
                key=left,
                operator=operator,
                literal=literal,
            )
        raise AotPlanError(
            f"{field_name} only supports normalized == or != conditions"
        )
    raw = as_mapping(value, field_name=field_name)
    operator = str(raw.get("operator", "") or "")
    if operator not in {"==", "!="}:
        raise AotPlanError(
            f"{field_name}.operator must be == or !="
        )
    literal = raw.get("literal")
    if not isinstance(literal, (str, bool)):
        raise AotPlanError(
            f"{field_name}.literal must be a string or boolean"
        )
    return ConditionSpec(
        key=required_text(
            raw.get("key"),
            field_name=f"{field_name}.key",
        ),
        operator=operator,
        literal=literal,
    )


__all__ = ["parse_condition"]
