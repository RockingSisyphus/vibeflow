from __future__ import annotations

from vibeflow.health.types import HealthFinding, HealthReport

__all__ = ["HealthFinding", "HealthReport", "validate_graph_health", "_HealthValidationState"]


def __getattr__(name: str):
    if name in {"validate_graph_health", "_HealthValidationState"}:
        from vibeflow.health.validation import _HealthValidationState, validate_graph_health

        return {"_HealthValidationState": _HealthValidationState, "validate_graph_health": validate_graph_health}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
