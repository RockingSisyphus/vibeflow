from __future__ import annotations

from vibeflow.targets.javascript.frontend.model_types import (
    ABI_VERSION,
    ASYNC_MODES,
    CARDINALITIES,
    COMPLETIONS,
    ENTRY_MODES,
    EXECUTORS,
    JOIN_POLICIES,
    PROFILES,
    TARGETS,
    AotPlanError,
    CapabilityOperation,
    CapabilityRequirement,
    CapabilitySpec,
    ConditionSpec,
    ImplementationSpec,
    InputSpec,
    LoopCarry,
    LoopCollect,
    LoopOutput,
    LoopSpec,
    NodeSpec,
    OutputSpec,
    ProviderSpec,
    RequirementSpec,
    RouteSpec,
    SCHEDULES,
    TaskSpec,
    WorkflowSpec,
)


def normalize_workflow_plan(
    value: WorkflowSpec | object,
) -> WorkflowSpec:
    return (
        value
        if isinstance(value, WorkflowSpec)
        else WorkflowSpec.from_portable(value)
    )


__all__ = [
    "ABI_VERSION",
    "AotPlanError",
    "COMPLETIONS",
    "CapabilityOperation",
    "CapabilityRequirement",
    "CapabilitySpec",
    "ConditionSpec",
    "ENTRY_MODES",
    "EXECUTORS",
    "ImplementationSpec",
    "InputSpec",
    "LoopCarry",
    "LoopCollect",
    "LoopOutput",
    "LoopSpec",
    "NodeSpec",
    "OutputSpec",
    "ProviderSpec",
    "RequirementSpec",
    "RouteSpec",
    "SCHEDULES",
    "TaskSpec",
    "WorkflowSpec",
    "normalize_workflow_plan",
]
