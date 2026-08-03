from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ABI_VERSION = "vibeflow.workflow.v3"
CARDINALITIES = frozenset({"exactly_one", "optional_one", "all"})
JOIN_POLICIES = frozenset({"safe_any", "any_active", "all"})
ASYNC_MODES = frozenset({"", "result_key", "detached"})
ENTRY_MODES = frozenset({"sync", "async"})
COMPLETIONS = frozenset({"immediate", "suspend"})
SCHEDULES = frozenset({"inline", "deferred", "detached"})
EXECUTORS = frozenset({"current", "event_loop", "thread"})
TARGETS = frozenset({"browser", "node"})
PROFILES = frozenset({"esm-module", "single-esm", "web-app"})


class AotPlanError(ValueError):
    """Raised when a portable plan cannot be emitted safely."""

    def __init__(self, message: str, *, code: str = "VF_PLAN") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InputSpec:
    key: str
    type: str
    required: bool
    schema: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "type": self.type,
            "required": self.required,
        }
        if self.schema is not None:
            payload["schema"] = dict(self.schema)
        return payload


@dataclass(frozen=True)
class OutputSpec:
    type: str
    cardinality: str
    alias: str
    schema: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "cardinality": self.cardinality,
            "as": self.alias,
        }
        if self.schema is not None:
            payload["schema"] = dict(self.schema)
        return payload


@dataclass(frozen=True)
class RequirementSpec:
    type: str
    cardinality: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "cardinality": self.cardinality}


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "type": self.type}


@dataclass(frozen=True)
class ImplementationSpec:
    module: str
    export: str = "run"
    language: str = "javascript"
    completion: str = "immediate"

    def to_dict(self) -> dict[str, str]:
        return {
            "module": self.module,
            "export": self.export,
            "language": self.language,
            "completion": self.completion,
        }


@dataclass(frozen=True)
class ConditionSpec:
    key: str
    operator: str
    literal: str | bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "operator": self.operator,
            "literal": self.literal,
        }


@dataclass(frozen=True)
class RouteSpec:
    source: str
    target: str
    condition: ConditionSpec | None = None
    schedule: bool = True
    transfer: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "schedule": self.schedule,
            "transfer": self.transfer,
        }
        if self.condition is not None:
            payload["condition"] = self.condition.to_dict()
        return payload


@dataclass(frozen=True)
class CapabilityRequirement:
    id: str
    operations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "operations": list(self.operations)}


@dataclass(frozen=True)
class CapabilityOperation:
    input_type: str = ""
    output_type: str = ""
    completion: str = "immediate"

    def to_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("input_type", self.input_type),
                ("output_type", self.output_type),
                ("completion", self.completion),
            )
            if value
        }


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    operations: Mapping[str, CapabilityOperation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operations": {
                key: value.to_dict()
                for key, value in sorted(self.operations.items())
            },
        }


@dataclass(frozen=True)
class LoopCarry:
    source: str
    target: str
    update: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "update": self.update}


@dataclass(frozen=True)
class LoopCollect:
    source: str
    target: str
    mode: str = "all"

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "mode": self.mode}


@dataclass(frozen=True)
class LoopOutput:
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target}


@dataclass(frozen=True)
class LoopSpec:
    max_iterations: int | None = 1000
    stop_after: int = 0
    stop_when_source: str = ""
    stop_when_equals: bool = True
    carry: tuple[LoopCarry, ...] = ()
    collect: tuple[LoopCollect, ...] = ()
    outputs: tuple[LoopOutput, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "max_iterations": self.max_iterations,
            "carry": [item.to_dict() for item in self.carry],
            "collect": [item.to_dict() for item in self.collect],
            "outputs": [item.to_dict() for item in self.outputs],
        }
        if self.stop_after:
            payload["stop_after"] = self.stop_after
        if self.stop_when_source:
            payload["stop_when"] = {
                "from": self.stop_when_source,
                "equals": self.stop_when_equals,
            }
        return payload


@dataclass(frozen=True)
class NodeSpec:
    id: str
    type_used: str
    implementation: ImplementationSpec | None
    requires: tuple[RequirementSpec, ...] = ()
    provides: tuple[ProviderSpec, ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)
    flow_kind: str = ""
    join_policy: str = "safe_any"
    async_mode: str = ""
    result_key: str = ""
    is_terminal: bool = False
    is_nodeset: bool = False
    is_loop: bool = False
    subplan: "WorkflowSpec | None" = None
    loop: LoopSpec = field(default_factory=LoopSpec)
    capabilities: tuple[CapabilityRequirement, ...] = ()
    completion: str = "immediate"
    schedule: str = "inline"
    executor: str = "current"
    io_operation: str = ""
    io_port: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type_used": self.type_used,
            "requires": [item.to_dict() for item in self.requires],
            "provides": [item.to_dict() for item in self.provides],
            "params": dict(self.params),
            "flow_kind": self.flow_kind,
            "join_policy": self.join_policy,
            "async_mode": self.async_mode,
            "result_key": self.result_key,
            "is_terminal": self.is_terminal,
            "is_nodeset": self.is_nodeset,
            "is_loop": self.is_loop,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "loop": self.loop.to_dict(),
            "completion": self.completion,
            "schedule": self.schedule,
            "executor": self.executor,
            "io_operation": self.io_operation,
            "io_port": self.io_port,
        }
        if self.implementation is not None:
            payload["implementation"] = self.implementation.to_dict()
        if self.subplan is not None:
            payload["subplan"] = self.subplan.to_dict()
        return payload


@dataclass(frozen=True)
class TaskSpec:
    id: str
    node_id: str
    schedule: str
    executor: str
    result_key: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "id": self.id,
            "node_id": self.node_id,
            "schedule": self.schedule,
            "executor": self.executor,
        }
        if self.result_key:
            payload["result_key"] = self.result_key
        return payload


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    inputs: tuple[InputSpec, ...]
    outputs: tuple[OutputSpec, ...]
    nodes: tuple[NodeSpec, ...]
    routes: tuple[RouteSpec, ...]
    order: tuple[str, ...]
    entries: tuple[str, ...]
    max_steps: int = 1000
    schemas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    capabilities: tuple[CapabilitySpec, ...] = ()
    abi_version: str = ABI_VERSION
    entry_mode: str = "sync"
    tasks: tuple[TaskSpec, ...] = ()

    @classmethod
    def from_portable(cls, value: object) -> "WorkflowSpec":
        from vibeflow.targets.javascript.frontend.frontend_parser import parse_workflow

        return parse_workflow(value, workflow_type=cls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "abi_version": self.abi_version,
            "workflow_id": self.workflow_id,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "nodes": [item.to_dict() for item in self.nodes],
            "routes": [item.to_dict() for item in self.routes],
            "order": list(self.order),
            "entries": list(self.entries),
            "max_steps": self.max_steps,
            "schemas": {
                key: dict(value)
                for key, value in sorted(self.schemas.items())
            },
            "capabilities": [item.to_dict() for item in self.capabilities],
            "entry_mode": self.entry_mode,
            "tasks": [item.to_dict() for item in self.tasks],
        }

    def implementation_modules(self) -> tuple[str, ...]:
        modules: list[str] = []

        def visit(workflow: WorkflowSpec) -> None:
            for node in workflow.nodes:
                if node.implementation is not None:
                    modules.append(node.implementation.module)
                if node.subplan is not None:
                    visit(node.subplan)

        visit(self)
        return tuple(dict.fromkeys(modules))


__all__ = [
    "ABI_VERSION",
    "ASYNC_MODES",
    "AotPlanError",
    "CARDINALITIES",
    "COMPLETIONS",
    "CapabilityOperation",
    "CapabilityRequirement",
    "CapabilitySpec",
    "ConditionSpec",
    "ImplementationSpec",
    "InputSpec",
    "ENTRY_MODES",
    "EXECUTORS",
    "JOIN_POLICIES",
    "LoopCarry",
    "LoopCollect",
    "LoopOutput",
    "LoopSpec",
    "NodeSpec",
    "OutputSpec",
    "PROFILES",
    "ProviderSpec",
    "RequirementSpec",
    "RouteSpec",
    "SCHEDULES",
    "TaskSpec",
    "TARGETS",
    "WorkflowSpec",
]
