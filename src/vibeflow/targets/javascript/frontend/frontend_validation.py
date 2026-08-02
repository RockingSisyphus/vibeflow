"""Validation helpers for the JavaScript workflow frontend."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping, Sequence

from vibeflow.targets.javascript.frontend.model_types import (
    ABI_VERSION,
    CARDINALITIES,
    COMPLETIONS,
    ENTRY_MODES,
    EXECUTORS,
    SCHEDULES,
    AotPlanError,
    WorkflowSpec,
)


def validate_workflow(plan: WorkflowSpec) -> None:
    if plan.entry_mode not in ENTRY_MODES:
        raise AotPlanError(
            f"entry_mode must be one of {sorted(ENTRY_MODES)}",
            code="VF_ENTRY_MODE",
        )
    assert_unique(
        (item.key for item in plan.inputs),
        field_name="pipeline input key",
    )
    assert_unique(
        (item.alias for item in plan.outputs),
        field_name="pipeline output alias",
    )
    assert_unique((item.id for item in plan.nodes), field_name="node id")
    node_ids = {node.id for node in plan.nodes}
    if set(plan.order) != node_ids or len(plan.order) != len(node_ids):
        raise AotPlanError(
            "workflow order must contain every node exactly once"
        )
    assert_unique(plan.entries, field_name="workflow entry")
    unknown_entries = sorted(set(plan.entries) - node_ids)
    if unknown_entries:
        raise AotPlanError(
            f"workflow entries contain unknown nodes: {unknown_entries}",
            code="VF_WORKFLOW_ENTRY",
        )
    incoming = {route.target for route in plan.routes if route.schedule}
    node_by_id = {node.id: node for node in plan.nodes}
    invalid_entries = [
        entry
        for entry in plan.entries
        if entry in incoming or not node_by_id[entry].is_terminal
    ]
    if invalid_entries:
        raise AotPlanError(
            (
                "workflow entries must be terminal nodes without incoming "
                f"routes: {invalid_entries}"
            ),
            code="VF_WORKFLOW_ENTRY",
        )
    if plan.nodes and not plan.entries:
        raise AotPlanError(
            "workflow block has nodes but no executable terminal entry",
            code="VF_WORKFLOW_ENTRY",
        )
    for route in plan.routes:
        if route.source not in node_ids:
            raise AotPlanError(
                f"route source '{route.source}' is not a workflow node"
            )
        if route.target not in node_ids:
            raise AotPlanError(
                f"route target '{route.target}' is not a workflow node"
            )
        if not route.schedule and not route.transfer:
            raise AotPlanError(
                (
                    f"route '{route.source} -> {route.target}' must schedule, "
                    "transfer, or both"
                )
            )
    for node in plan.nodes:
        assert_unique(
            (item.type for item in node.requires),
            field_name=f"node '{node.id}' requirement type",
        )
        assert_unique(
            (item.key for item in node.provides),
            field_name=f"node '{node.id}' provider key",
        )
        if (node.is_nodeset or node.is_loop) and node.subplan is None:
            raise AotPlanError(
                f"composite node '{node.id}' has no portable subplan"
            )
        if node.is_loop:
            if (
                node.loop.max_iterations is not None
                and node.loop.max_iterations < 1
            ):
                raise AotPlanError(
                    f"loop node '{node.id}' max_iterations must be null or positive"
                )
        if node.completion not in COMPLETIONS:
            raise AotPlanError(
                f"node '{node.id}' has invalid completion '{node.completion}'"
            )
        if node.schedule not in SCHEDULES:
            raise AotPlanError(
                f"node '{node.id}' has invalid schedule '{node.schedule}'"
            )
        if node.executor not in EXECUTORS:
            raise AotPlanError(
                f"node '{node.id}' has invalid executor '{node.executor}'"
            )
        if node.type_used == "vibeflow.io":
            if node.io_operation not in {"receive", "send"}:
                raise AotPlanError(
                    f"vibeflow.io node '{node.id}' must declare receive or send",
                    code="VF_IO_OPERATION",
                )
            if not node.io_port:
                raise AotPlanError(
                    f"vibeflow.io node '{node.id}' must declare a port",
                    code="VF_IO_PORT",
                )
            if node.io_operation == "receive" and (
                node.requires
                or len(node.provides) != 1
                or node.completion != "suspend"
            ):
                raise AotPlanError(
                    (
                        f"vibeflow.io receive node '{node.id}' requires zero "
                        "inputs, one output, and suspend completion"
                    ),
                    code="VF_IO_CONTRACT",
                )
            if node.io_operation == "send" and (
                len(node.requires) != 1
                or node.requires[0].cardinality != "exactly_one"
                or node.provides
                or node.completion != "immediate"
            ):
                raise AotPlanError(
                    (
                        f"vibeflow.io send node '{node.id}' requires one "
                        "exactly_one input, zero outputs, and immediate completion"
                    ),
                    code="VF_IO_CONTRACT",
                )
        if plan.entry_mode == "sync" and node.completion == "suspend":
            raise AotPlanError(
                (
                    f"sync workflow contains suspending node '{node.id}'; "
                    "declare pipeline.entry_mode='async'"
                ),
                code="VF_ENTRY_MODE_SUSPEND_IN_SYNC",
            )
        if plan.entry_mode == "sync" and node.schedule != "inline":
            raise AotPlanError(
                (
                    f"sync workflow contains {node.schedule} task "
                    f"'{node.id}'; declare pipeline.entry_mode='async'"
                ),
                code="VF_ENTRY_MODE_TASK_IN_SYNC",
            )
    declared_capabilities = {item.id: item for item in plan.capabilities}
    for node in plan.nodes:
        for requirement in node.capabilities:
            descriptor = declared_capabilities.get(requirement.id)
            if descriptor is None:
                raise AotPlanError(
                    (
                        f"node '{node.id}' requires undeclared capability "
                        f"'{requirement.id}'"
                    )
                )
            unknown = sorted(
                set(requirement.operations) - set(descriptor.operations)
            )
            if unknown:
                raise AotPlanError(
                    (
                        f"node '{node.id}' requires unknown operations on "
                        f"capability '{requirement.id}': {unknown}"
                    )
                )


def schema_for(
    raw: Mapping[str, Any],
    *,
    type_key: str,
    schemas: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    schema = raw.get("schema", schemas.get(type_key))
    if schema is None:
        return None
    return dict(as_mapping(schema, field_name=f"schema for '{type_key}'"))


def parse_schemas(value: object) -> dict[str, Mapping[str, Any]]:
    if value in (None, (), []):
        return {}
    if isinstance(value, Mapping):
        out: dict[str, Mapping[str, Any]] = {}
        for key, item in value.items():
            if isinstance(item, Mapping) and "schema" in item:
                item = item["schema"]
            out[str(key)] = dict(
                as_mapping(item, field_name=f"schemas.{key}")
            )
        return out
    out = {}
    for index, item in enumerate(sequence(value, field_name="schemas")):
        raw = as_mapping(item, field_name=f"schemas[{index}]")
        type_key = required_text(
            raw.get("type", raw.get("id")),
            field_name=f"schemas[{index}].type",
        )
        out[type_key] = dict(
            as_mapping(
                raw.get("schema"),
                field_name=f"schemas[{index}].schema",
            )
        )
    return out


def nodes_from_blocks(value: object) -> list[object]:
    nodes: list[object] = []

    def visit(block_value: object) -> None:
        raw = as_mapping(block_value, field_name="blocks[]")
        nodes.extend(
            sequence(raw.get("nodes", ()), field_name="blocks[].nodes")
        )
        for child in sequence(
            raw.get("children", ()),
            field_name="blocks[].children",
        ):
            visit(child)

    for block in sequence(value, field_name="blocks"):
        visit(block)
    return nodes


def workflow_mapping_from_blocks(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Turn canonical portable block references into nested AOT subplans."""

    block_items = sequence(value.get("blocks", ()), field_name="blocks")
    blocks: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(block_items):
        block = as_mapping(item, field_name=f"blocks[{index}]")
        block_id = required_text(
            block.get("id"),
            field_name=f"blocks[{index}].id",
        )
        if block_id in blocks:
            raise AotPlanError(f"duplicate block id: {block_id}")
        blocks[block_id] = block
    entry_id = required_text(
        value.get("entry_block"),
        field_name="entry_block",
    )
    if entry_id not in blocks:
        raise AotPlanError(f"entry_block '{entry_id}' does not exist")

    active: set[str] = set()

    def expand(block_id: str, workflow_id: str) -> dict[str, Any]:
        if block_id in active:
            raise AotPlanError(
                (
                    "recursive portable block reference cannot target JS: "
                    f"{block_id}"
                )
            )
        block = blocks.get(block_id)
        if block is None:
            raise AotPlanError(f"child_block '{block_id}' does not exist")
        active.add(block_id)
        try:
            nodes: list[dict[str, Any]] = []
            for index, node_value in enumerate(
                sequence(
                    block.get("nodes", ()),
                    field_name=f"block '{block_id}'.nodes",
                )
            ):
                node = dict(
                    as_mapping(
                        node_value,
                        field_name=f"block '{block_id}'.nodes[{index}]",
                    )
                )
                child_block = str(node.get("child_block", "") or "")
                if child_block:
                    node["subplan"] = expand(
                        child_block,
                        f"{workflow_id}.{node.get('id', index)}",
                    )
                    child = blocks[child_block]
                    if bool(node.get("is_loop", False)):
                        node["loop"] = child.get("loop") or {}
                nodes.append(node)
            inputs = (
                value.get("inputs", ())
                if block_id == entry_id
                else block.get("inputs", ())
            )
            outputs = (
                value.get("outputs", ())
                if block_id == entry_id
                else block.get("outputs", ())
            )
            return {
                "abi_version": value.get("abi_version", ABI_VERSION),
                "workflow_id": workflow_id,
                "inputs": inputs,
                "outputs": outputs,
                "nodes": nodes,
                "routes": block.get("routes", ()),
                "order": block.get("order", ()),
                "entries": block.get("entries"),
                "max_steps": block.get(
                    "max_steps",
                    value.get("max_steps", 1000),
                ),
                "schemas": value.get(
                    "schemas",
                    value.get("data_schemas", {}),
                ),
                "capabilities": value.get("capabilities", ()),
                "entry_mode": value.get("entry_mode", "sync"),
            }
        finally:
            active.remove(block_id)

    return expand(
        entry_id,
        required_text(
            value.get("workflow_id", value.get("id", "")),
            field_name="workflow_id",
        ),
    )


def with_default_workflow_id(
    value: object,
    default: str,
) -> Mapping[str, Any]:
    raw = dict(as_mapping(value, field_name="subplan"))
    raw.setdefault("workflow_id", default)
    raw.setdefault("abi_version", ABI_VERSION)
    if "nodes" not in raw and "blocks" not in raw:
        raw["nodes"] = ()
    raw.setdefault("inputs", ())
    raw.setdefault("outputs", ())
    raw.setdefault("routes", ())
    return raw


def capability_items(value: object) -> tuple[object, ...]:
    if isinstance(value, Mapping):
        return tuple(
            {
                "id": key,
                **dict(
                    as_mapping(
                        item,
                        field_name=f"capabilities.{key}",
                    )
                ),
            }
            for key, item in value.items()
        )
    return tuple(sequence(value, field_name="capabilities"))


def capability_requirement_items(value: object) -> tuple[object, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(
            {"id": key, "operations": item}
            if isinstance(item, Sequence)
            and not isinstance(item, (str, bytes))
            else {
                "id": key,
                **dict(
                    as_mapping(
                        item,
                        field_name=f"capability requirement {key}",
                    )
                ),
            }
            for key, item in value.items()
        )
    return tuple(sequence(value, field_name="capability requirements"))


def as_mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        value = value.to_dict()
    elif is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, Mapping):
        raise AotPlanError(f"{field_name} must be an object")
    return {str(key): item for key, item in value.items()}


def mapping_or_empty(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if value in (None, ""):
        return {}
    return as_mapping(value, field_name=field_name)


def sequence(value: object, *, field_name: str) -> list[object]:
    if value in (None, ()):
        return []
    if (
        isinstance(value, (str, bytes, Mapping))
        or not isinstance(value, Sequence)
    ):
        raise AotPlanError(f"{field_name} must be a list")
    return list(value)


def required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AotPlanError(f"{field_name} must be a non-empty string")
    return text


def cardinality(value: object, *, field_name: str) -> str:
    text = required_text(value, field_name=field_name)
    if text not in CARDINALITIES:
        raise AotPlanError(
            f"{field_name} must be one of {sorted(CARDINALITIES)}"
        )
    return text


def positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise AotPlanError(f"{field_name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AotPlanError(
            f"{field_name} must be a positive integer"
        ) from exc
    if number <= 0:
        raise AotPlanError(f"{field_name} must be a positive integer")
    return number


def non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise AotPlanError(
            f"{field_name} must be a non-negative integer"
        )
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AotPlanError(
            f"{field_name} must be a non-negative integer"
        ) from exc
    if number < 0:
        raise AotPlanError(
            f"{field_name} must be a non-negative integer"
        )
    return number


def assert_unique(values: Iterable[str], *, field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise AotPlanError(f"duplicate {field_name}: {value}")
        seen.add(value)


__all__ = [
    "as_mapping",
    "assert_unique",
    "capability_items",
    "capability_requirement_items",
    "cardinality",
    "mapping_or_empty",
    "nodes_from_blocks",
    "non_negative_int",
    "parse_schemas",
    "positive_int",
    "required_text",
    "schema_for",
    "sequence",
    "validate_workflow",
    "with_default_workflow_id",
    "workflow_mapping_from_blocks",
]
