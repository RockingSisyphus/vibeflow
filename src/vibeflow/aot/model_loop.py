from __future__ import annotations

from vibeflow.aot.model_types import (
    AotPlanError,
    CapabilityOperation,
    CapabilityRequirement,
    CapabilitySpec,
    LoopCarry,
    LoopCollect,
    LoopOutput,
    LoopSpec,
)
from vibeflow.aot.model_validation import (
    as_mapping,
    mapping_or_empty,
    non_negative_int,
    positive_int,
    required_text,
    sequence,
)


def parse_loop(value: object, *, node_id: str) -> LoopSpec:
    raw = mapping_or_empty(value, field_name=f"node '{node_id}'.loop")
    stop_when_raw = mapping_or_empty(
        raw.get("stop_when", {}),
        field_name=f"node '{node_id}'.loop.stop_when",
    )
    stop_when_source = str(
        stop_when_raw.get(
            "from",
            stop_when_raw.get("source", stop_when_raw.get("key", "")),
        )
        or ""
    )
    if "key" in stop_when_raw:
        operator = str(stop_when_raw.get("operator", "") or "")
        literal = stop_when_raw.get("literal")
        if operator not in {"==", "!="} or not isinstance(literal, bool):
            raise AotPlanError(
                (
                    f"node '{node_id}'.loop.stop_when canonical condition "
                    "must compare a boolean with == or !="
                )
            )
        stop_when_equals = literal if operator == "==" else not literal
    else:
        raw_equals = stop_when_raw.get("equals", True)
        if not isinstance(raw_equals, bool):
            raise AotPlanError(
                f"node '{node_id}'.loop.stop_when.equals must be boolean"
            )
        stop_when_equals = raw_equals
    stop_after_raw = raw.get("stop_after", 0)
    max_iterations_raw = raw.get("max_iterations", 1000)
    return LoopSpec(
        max_iterations=(
            None
            if max_iterations_raw is None
            else positive_int(
                max_iterations_raw,
                field_name=f"node '{node_id}'.loop.max_iterations",
            )
        ),
        stop_after=non_negative_int(
            0 if stop_after_raw is None else stop_after_raw,
            field_name=f"node '{node_id}'.loop.stop_after",
        ),
        stop_when_source=stop_when_source,
        stop_when_equals=stop_when_equals,
        carry=tuple(
            LoopCarry(
                source=required_text(
                    as_mapping(item, field_name="loop.carry[]").get(
                        "from",
                        as_mapping(
                            item,
                            field_name="loop.carry[]",
                        ).get("source"),
                    ),
                    field_name="loop.carry[].from",
                ),
                target=required_text(
                    as_mapping(item, field_name="loop.carry[]").get(
                        "as",
                        as_mapping(
                            item,
                            field_name="loop.carry[]",
                        ).get("target"),
                    ),
                    field_name="loop.carry[].as",
                ),
                update=required_text(
                    as_mapping(
                        item,
                        field_name="loop.carry[]",
                    ).get("update"),
                    field_name="loop.carry[].update",
                ),
            )
            for item in sequence(
                raw.get("carry", ()),
                field_name="loop.carry",
            )
        ),
        collect=tuple(
            LoopCollect(
                source=required_text(
                    as_mapping(item, field_name="loop.collect[]").get(
                        "from",
                        as_mapping(
                            item,
                            field_name="loop.collect[]",
                        ).get("source"),
                    ),
                    field_name="loop.collect[].from",
                ),
                target=required_text(
                    as_mapping(item, field_name="loop.collect[]").get(
                        "as",
                        as_mapping(
                            item,
                            field_name="loop.collect[]",
                        ).get("target"),
                    ),
                    field_name="loop.collect[].as",
                ),
                mode=str(
                    as_mapping(
                        item,
                        field_name="loop.collect[]",
                    ).get("mode", "all")
                    or "all"
                ),
            )
            for item in sequence(
                raw.get("collect", ()),
                field_name="loop.collect",
            )
        ),
        outputs=tuple(
            LoopOutput(
                source=required_text(
                    as_mapping(item, field_name="loop.outputs[]").get(
                        "from",
                        as_mapping(
                            item,
                            field_name="loop.outputs[]",
                        ).get("source"),
                    ),
                    field_name="loop.outputs[].from",
                ),
                target=required_text(
                    as_mapping(item, field_name="loop.outputs[]").get(
                        "as",
                        as_mapping(
                            item,
                            field_name="loop.outputs[]",
                        ).get("target"),
                    ),
                    field_name="loop.outputs[].as",
                ),
            )
            for item in sequence(
                raw.get("outputs", ()),
                field_name="loop.outputs",
            )
        ),
    )


def parse_capability(value: object, *, index: int) -> CapabilitySpec:
    raw = as_mapping(value, field_name=f"capabilities[{index}]")
    operations_raw = as_mapping(
        raw.get("operations", {}),
        field_name=f"capabilities[{index}].operations",
    )
    operations: dict[str, CapabilityOperation] = {}
    for operation_name, operation_value in operations_raw.items():
        operation = as_mapping(
            operation_value,
            field_name=(
                f"capabilities[{index}].operations.{operation_name}"
            ),
        )
        operations[str(operation_name)] = CapabilityOperation(
            input_type=str(operation.get("input_type", "") or ""),
            output_type=str(operation.get("output_type", "") or ""),
            completion=str(
                operation.get("completion", "immediate")
                or "immediate"
            ),
        )
    return CapabilitySpec(
        id=required_text(
            raw.get("id"),
            field_name=f"capabilities[{index}].id",
        ),
        operations=operations,
    )


def parse_capability_requirement(
    value: object,
    *,
    field_name: str,
) -> CapabilityRequirement:
    if isinstance(value, str):
        return CapabilityRequirement(
            id=required_text(value, field_name=field_name),
            operations=(),
        )
    raw = as_mapping(value, field_name=field_name)
    operations = tuple(
        required_text(
            item,
            field_name=f"{field_name}.operations[]",
        )
        for item in sequence(
            raw.get("operations", ()),
            field_name=f"{field_name}.operations",
        )
    )
    return CapabilityRequirement(
        id=required_text(
            raw.get("id"),
            field_name=f"{field_name}.id",
        ),
        operations=operations,
    )


__all__ = [
    "parse_capability",
    "parse_capability_requirement",
    "parse_loop",
]
