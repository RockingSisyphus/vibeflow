"""Frozen, deterministic, language-neutral Block Compiler IR."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, TypeAlias


WORKFLOW_ABI_VERSION = "vibeflow.workflow.v3"
_CARDINALITIES = frozenset({"exactly_one", "optional_one", "all"})
_BLOCK_KINDS = frozenset({"workflow", "nodeset", "loop"})
_CONDITION_OPERATORS = frozenset({"==", "!="})
_ENTRY_MODES = frozenset({"sync", "async"})
_COMPLETIONS = frozenset({"immediate", "suspend"})
_SCHEDULES = frozenset({"inline", "deferred", "detached"})
_EXECUTORS = frozenset({"current", "event_loop", "thread"})
_EXECUTION_LOCK_SCOPES = frozenset({"root", "block", "node"})

JsonScalar: TypeAlias = None | bool | int | float | str


class PortablePlanError(ValueError):
    """Raised when a graph value cannot be represented by the portable IR."""


@dataclass(frozen=True)
class PortableArray:
    values: tuple["PortableValue", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple) or not all(_is_portable_value(value) for value in self.values):
            raise PortablePlanError("portable JSON array values must be frozen portable values")

    def to_value(self) -> list[object]:
        return [_portable_value(value) for value in self.values]


@dataclass(frozen=True)
class PortableObject:
    fields: tuple[tuple[str, "PortableValue"], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.fields, tuple):
            raise PortablePlanError("portable JSON object fields must be a tuple")
        keys: list[str] = []
        for item in self.fields:
            if not isinstance(item, tuple) or len(item) != 2:
                raise PortablePlanError("portable JSON object fields must be (key, value) tuples")
            key, value = item
            if not isinstance(key, str) or not _is_portable_value(value):
                raise PortablePlanError("portable JSON object fields must use string keys and frozen portable values")
            keys.append(key)
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise PortablePlanError("portable JSON object keys must be unique and sorted")

    def to_value(self) -> dict[str, object]:
        return {key: _portable_value(value) for key, value in self.fields}


PortableValue: TypeAlias = JsonScalar | PortableArray | PortableObject


def freeze_json_object(value: Mapping[str, Any], *, path: str = "value") -> PortableObject:
    frozen = _freeze_json(value, path=path, active=set())
    if not isinstance(frozen, PortableObject):
        raise PortablePlanError(f"{path} must be a JSON object")
    return frozen


@dataclass(frozen=True)
class SourceRef:
    kind: str
    ref: str
    export: str = ""

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise PortablePlanError("source reference kind must be non-empty")
        if not self.ref.strip():
            raise PortablePlanError("source reference ref must be non-empty")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref, "export": self.export}


@dataclass(frozen=True)
class ExecutionLockPlan:
    key: str
    scope: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise PortablePlanError("execution lock key must be non-empty")
        normalized = self.key.strip()
        if normalized.startswith("vibeflow."):
            raise PortablePlanError(
                "execution lock key uses reserved prefix 'vibeflow.'"
            )
        if self.scope not in _EXECUTION_LOCK_SCOPES:
            raise PortablePlanError(
                "execution lock scope must be one of "
                f"{sorted(_EXECUTION_LOCK_SCOPES)}"
            )
        object.__setattr__(self, "key", normalized)

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "scope": self.scope}


@dataclass(frozen=True)
class ConditionPlan:
    key: str
    operator: str
    literal: bool | str

    def __post_init__(self) -> None:
        if not self.key:
            raise PortablePlanError("condition key must be non-empty")
        if self.operator not in _CONDITION_OPERATORS:
            raise PortablePlanError(f"condition operator must be one of {sorted(_CONDITION_OPERATORS)}")
        if not isinstance(self.literal, (bool, str)):
            raise PortablePlanError("condition literal must be a boolean or string")

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "operator": self.operator, "literal": self.literal}


@dataclass(frozen=True)
class DataProviderPlan:
    key: str
    type: str
    display_name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "type": self.type, "display_name": self.display_name}


@dataclass(frozen=True)
class DataRequirementPlan:
    type: str
    cardinality: str
    display_name: str = ""

    def __post_init__(self) -> None:
        if self.cardinality not in _CARDINALITIES:
            raise PortablePlanError(f"cardinality must be one of {sorted(_CARDINALITIES)}")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "cardinality": self.cardinality, "display_name": self.display_name}


@dataclass(frozen=True)
class PipelineInputSpec:
    key: str
    type: str
    required: bool | None = None
    display_name: str = ""

    def __post_init__(self) -> None:
        if self.required is not None and not isinstance(self.required, bool):
            raise PortablePlanError("pipeline input required must be true, false, or null for legacy input")

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "type": self.type,
            "required": self.required,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class PipelineOutputSpec:
    type: str
    cardinality: str
    as_key: str
    display_name: str = ""

    def __post_init__(self) -> None:
        if self.cardinality not in _CARDINALITIES:
            raise PortablePlanError(f"cardinality must be one of {sorted(_CARDINALITIES)}")
        if not self.as_key:
            raise PortablePlanError("pipeline output alias must be non-empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "cardinality": self.cardinality,
            "as": self.as_key,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class RoutePlan:
    source: str
    target: str
    condition: ConditionPlan | None = None
    schedule: bool = False
    transfer: bool = False
    explicit: bool = False
    mainline: bool = False
    data_bypass: bool = False
    asynchronous: bool = False

    @property
    def pair(self) -> tuple[str, str]:
        return (self.source, self.target)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "condition": self.condition.to_dict() if self.condition is not None else None,
            "schedule": self.schedule,
            "transfer": self.transfer,
            "explicit": self.explicit,
            "mainline": self.mainline,
            "data_bypass": self.data_bypass,
            "asynchronous": self.asynchronous,
        }


@dataclass(frozen=True)
class LoopCarryPlan:
    source: str
    target: str
    update: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "update": self.update}


@dataclass(frozen=True)
class LoopCollectPlan:
    source: str
    target: str
    mode: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "mode": self.mode}


@dataclass(frozen=True)
class LoopOutputPlan:
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target}


@dataclass(frozen=True)
class LoopPlan:
    body_type_key: str
    max_iterations: int | None
    stop_after: int | None
    stop_when: ConditionPlan | None
    carry: tuple[LoopCarryPlan, ...] = ()
    collect: tuple[LoopCollectPlan, ...] = ()
    outputs: tuple[LoopOutputPlan, ...] = ()

    def __post_init__(self) -> None:
        if self.max_iterations is not None and (
            isinstance(self.max_iterations, bool)
            or self.max_iterations < 1
        ):
            raise PortablePlanError(
                "loop max_iterations must be null or an integer >= 1"
            )
        if self.stop_after is not None and (
            isinstance(self.stop_after, bool) or self.stop_after < 1
        ):
            raise PortablePlanError(
                "loop stop_after must be an integer >= 1"
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "body": self.body_type_key,
            "max_iterations": self.max_iterations,
            "carry": [item.to_dict() for item in self.carry],
            "collect": [item.to_dict() for item in self.collect],
            "outputs": [item.to_dict() for item in self.outputs],
        }
        if self.stop_after is not None:
            payload["stop_after"] = self.stop_after
        if self.stop_when is not None:
            payload["stop_when"] = self.stop_when.to_dict()
        return payload


@dataclass(frozen=True)
class NodeCallPlan:
    id: str
    type_used: str
    implementation: SourceRef
    requires: tuple[DataRequirementPlan, ...]
    provides: tuple[DataProviderPlan, ...]
    params: PortableObject
    config_overrides: PortableObject
    flow_kind: str
    join_policy: str
    status: str
    planned_behavior: str
    async_mode: str
    result_key: str
    is_terminal: bool
    is_nodeset: bool
    is_loop: bool
    nodeset_type_key: str
    child_block: str
    exports: tuple[DataProviderPlan, ...]
    allow_config_override: bool = False
    display_name: str = ""
    description: str = ""
    completion: str = "immediate"
    schedule: str = "inline"
    executor: str = "current"
    io_operation: str = ""
    io_port: str = ""
    effect_scope: str = "none"
    execution_lock: ExecutionLockPlan | None = None
    contains_global_state: bool = False

    def __post_init__(self) -> None:
        if self.completion not in _COMPLETIONS:
            raise PortablePlanError(
                f"node completion must be one of {sorted(_COMPLETIONS)}"
            )
        if self.schedule not in _SCHEDULES:
            raise PortablePlanError(
                f"node schedule must be one of {sorted(_SCHEDULES)}"
            )
        if self.executor not in _EXECUTORS:
            raise PortablePlanError(
                f"node executor must be one of {sorted(_EXECUTORS)}"
            )
        if not isinstance(self.effect_scope, str) or not self.effect_scope:
            raise PortablePlanError("node effect_scope must be non-empty")
        if self.execution_lock is not None and not isinstance(
            self.execution_lock, ExecutionLockPlan
        ):
            raise PortablePlanError(
                "node execution_lock must be an ExecutionLockPlan or null"
            )
        if not isinstance(self.contains_global_state, bool):
            raise PortablePlanError(
                "node contains_global_state must be a boolean"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type_used": self.type_used,
            "implementation": self.implementation.to_dict(),
            "requires": [item.to_dict() for item in self.requires],
            "provides": [item.to_dict() for item in self.provides],
            "params": self.params.to_value(),
            "config_overrides": self.config_overrides.to_value(),
            "flow_kind": self.flow_kind,
            "join_policy": self.join_policy,
            "status": self.status,
            "planned_behavior": self.planned_behavior,
            "async_mode": self.async_mode,
            "result_key": self.result_key,
            "is_terminal": self.is_terminal,
            "is_nodeset": self.is_nodeset,
            "is_loop": self.is_loop,
            "nodeset_type_key": self.nodeset_type_key,
            "child_block": self.child_block,
            "exports": [item.to_dict() for item in self.exports],
            "allow_config_override": self.allow_config_override,
            "display_name": self.display_name,
            "description": self.description,
            "completion": self.completion,
            "schedule": self.schedule,
            "executor": self.executor,
            "io_operation": self.io_operation,
            "io_port": self.io_port,
            "effect_scope": self.effect_scope,
            "execution_lock": (
                self.execution_lock.to_dict()
                if self.execution_lock is not None
                else None
            ),
            "contains_global_state": self.contains_global_state,
        }


@dataclass(frozen=True)
class TaskPlan:
    id: str
    node_id: str
    schedule: str
    executor: str
    result_key: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.node_id:
            raise PortablePlanError("task id and node_id must be non-empty")
        if self.schedule not in {"deferred", "detached"}:
            raise PortablePlanError(
                "task schedule must be deferred or detached"
            )
        if self.executor not in _EXECUTORS:
            raise PortablePlanError(
                f"task executor must be one of {sorted(_EXECUTORS)}"
            )
        if self.schedule == "deferred" and not self.result_key:
            raise PortablePlanError(
                "deferred task must declare result_key"
            )
        if self.schedule == "detached" and self.result_key:
            raise PortablePlanError(
                "detached task cannot declare result_key"
            )

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
class BlockPlan:
    id: str
    kind: str
    path: tuple[str, ...]
    source: SourceRef
    inputs: tuple[PipelineInputSpec, ...]
    outputs: tuple[PipelineOutputSpec, ...]
    nodes: tuple[NodeCallPlan, ...]
    routes: tuple[RoutePlan, ...]
    order: tuple[str, ...]
    entries: tuple[str, ...]
    exits: tuple[str, ...]
    max_steps: int
    tasks: tuple[TaskPlan, ...] = ()
    loop: LoopPlan | None = None
    execution_lock: ExecutionLockPlan | None = None
    contains_global_state: bool = False
    root_exclusive: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _BLOCK_KINDS:
            raise PortablePlanError(f"block kind must be one of {sorted(_BLOCK_KINDS)}")
        if self.execution_lock is not None and not isinstance(
            self.execution_lock, ExecutionLockPlan
        ):
            raise PortablePlanError(
                "block execution_lock must be an ExecutionLockPlan or null"
            )
        if not isinstance(self.contains_global_state, bool):
            raise PortablePlanError(
                "block contains_global_state must be a boolean"
            )
        if not isinstance(self.root_exclusive, bool):
            raise PortablePlanError("block root_exclusive must be a boolean")

    def node(self, node_id: str) -> NodeCallPlan:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": list(self.path),
            "source": self.source.to_dict(),
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "nodes": [item.to_dict() for item in self.nodes],
            "routes": [item.to_dict() for item in self.routes],
            "order": list(self.order),
            "entries": list(self.entries),
            "exits": list(self.exits),
            "max_steps": self.max_steps,
            "tasks": [item.to_dict() for item in self.tasks],
            "loop": self.loop.to_dict() if self.loop is not None else None,
            "execution_lock": (
                self.execution_lock.to_dict()
                if self.execution_lock is not None
                else None
            ),
            "contains_global_state": self.contains_global_state,
            "root_exclusive": self.root_exclusive,
        }


@dataclass(frozen=True)
class WorkflowPlan:
    abi_version: str
    workflow_id: str
    source: SourceRef
    entry_block: str
    inputs: tuple[PipelineInputSpec, ...]
    outputs: tuple[PipelineOutputSpec, ...]
    blocks: tuple[BlockPlan, ...]
    max_steps: int
    entry_mode: str = "sync"
    execution_lock: ExecutionLockPlan | None = None
    contains_global_state: bool = False
    root_exclusive: bool = False

    def __post_init__(self) -> None:
        if self.abi_version != WORKFLOW_ABI_VERSION:
            raise PortablePlanError(
                f"workflow ABI must be '{WORKFLOW_ABI_VERSION}', got "
                f"'{self.abi_version}'"
            )
        if self.entry_mode not in _ENTRY_MODES:
            raise PortablePlanError(
                f"workflow entry_mode must be one of {sorted(_ENTRY_MODES)}"
            )
        if self.execution_lock is not None and not isinstance(
            self.execution_lock, ExecutionLockPlan
        ):
            raise PortablePlanError(
                "workflow execution_lock must be an ExecutionLockPlan or null"
            )
        if not isinstance(self.contains_global_state, bool):
            raise PortablePlanError(
                "workflow contains_global_state must be a boolean"
            )
        if not isinstance(self.root_exclusive, bool):
            raise PortablePlanError(
                "workflow root_exclusive must be a boolean"
            )

    def block(self, block_id: str) -> BlockPlan:
        for block in self.blocks:
            if block.id == block_id:
                return block
        raise KeyError(block_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "abi_version": self.abi_version,
            "workflow_id": self.workflow_id,
            "source": self.source.to_dict(),
            "entry_block": self.entry_block,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "blocks": [item.to_dict() for item in self.blocks],
            "max_steps": self.max_steps,
            "entry_mode": self.entry_mode,
            "execution_lock": (
                self.execution_lock.to_dict()
                if self.execution_lock is not None
                else None
            ),
            "contains_global_state": self.contains_global_state,
            "root_exclusive": self.root_exclusive,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _freeze_json(value: Any, *, path: str, active: set[int]) -> PortableValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PortablePlanError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in active:
            raise PortablePlanError(f"{path} contains a circular object")
        active.add(object_id)
        try:
            fields: list[tuple[str, PortableValue]] = []
            keys = tuple(value)
            if not all(isinstance(key, str) for key in keys):
                raise PortablePlanError(f"{path} contains a non-string object key")
            for key in sorted(keys):
                fields.append((key, _freeze_json(value[key], path=f"{path}.{key}", active=active)))
            return PortableObject(tuple(fields))
        finally:
            active.remove(object_id)
    if isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in active:
            raise PortablePlanError(f"{path} contains a circular array")
        active.add(object_id)
        try:
            return PortableArray(
                tuple(_freeze_json(item, path=f"{path}[{index}]", active=active) for index, item in enumerate(value))
            )
        finally:
            active.remove(object_id)
    raise PortablePlanError(f"{path} contains non-portable value of type {type(value).__name__}")


def _is_portable_value(value: object) -> bool:
    if value is None or isinstance(value, (bool, int, str)):
        return True
    return isinstance(value, (float, PortableArray, PortableObject)) and (
        not isinstance(value, float) or math.isfinite(value)
    )


def _portable_value(value: PortableValue) -> object:
    if isinstance(value, PortableObject):
        return value.to_value()
    if isinstance(value, PortableArray):
        return value.to_value()
    return value
