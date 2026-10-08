from __future__ import annotations

from vibeflow.core.findings import HealthFinding


def _finding(rule_id: str, message: str, object_id: str, failure_layer: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=failure_layer,
        object_id=object_id,
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
    )


__all__ = ["_finding"]
