"""Normalize portable workflow mappings for the JavaScript Target."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.frontend_condition import parse_condition
from vibeflow.targets.javascript.frontend.frontend_loop import (
    parse_capability,
    parse_capability_requirement,
    parse_loop,
)
from vibeflow.targets.javascript.frontend.model_types import (
    ABI_VERSION,
    ASYNC_MODES,
    COMPLETIONS,
    ENTRY_MODES,
    EXECUTORS,
    JOIN_POLICIES,
    SCHEDULES,
    AotPlanError,
    ImplementationSpec,
    InputSpec,
    NodeSpec,
    OutputSpec,
    ProviderSpec,
    RequirementSpec,
    RouteSpec,
    TaskSpec,
    WorkflowSpec,
)
from vibeflow.targets.javascript.frontend.frontend_validation import (
    as_mapping,
    capability_items,
    capability_requirement_items,
    cardinality,
    mapping_or_empty,
    nodes_from_blocks,
    parse_schemas,
    positive_int,
    required_text,
    schema_for,
    sequence,
    validate_workflow,
    with_default_workflow_id,
    workflow_mapping_from_blocks,
)


def parse_workflow(
    value: object,
    *,
    workflow_type: type[WorkflowSpec] = WorkflowSpec,
) -> WorkflowSpec:
    raw = as_mapping(value, field_name="workflow plan")
    _reject_unsupported_target_features(raw, field_name="workflow plan")
    if raw.get("entry_block") and raw.get("blocks") is not None:
        raw = workflow_mapping_from_blocks(raw)
    workflow_id = required_text(
        raw.get("workflow_id", raw.get("id", "")),
        field_name="workflow_id",
    )
    entry_mode = str(raw.get("entry_mode", "sync") or "sync")
    if entry_mode not in ENTRY_MODES:
        raise AotPlanError(
            f"entry_mode must be one of {sorted(ENTRY_MODES)}",
            code="VF_ENTRY_MODE",
        )
    abi_version = str(raw.get("abi_version", ABI_VERSION) or ABI_VERSION)
    if abi_version != ABI_VERSION:
        raise AotPlanError(
            (
                f"unsupported workflow ABI '{abi_version}'; "
                f"expected '{ABI_VERSION}'"
            )
        )
    schemas = parse_schemas(
        raw.get("schemas", raw.get("data_schemas", {}))
    )
    inputs = tuple(
        _parse_input(item, schemas=schemas, index=index)
        for index, item in enumerate(
            sequence(raw.get("inputs", ()), field_name="inputs")
        )
    )
    outputs = tuple(
        _parse_output(item, schemas=schemas, index=index)
        for index, item in enumerate(
            sequence(raw.get("outputs", ()), field_name="outputs")
        )
    )
    node_items = raw.get("nodes")
    if node_items is None:
        node_items = nodes_from_blocks(raw.get("blocks", ()))
    nodes = tuple(
        _parse_node(
            item,
            parent_workflow=workflow_id,
            parent_entry_mode=entry_mode,
            index=index,
        )
        for index, item in enumerate(
            sequence(node_items, field_name="nodes")
        )
    )
    routes = tuple(
        _parse_route(item, index=index)
        for index, item in enumerate(
            sequence(raw.get("routes", ()), field_name="routes")
        )
    )
    order_raw = raw.get("order")
    order = (
        tuple(
            required_text(item, field_name="order[]")
            for item in sequence(order_raw, field_name="order")
        )
        if order_raw is not None
        else tuple(node.id for node in nodes)
    )
    entries_raw = raw.get("entries")
    if entries_raw is None:
        incoming = {route.target for route in routes if route.schedule}
        terminal_by_id = {node.id: node.is_terminal for node in nodes}
        entries = tuple(
            node_id
            for node_id in order
            if node_id not in incoming
            and terminal_by_id.get(node_id, False)
        )
    else:
        entries = tuple(
            required_text(item, field_name="entries[]")
            for item in sequence(entries_raw, field_name="entries")
        )
    max_steps = positive_int(
        raw.get("max_steps", 1000),
        field_name="max_steps",
    )
    capabilities = tuple(
        parse_capability(item, index=index)
        for index, item in enumerate(
            capability_items(raw.get("capabilities", ()))
        )
    )
    tasks = tuple(
        TaskSpec(
            id=f"task:{node.id}",
            node_id=node.id,
            schedule=node.schedule,
            executor=node.executor,
            result_key=node.result_key,
        )
        for node in nodes
        if node.schedule != "inline"
    )
    plan = workflow_type(
        workflow_id=workflow_id,
        inputs=inputs,
        outputs=outputs,
        nodes=nodes,
        routes=routes,
        order=order,
        entries=entries,
        max_steps=max_steps,
        schemas=schemas,
        capabilities=capabilities,
        abi_version=abi_version,
        entry_mode=entry_mode,
        tasks=tasks,
    )
    validate_workflow(plan)
    return plan


def _reject_unsupported_target_features(
    raw: Mapping[str, Any],
    *,
    field_name: str,
) -> None:
    if bool(raw.get("contains_global_state", False)):
        _unsupported_target_feature("global_state", field_name=field_name)
    if raw.get("execution_lock") is not None:
        _unsupported_target_feature("execution_locks", field_name=field_name)
    for index, block_value in enumerate(
        sequence(raw.get("blocks", ()), field_name=f"{field_name}.blocks")
    ):
        block = as_mapping(
            block_value,
            field_name=f"{field_name}.blocks[{index}]",
        )
        _reject_unsupported_target_features(
            block,
            field_name=f"{field_name}.blocks[{index}]",
        )
    for index, node_value in enumerate(
        sequence(raw.get("nodes", ()), field_name=f"{field_name}.nodes")
    ):
        node = as_mapping(
            node_value,
            field_name=f"{field_name}.nodes[{index}]",
        )
        node_field = f"{field_name}.nodes[{index}]"
        status = str(node.get("status", "implemented") or "implemented")
        if status != "planned" and node.get("execution_lock") is not None:
            _unsupported_target_feature(
                "execution_locks",
                field_name=node_field,
            )
        if status != "planned" and (
            str(node.get("flow_kind", "") or "") == "global_state"
            or str(node.get("effect_scope", "") or "") == "global_state"
            or bool(node.get("contains_global_state", False))
        ):
            _unsupported_target_feature(
                "global_state",
                field_name=node_field,
            )
        child = node.get("subplan", node.get("children"))
        if isinstance(child, Mapping):
            _reject_unsupported_target_features(
                child,
                field_name=f"{node_field}.subplan",
            )


def _unsupported_target_feature(feature: str, *, field_name: str) -> None:
    raise AotPlanError(
        f"JavaScript target does not support feature '{feature}' at {field_name}",
        code="TARGET.FEATURE.UNSUPPORTED",
    )


def _parse_input(
    value: object,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
    index: int,
) -> InputSpec:
    raw = as_mapping(value, field_name=f"inputs[{index}]")
    key = required_text(
        raw.get("key"),
        field_name=f"inputs[{index}].key",
    )
    type_key = required_text(
        raw.get("type"),
        field_name=f"inputs[{index}].type",
    )
    if "required" not in raw or not isinstance(raw["required"], bool):
        raise AotPlanError(
            (
                f"inputs[{index}].required must be explicitly true or false "
                "for JS AOT"
            )
        )
    schema = schema_for(raw, type_key=type_key, schemas=schemas)
    return InputSpec(
        key=key,
        type=type_key,
        required=bool(raw["required"]),
        schema=schema,
    )


def _parse_output(
    value: object,
    *,
    schemas: Mapping[str, Mapping[str, Any]],
    index: int,
) -> OutputSpec:
    raw = as_mapping(value, field_name=f"outputs[{index}]")
    type_key = required_text(
        raw.get("type"),
        field_name=f"outputs[{index}].type",
    )
    output_cardinality = cardinality(
        raw.get("cardinality"),
        field_name=f"outputs[{index}].cardinality",
    )
    alias = required_text(
        raw.get("as", raw.get("alias", type_key)),
        field_name=f"outputs[{index}].as",
    )
    schema = schema_for(raw, type_key=type_key, schemas=schemas)
    return OutputSpec(
        type=type_key,
        cardinality=output_cardinality,
        alias=alias,
        schema=schema,
    )


def _parse_node(
    value: object,
    *,
    parent_workflow: str,
    parent_entry_mode: str,
    index: int,
) -> NodeSpec:
    raw = as_mapping(value, field_name=f"nodes[{index}]")
    node_id = required_text(
        raw.get("id"),
        field_name=f"nodes[{index}].id",
    )
    type_used = required_text(
        raw.get("type_used", raw.get("type")),
        field_name=f"nodes[{index}].type_used",
    )
    is_nodeset = bool(raw.get("is_nodeset", False))
    is_loop = bool(raw.get("is_loop", False))
    subplan_value = raw.get("subplan")
    if subplan_value is None and isinstance(raw.get("children"), Mapping):
        subplan_value = raw["children"]
    subplan_payload = (
        dict(
            with_default_workflow_id(
                subplan_value,
                f"{parent_workflow}.{node_id}",
            )
        )
        if subplan_value is not None
        else None
    )
    if subplan_payload is not None:
        subplan_payload.setdefault("entry_mode", parent_entry_mode)
    subplan = (
        WorkflowSpec.from_portable(subplan_payload)
        if subplan_value is not None
        else None
    )
    implementation = _parse_implementation(raw.get("implementation"))
    if (
        not (is_nodeset or is_loop)
        and type_used != "vibeflow.io"
        and implementation is None
    ):
        raise AotPlanError(
            f"node '{node_id}' has no JavaScript/TypeScript implementation"
        )
    requires = tuple(
        _parse_requirement(
            item,
            field_name=f"nodes[{index}].requires[{item_index}]",
        )
        for item_index, item in enumerate(
            sequence(
                raw.get("requires", ()),
                field_name=f"nodes[{index}].requires",
            )
        )
    )
    provides = tuple(
        _parse_provider(
            item,
            field_name=f"nodes[{index}].provides[{item_index}]",
        )
        for item_index, item in enumerate(
            sequence(
                raw.get("provides", ()),
                field_name=f"nodes[{index}].provides",
            )
        )
    )
    join_policy = str(raw.get("join_policy", "safe_any") or "safe_any")
    if join_policy not in JOIN_POLICIES:
        raise AotPlanError(
            f"node '{node_id}' has unsupported join_policy '{join_policy}'"
        )
    async_mode = str(raw.get("async_mode", raw.get("async", "")) or "")
    if async_mode not in ASYNC_MODES:
        raise AotPlanError(
            f"node '{node_id}' has unsupported async_mode '{async_mode}'"
        )
    result_key = str(raw.get("result_key", "") or "")
    if (
        async_mode == "result_key"
        and result_key not in {item.key for item in provides}
    ):
        raise AotPlanError(
            f"async node '{node_id}' result_key must be declared in provides"
        )
    status = str(raw.get("status", "implemented") or "implemented")
    planned = raw.get("planned_behavior")
    if status == "planned" or planned not in (None, "", {}, "blocking"):
        raise AotPlanError(
            (
                f"node '{node_id}' uses planned/Python-only behavior and "
                "cannot target JS"
            )
        )
    flow_kind = str(raw.get("flow_kind", "") or "")
    completion = str(
        raw.get(
            "completion",
            implementation.completion if implementation else "immediate",
        )
        or "immediate"
    )
    if completion not in COMPLETIONS:
        raise AotPlanError(
            f"node '{node_id}' has unsupported completion '{completion}'",
            code="VF_COMPLETION",
        )
    legacy_schedule = {
        "": "inline",
        "result_key": "deferred",
        "detached": "detached",
    }[async_mode]
    schedule = str(raw.get("schedule", legacy_schedule) or legacy_schedule)
    if schedule not in SCHEDULES:
        raise AotPlanError(
            f"node '{node_id}' has unsupported schedule '{schedule}'",
            code="VF_SCHEDULE",
        )
    if async_mode and schedule != legacy_schedule:
        raise AotPlanError(
            f"node '{node_id}' schedule conflicts with legacy async_mode",
            code="VF_SCHEDULE",
        )
    executor_default = (
        "event_loop"
        if completion == "suspend" or schedule != "inline"
        else "current"
    )
    executor = str(raw.get("executor", executor_default) or executor_default)
    if executor not in EXECUTORS:
        raise AotPlanError(
            f"node '{node_id}' has unsupported executor '{executor}'",
            code="VF_EXECUTOR",
        )
    return NodeSpec(
        id=node_id,
        type_used=type_used,
        implementation=implementation,
        requires=requires,
        provides=provides,
        params=dict(
            mapping_or_empty(
                raw.get("params", raw.get("config", {})),
                field_name=f"nodes[{index}].params",
            )
        ),
        flow_kind=flow_kind,
        join_policy=join_policy,
        async_mode=async_mode,
        result_key=result_key,
        is_terminal=bool(raw.get("is_terminal", flow_kind == "terminal")),
        is_nodeset=is_nodeset,
        is_loop=is_loop,
        subplan=subplan,
        loop=parse_loop(
            raw.get("loop", raw.get("loop_spec", {})),
            node_id=node_id,
        ),
        capabilities=tuple(
            parse_capability_requirement(
                item,
                field_name=(
                    f"nodes[{index}].capabilities[{item_index}]"
                ),
            )
            for item_index, item in enumerate(
                capability_requirement_items(
                    raw.get(
                        "capabilities",
                        raw.get("required_capabilities", ()),
                    )
                )
            )
        ),
        completion=completion,
        schedule=schedule,
        executor=executor,
        io_operation=str(
            raw.get(
                "io_operation",
                (
                    raw.get("io", {}).get("operation", "")
                    if isinstance(raw.get("io"), Mapping)
                    else ""
                ),
            )
            or ""
        ),
        io_port=str(
            raw.get(
                "io_port",
                (
                    raw.get("io", {}).get("port", "")
                    if isinstance(raw.get("io"), Mapping)
                    else ""
                ),
            )
            or ""
        ),
    )


def _parse_implementation(value: object) -> ImplementationSpec | None:
    if value in (None, "", {}):
        return None
    if isinstance(value, (str, Path)):
        return ImplementationSpec(module=str(value))
    raw = as_mapping(value, field_name="implementation")
    source = raw.get("source")
    source_map = source if isinstance(source, Mapping) else {}
    module = raw.get(
        "module",
        raw.get(
            "entry",
            raw.get(
                "ref",
                source_map.get("ref", source_map.get("module", "")),
            ),
        ),
    )
    module_text = required_text(
        module,
        field_name="implementation.module",
    )
    export = required_text(
        raw.get("export", source_map.get("export", "run")),
        field_name="implementation.export",
    )
    language = str(raw.get("language", "") or "").lower()
    if not language:
        suffix = Path(module_text).suffix.lower()
        language = (
            "typescript"
            if suffix in {".ts", ".tsx", ".mts"}
            else "javascript"
        )
    if language not in {"javascript", "typescript", "js", "ts"}:
        raise AotPlanError(
            (
                f"implementation '{module_text}' has unsupported language "
                f"'{language}'"
            )
        )
    completion = str(raw.get("completion", "immediate") or "immediate")
    if completion not in COMPLETIONS:
        raise AotPlanError(
            f"implementation.completion must be one of {sorted(COMPLETIONS)}",
            code="VF_COMPLETION",
        )
    return ImplementationSpec(
        module=module_text,
        export=export,
        language=(
            "typescript"
            if language in {"typescript", "ts"}
            else "javascript"
        ),
        completion=completion,
    )


def _parse_requirement(
    value: object,
    *,
    field_name: str,
) -> RequirementSpec:
    raw = as_mapping(value, field_name=field_name)
    return RequirementSpec(
        type=required_text(
            raw.get("type"),
            field_name=f"{field_name}.type",
        ),
        cardinality=cardinality(
            raw.get("cardinality"),
            field_name=f"{field_name}.cardinality",
        ),
    )


def _parse_provider(
    value: object,
    *,
    field_name: str,
) -> ProviderSpec:
    raw = as_mapping(value, field_name=field_name)
    return ProviderSpec(
        key=required_text(
            raw.get("key"),
            field_name=f"{field_name}.key",
        ),
        type=required_text(
            raw.get("type"),
            field_name=f"{field_name}.type",
        ),
    )


def _parse_route(value: object, *, index: int) -> RouteSpec:
    raw = as_mapping(value, field_name=f"routes[{index}]")
    source = required_text(
        raw.get("source", raw.get("from")),
        field_name=f"routes[{index}].source",
    )
    target = required_text(
        raw.get("target", raw.get("to")),
        field_name=f"routes[{index}].target",
    )
    condition = parse_condition(
        raw.get("condition", raw.get("when")),
        field_name=f"routes[{index}].condition",
    )
    return RouteSpec(
        source=source,
        target=target,
        condition=condition,
        schedule=bool(raw.get("schedule", True)),
        transfer=bool(raw.get("transfer", True)),
    )


__all__ = ["parse_workflow"]
