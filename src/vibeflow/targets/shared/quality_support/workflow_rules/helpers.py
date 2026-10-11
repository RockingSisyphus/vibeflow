"""Small language-neutral helpers shared by structural flow checks."""

from __future__ import annotations

from typing import Mapping

from vibeflow.core.findings import HealthFinding


def _data_finding(
    rule_id: str,
    key: str,
    message: str,
    *,
    node: str,
    severity: str = "warning",
    details: Mapping[str, object] | None = None,
) -> HealthFinding:
    payload = {"node": node}
    if details:
        payload.update(details)
    return HealthFinding(
        rule_id=rule_id,
        severity=severity,
        object_type="contract_key",
        object_id=key,
        failure_layer="topology",
        message=message,
        suggested_fix_type="fix_config",
        details=payload,
    )


def _parse_when(expression: str) -> tuple[str, str, object] | None:
    if not expression:
        return None
    for operator in ("==", "!="):
        if operator not in expression:
            continue
        left, right = (
            part.strip() for part in expression.split(operator, 1)
        )
        if not left or not right:
            return None
        return left, operator, _literal_value(right)
    return None


def _literal_value(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        return value[1:-1]
    return value


__all__: list[str] = []
