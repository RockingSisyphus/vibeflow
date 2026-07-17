from __future__ import annotations

from vibeflow.health.types import HealthFinding


def schema_finding(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    object_type: str,
    suggested_fix_type: str,
    rule_source: str = "kernel.default_policy",
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=object_type,
        object_id=object_id,
        failure_layer="schema",
        message=message,
        suggested_fix_type=suggested_fix_type,
        rule_source=rule_source,
    )
