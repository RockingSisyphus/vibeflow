"""Structural contracts and leaf views used by JavaScript code generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from vibeflow.block_compiler.model import (
    ConditionPlan,
    LoopPlan,
    PipelineInputSpec,
    PipelineOutputSpec,
    RoutePlan,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptCallBinding,
    JavascriptSchemaMemberOrder,
)
from vibeflow.targets.javascript.frontend.model_types import AotPlanError, ImplementationSpec


class EmissionNode(Protocol):
    id: str
    type_used: str
    implementation: object | None
    requires: Sequence[object]
    provides: Sequence[object]
    params: Mapping[str, Any]
    flow_kind: str
    join_policy: str
    async_mode: str
    result_key: str
    is_terminal: bool
    is_nodeset: bool
    is_loop: bool
    subplan: "EmissionWorkflow | None"
    loop: object
    capabilities: Sequence[object]
    completion: str
    schedule: str
    executor: str
    io_operation: str
    io_port: str


class EmissionWorkflow(Protocol):
    abi_version: str
    workflow_id: str
    inputs: Sequence[object]
    outputs: Sequence[object]
    nodes: Sequence[EmissionNode]
    routes: Sequence[object]
    order: Sequence[str]
    entries: Sequence[str]
    max_steps: int
    schemas: Mapping[str, Mapping[str, Any]]
    capabilities: Sequence[object]
    entry_mode: str

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BoundInputView:
    source: PipelineInputSpec
    schema: Mapping[str, Any] | None

    @property
    def key(self) -> str:
        return self.source.key

    @property
    def type(self) -> str:
        return self.source.type

    @property
    def required(self) -> bool:
        value = self.source.required
        if not isinstance(value, bool):
            raise AotPlanError(
                "pipeline input required must be explicitly true or false "
                "for JS AOT"
            )
        return value

    def to_dict(self) -> dict[str, Any]:
        return _schema_payload(
            dict(key=self.key, type=self.type, required=self.required),
            self.schema,
        )


@dataclass(frozen=True)
class BoundOutputView:
    source: PipelineOutputSpec
    schema: Mapping[str, Any] | None

    @property
    def type(self) -> str:
        return self.source.type

    @property
    def cardinality(self) -> str:
        return self.source.cardinality

    @property
    def alias(self) -> str:
        return self.source.as_key

    def to_dict(self) -> dict[str, Any]:
        return _schema_payload(
            dict(type=self.type, cardinality=self.cardinality, **{"as": self.alias}),
            self.schema,
        )


@dataclass(frozen=True)
class BoundRequirementView:
    source: object

    @property
    def type(self) -> str:
        return str(getattr(self.source, "type"))

    @property
    def cardinality(self) -> str:
        return str(getattr(self.source, "cardinality"))

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "cardinality": self.cardinality}


@dataclass(frozen=True)
class BoundProviderView:
    source: object

    @property
    def key(self) -> str:
        return str(getattr(self.source, "key"))

    @property
    def type(self) -> str:
        return str(getattr(self.source, "type"))

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "type": self.type}


@dataclass(frozen=True)
class BoundRouteView:
    source_plan: RoutePlan

    @property
    def source(self) -> str:
        return self.source_plan.source

    @property
    def target(self) -> str:
        return self.source_plan.target

    @property
    def condition(self) -> ConditionPlan | None:
        return self.source_plan.condition

    @property
    def schedule(self) -> bool:
        return self.source_plan.schedule

    @property
    def transfer(self) -> bool:
        return self.source_plan.transfer

    def to_dict(self) -> dict[str, Any]:
        payload = dict(
            source=self.source,
            target=self.target,
            schedule=self.schedule,
            transfer=self.transfer,
        )
        condition = self.condition.to_dict() if self.condition is not None else None
        return _optional_field(payload, "condition", condition)


@dataclass(frozen=True)
class BoundImplementationView:
    binding: JavascriptCallBinding

    @property
    def module(self) -> str:
        return self.binding.implementation.ref

    @property
    def export(self) -> str:
        return self.binding.implementation.export or "run"

    @property
    def language(self) -> str:
        return self.binding.language

    @property
    def completion(self) -> str:
        return self.binding.completion

    def to_dict(self) -> dict[str, str]:
        return dict(
            module=self.module,
            export=self.export,
            language=self.language,
            completion=self.completion,
        )


@dataclass(frozen=True)
class BoundCapabilityOperationView:
    input_type: str = ""
    output_type: str = ""
    completion: str = "immediate"

    def to_dict(self) -> dict[str, str]:
        return _truthy_fields(
            input_type=self.input_type,
            output_type=self.output_type,
            completion=self.completion,
        )


@dataclass(frozen=True)
class BoundCapabilityView:
    id: str
    operations: Mapping[str, BoundCapabilityOperationView]

    def to_dict(self) -> dict[str, Any]:
        return dict(
            id=self.id,
            operations={
                key: value.to_dict()
                for key, value in sorted(self.operations.items())
            },
        )


@dataclass(frozen=True)
class BoundLoopView:
    max_iterations: int | None = 1000
    stop_after: int = 0
    stop_when_source: str = ""
    stop_when_equals: bool = True
    carry: tuple[object, ...] = ()
    collect: tuple[object, ...] = ()
    outputs: tuple[object, ...] = ()

    @classmethod
    def from_plan(cls, value: LoopPlan | None) -> "BoundLoopView":
        if value is None:
            return cls()
        source = ""
        equals = True
        if value.stop_when is not None:
            condition = value.stop_when
            if not isinstance(condition.literal, bool):
                raise AotPlanError(
                    "loop stop condition must compare a boolean for JS AOT"
                )
            source = condition.key
            equals = (
                condition.literal
                if condition.operator == "=="
                else not condition.literal
            )
        return cls(
            max_iterations=value.max_iterations,
            stop_after=value.stop_after or 0,
            stop_when_source=source,
            stop_when_equals=equals,
            carry=tuple(value.carry),
            collect=tuple(value.collect),
            outputs=tuple(value.outputs),
        )

    def to_dict(self) -> dict[str, Any]:
        return _loop_payload(self)


def implementation_override(value: object) -> ImplementationSpec:
    """Normalize one legacy emitter implementation override."""

    if isinstance(value, ImplementationSpec):
        return value
    if isinstance(value, (str, Path)):
        return ImplementationSpec(module=str(value))
    if not isinstance(value, Mapping):
        raise TypeError(
            "implementation override must be a path, mapping, "
            "or ImplementationSpec"
        )
    source = value.get("source")
    source_map = source if isinstance(source, Mapping) else {}
    module = value.get("module", value.get("entry", value.get(
        "ref", source_map.get("ref", source_map.get("module", ""))
    )))
    if not str(module or "").strip():
        raise ValueError("implementation override requires module/ref")
    exported = value.get("export", source_map.get("export", "run"))
    return ImplementationSpec(
        module=str(module),
        export=str(exported or "run"),
        language=str(value.get("language", "javascript") or "javascript"),
        completion=str(value.get("completion", "immediate") or "immediate"),
    )


def module_specifier(value: str) -> str:
    module = str(value).strip()
    if not module:
        raise ValueError("node implementation module cannot be empty")
    if "\n" in module or "\r" in module or "\x00" in module:
        raise ValueError("node implementation module contains invalid characters")
    return module


def copy_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): copy_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [copy_json(item) for item in value]
    return value


def restore_properties_order(
    root: dict[str, Any],
    record: JavascriptSchemaMemberOrder,
) -> None:
    current: object = root
    for segment in record.path:
        try:
            current = current[segment] if isinstance(current, (dict, list)) else None
        except (IndexError, KeyError, TypeError) as exc:
            raise AotPlanError(
                "schema member-order path does not match frozen schema"
            ) from exc
    if not isinstance(current, dict):
        raise AotPlanError("schema member-order path does not identify an object schema")
    properties = current.get("properties")
    if not isinstance(properties, dict):
        raise AotPlanError("schema member-order record has no properties object")
    if set(properties) != set(record.members):
        raise AotPlanError("schema member-order keys do not match frozen schema")
    current["properties"] = {key: properties[key] for key in record.members}


def schema_order_path_key(value: JavascriptSchemaMemberOrder) -> str:
    return "/".join(str(item) for item in value.path)


def _schema_payload(
    payload: dict[str, Any],
    schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if schema is not None:
        payload["schema"] = dict(schema)
    return payload


def _optional_field(
    payload: dict[str, Any],
    key: str,
    value: object | None,
) -> dict[str, Any]:
    if value is not None:
        payload[key] = value
    return payload


def _truthy_fields(**values: str) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


def _loop_payload(loop: BoundLoopView) -> dict[str, Any]:
    payload = dict(
        max_iterations=loop.max_iterations,
        carry=[item.to_dict() for item in loop.carry],
        collect=[item.to_dict() for item in loop.collect],
        outputs=[item.to_dict() for item in loop.outputs],
    )
    if loop.stop_after:
        payload["stop_after"] = loop.stop_after
    if loop.stop_when_source:
        payload["stop_when"] = {
            "from": loop.stop_when_source,
            "equals": loop.stop_when_equals,
        }
    return payload


__all__ = [
    "BoundCapabilityOperationView",
    "BoundCapabilityView",
    "BoundImplementationView",
    "BoundInputView",
    "BoundLoopView",
    "BoundOutputView",
    "BoundProviderView",
    "BoundRequirementView",
    "BoundRouteView",
    "EmissionNode",
    "EmissionWorkflow",
    "copy_json",
    "implementation_override",
    "module_specifier",
    "restore_properties_order",
    "schema_order_path_key",
]
