from __future__ import annotations

from typing import Any, Mapping

from vibeflow.core.contracts import (
    DataProvider,
    DataRequirement,
    parse_data_providers,
    parse_data_requirements,
    parse_pipeline_inputs,
    parse_pipeline_outputs,
    provider_keys,
)
from vibeflow.core.flow import (
    EdgeSpec, ExecutionLockSpec, GraphConfig, GraphConfigError, JOIN_POLICIES, JOIN_POLICY_SAFE_ANY, JOIN_POLICY_ALL, JOIN_POLICY_ANY_ACTIVE,
    ENTRY_MODES, ENTRY_MODE_SYNC,
    IO_NODE_TYPE, IO_OPERATIONS, IoSpec, LOOP_NODE_TYPES, LOOP_WHILE_TYPE, LoopCarrySpec, LoopCollectSpec, LoopOutputSpec, LoopSpec, LoopStopWhenSpec,
    NodeMetadata, NodeSimilarity, NodeSpec, NodeStyle, NodesetSpec, SIMILAR_TO_RELATIONSHIPS, STATUSES, STATUS_IMPLEMENTED, STATUS_PLANNED,
)
from vibeflow.core.config.edge import parse_edge as _parse_edge
from vibeflow.core.constants import FLOW_KINDS, FLOW_KIND_PREDEFINED
from vibeflow.core.planned import PlannedBehavior, parse_planned_behavior
from vibeflow.core.style import (
    NODE_STYLE_FIELDS,
    is_hex_color,
    is_reserved_system_color,
    normalize_hex_color,
)


def parse_graph_config_data(
    config: Mapping[str, Any],
    *,
    project_root: str = "",
    root_id: str = "",
    root_path: str = "",
    source_path: str = "",
) -> GraphConfig:
    raw = config.get("pipeline", config)
    root_text = str(project_root)
    actual_root_path = str(root_path) or root_text
    actual_source_path = str(source_path)
    if not isinstance(raw, Mapping):
        raise GraphConfigError("pipeline config must be an object")
    if "boundary" in config:
        raise GraphConfigError("boundary is removed; use terminal/io/data_store/document nodes")
    nodesets = _parse_nodesets(
        config.get("nodesets", raw.get("nodesets", [])),
        project_root=root_text,
        root_id=root_id,
        root_path=actual_root_path,
    )
    graph = _parse_graph_body(
        raw,
        nodesets=nodesets,
        known_nodesets=set(nodesets),
        project_root=root_text,
        field="pipeline",
        root_id=root_id,
        root_path=actual_root_path,
        source_path=actual_source_path,
    )
    return graph


def _parse_graph_body(
    raw: Mapping[str, Any],
    *,
    nodesets: dict[str, NodesetSpec],
    known_nodesets: set[str],
    project_root: str,
    field: str,
    root_id: str = "",
    root_path: str = "",
    source_path: str = "",
) -> GraphConfig:
    if "boundary" in raw:
        raise GraphConfigError("boundary is removed; use terminal/io/data_store/document nodes")
    if "loops" in raw:
        raise GraphConfigError("pipeline.loops is removed; use vibeflow.loop.while nodes")
    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise GraphConfigError(f"{field}.nodes must be a non-empty list")
    nodes = tuple(_parse_node(item, index=index) for index, item in enumerate(nodes_raw))
    names = {node.id for node in nodes}
    if len(names) != len(nodes):
        raise GraphConfigError("duplicate node id")
    _validate_node_similarity_targets(nodes, field=f"{field}.nodes")
    _validate_loop_targets(nodes, known_nodesets, field=f"{field}.nodes")
    _validate_nodeset_call_targets(nodes, known_nodesets, field=f"{field}.nodes")
    edges = tuple(_parse_edge(item, index=index) for index, item in enumerate(raw.get("edges", [])))
    try:
        inputs = parse_pipeline_inputs(raw.get("inputs", ()), field=f"{field}.inputs")
        outputs = parse_pipeline_outputs(raw.get("outputs", ()), field=f"{field}.outputs")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    max_steps = _parse_max_steps(raw.get("max_steps", 1000))
    entry_mode = _parse_entry_mode(
        raw.get("entry_mode", ENTRY_MODE_SYNC),
        field=f"{field}.entry_mode",
    )
    execution_lock = _parse_execution_lock(
        raw.get("execution_lock"),
        field=f"{field}.execution_lock",
    )

    for edge in edges:
        if edge.source not in names or edge.target not in names:
            raise GraphConfigError(f"edge references unknown node: {edge.source}->{edge.target}")
    return GraphConfig(
        nodes=nodes,
        edges=edges,
        nodesets=nodesets,
        inputs=inputs,
        outputs=outputs,
        max_steps=max_steps,
        entry_mode=entry_mode,
        project_root=project_root,
        root_id=root_id,
        root_path=root_path,
        source_path=source_path,
        execution_lock=execution_lock,
    )


def _parse_node(item: Any, *, index: int) -> NodeSpec:
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.nodes[{index}] must be an object")
    if "name" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].name is removed; use id")
    if "type" in item or "registry_key" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].type is removed; use type_used")
    node_id = str(item.get("id", "")).strip()
    status = _parse_status(item.get("status", STATUS_IMPLEMENTED), field=f"pipeline.nodes[{index}].status")
    type_used = str(item.get("type_used", "")).strip()
    if not node_id:
        raise GraphConfigError(f"pipeline.nodes[{index}] requires id")
    if status == STATUS_IMPLEMENTED and "planned_behavior" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].planned_behavior is only allowed for planned nodes")
    if not type_used:
        if status != STATUS_PLANNED:
            raise GraphConfigError(f"pipeline.nodes[{index}] requires type_used")
        type_used = f"planned.{node_id}"
    if type_used.startswith("nodeset."):
        raise GraphConfigError(f"pipeline.nodes[{index}].type_used must use the nodeset type_key directly, not nodeset.<name>")
    flow_kind = str(item.get("flow_kind", "")).strip()
    try:
        planned_behavior = parse_planned_behavior(item.get("planned_behavior", None), field=f"pipeline.nodes[{index}].planned_behavior")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    if status == STATUS_PLANNED and not flow_kind:
        raise GraphConfigError(f"pipeline.nodes[{index}].flow_kind is required for planned nodes")
    if flow_kind and flow_kind not in FLOW_KINDS:
        raise GraphConfigError(f"pipeline.nodes[{index}].flow_kind must be one of {sorted(FLOW_KINDS)}")
    if status == STATUS_IMPLEMENTED and flow_kind:
        raise GraphConfigError(f"pipeline.nodes[{index}].flow_kind is only allowed for planned nodes")
    explicit_contract = status == STATUS_PLANNED or type_used in LOOP_NODE_TYPES or type_used == IO_NODE_TYPE
    if explicit_contract:
        for field_name in ("requires", "provides"):
            if field_name not in item:
                raise GraphConfigError(
                    f"pipeline.nodes[{index}].{field_name} is required for planned or system nodes"
                )
    else:
        for field_name in ("requires", "provides"):
            if field_name in item:
                raise GraphConfigError(
                    f"pipeline.nodes[{index}].{field_name} is derived from type_used and must not be declared"
                )
    try:
        requires = parse_data_requirements(item.get("requires", ()), field=f"node[{node_id}].requires")
        provides = parse_data_providers(item.get("provides", ()), field=f"node[{node_id}].provides")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    async_mode, result_key = _parse_node_async(item, index=index, provides=provides)
    join_policy = _parse_join_policy(item.get("join_policy", JOIN_POLICY_SAFE_ANY), field=f"pipeline.nodes[{index}].join_policy")
    from vibeflow.core.config.loop import _parse_loop_spec

    loop = _parse_loop_spec(item.get("loop", {}), type_used=type_used, provides=provides, field=f"pipeline.nodes[{index}].loop")
    io = _parse_io_spec(
        item.get("io", {}),
        type_used=type_used,
        requires=requires,
        provides=provides,
        async_mode=async_mode,
        field=f"pipeline.nodes[{index}].io",
    )
    execution_lock = _parse_execution_lock(
        item.get("execution_lock"),
        field=f"pipeline.nodes[{index}].execution_lock",
    )
    reserved = {"id", "type_used", "requires", "provides", "config", "node_configs", "allow_config_override", "override_child_config", "status", "flow_kind", "planned_behavior", "async", "result_key", "execution_lock", "display_name", "description", "style", "similar_to", "join_policy", "loop", "io"}
    return NodeSpec(
        id=node_id,
        type_used=type_used,
        requires=requires,
        provides=provides,
        params=_parse_node_params(item, reserved=reserved, field=f"node[{node_id}].config"),
        metadata=_parse_node_metadata(item),
        style=_parse_node_style(item.get("style", {}), field=f"pipeline.nodes[{index}].style"),
        similar_to=_parse_node_similarity(item.get("similar_to", {}), field=f"pipeline.nodes[{index}].similar_to"),
        join_policy=join_policy,
        loop=loop,
        io=io,
        node_config_overrides=_parse_node_config_overrides(item.get("node_configs", {}), field=f"node[{node_id}].node_configs"),
        allow_config_override=_parse_bool(item.get("allow_config_override", item.get("override_child_config", False)), field=f"node[{node_id}].allow_config_override"),
        status=status,
        flow_kind=flow_kind,
        planned_behavior=planned_behavior,
        async_mode=async_mode,
        result_key=result_key,
        execution_lock=execution_lock,
    )


def _parse_io_spec(
    value: Any,
    *,
    type_used: str,
    requires: tuple[DataRequirement, ...],
    provides: tuple[DataProvider, ...],
    async_mode: str,
    field: str,
) -> IoSpec:
    if type_used != IO_NODE_TYPE:
        if value not in (None, {}):
            raise GraphConfigError(
                f"{field} is only allowed on {IO_NODE_TYPE}"
            )
        return IoSpec()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    unknown = sorted(
        set(str(key) for key in value) - {"operation", "port"}
    )
    if unknown:
        raise GraphConfigError(
            f"{field} contains unsupported keys: {unknown}"
        )
    operation = str(value.get("operation", "")).strip()
    if operation not in IO_OPERATIONS:
        raise GraphConfigError(
            f"{field}.operation must be receive or send"
        )
    port = str(value.get("port", "default")).strip()
    if not port:
        raise GraphConfigError(
            f"{field}.port must be a non-empty string"
        )
    if async_mode:
        raise GraphConfigError(
            f"{IO_NODE_TYPE} uses its operation completion and cannot "
            "also declare legacy node.async"
        )
    if operation == "receive":
        if requires or len(provides) != 1:
            raise GraphConfigError(
                f"{field} receive requires zero inputs and exactly one output"
            )
    elif (
        len(requires) != 1
        or requires[0].cardinality != "exactly_one"
        or provides
    ):
        raise GraphConfigError(
            f"{field} send requires one exactly_one input and zero outputs"
        )
    return IoSpec(operation=operation, port=port)


def _parse_nodesets(value: Any, *, project_root: str = "", root_id: str = "", root_path: str = "") -> dict[str, NodesetSpec]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise GraphConfigError("nodesets must be a list")
    raw_nodesets: list[tuple[int, str, Mapping[str, Any], str, PlannedBehavior, str]] = []
    type_keys: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise GraphConfigError(f"nodesets[{index}] must be an object")
        for removed in ("name", "category", "version", "purity", "exports"):
            if removed in item:
                raise GraphConfigError(f"nodesets[{index}].{removed} is removed from nodeset definitions")
        type_key = str(item.get("type_key", "")).strip()
        if not type_key:
            raise GraphConfigError(f"nodesets[{index}] missing type_key")
        for field_name in ("display_name", "description"):
            raw_text = item.get(field_name)
            if not isinstance(raw_text, str) or not raw_text.strip():
                raise GraphConfigError(
                    f"nodesets[{index}].{field_name} must be a non-empty string"
                )
        for field_name in ("requires", "provides"):
            if field_name not in item:
                raise GraphConfigError(
                    f"nodesets[{index}].{field_name} is required"
                )
        if type_key in type_keys:
            raise GraphConfigError(f"duplicate nodeset type_key: {type_key}")
        type_keys.add(type_key)
        status = _parse_status(item.get("status", STATUS_IMPLEMENTED), field=f"nodesets[{index}].status")
        if status == STATUS_IMPLEMENTED and "planned_behavior" in item:
            raise GraphConfigError(f"nodesets[{index}].planned_behavior is only allowed for planned nodes")
        try:
            planned_behavior = parse_planned_behavior(item.get("planned_behavior", None), field=f"nodesets[{index}].planned_behavior")
        except ValueError as exc:
            raise GraphConfigError(str(exc)) from exc
        flow_kind = str(item.get("flow_kind", FLOW_KIND_PREDEFINED)).strip() or FLOW_KIND_PREDEFINED
        if flow_kind not in FLOW_KINDS:
            raise GraphConfigError(f"nodesets[{index}].flow_kind must be one of {sorted(FLOW_KINDS)}")
        raw_nodesets.append((index, type_key, item, status, planned_behavior, flow_kind))

    out: dict[str, NodesetSpec] = {}
    for nodeset_index, type_key, item, status, planned_behavior, flow_kind in raw_nodesets:
        pipeline = item.get("pipeline")
        nodeset_root_id = str(item.get("__vibeflow_root_id__", root_id)).strip()
        nodeset_root_path = str(item.get("__vibeflow_root_path__", root_path)).strip()
        nodeset_source_path = str(item.get("__vibeflow_source_path__", "")).strip()
        nodeset_project_root = nodeset_root_path or project_root
        if pipeline is None and status == STATUS_PLANNED:
            graph = GraphConfig(
                nodes=(),
                nodesets=out,
                project_root=nodeset_project_root,
                root_id=nodeset_root_id,
                root_path=nodeset_root_path,
                source_path=nodeset_source_path,
            )
        elif not isinstance(pipeline, Mapping):
            raise GraphConfigError(f"nodeset '{type_key}' requires pipeline")
        else:
            graph = _parse_graph_body(
                pipeline,
                nodesets=out,
                known_nodesets=type_keys,
                project_root=nodeset_project_root,
                field=f"nodesets[{nodeset_index}].pipeline",
                root_id=nodeset_root_id,
                root_path=nodeset_root_path,
                source_path=nodeset_source_path,
            )
        out[type_key] = NodesetSpec(
            type_key=type_key,
            display_name=str(item["display_name"]).strip(),
            description=str(item["description"]).strip(),
            requires=_parse_nodeset_requirements(item.get("requires", ()), field=f"nodeset[{type_key}].requires"),
            provides=_parse_nodeset_providers(item.get("provides", ()), field=f"nodeset[{type_key}].provides"),
            graph=graph,
            global_config=_parse_mapping(item.get("global_config", {}), field=f"nodeset[{type_key}].global_config"),
            status=status,
            flow_kind=flow_kind,
            planned_behavior=planned_behavior,
            root_id=nodeset_root_id,
            root_path=nodeset_root_path,
            source_path=nodeset_source_path,
        )
    return out


def _parse_nodeset_requirements(value: Any, *, field: str) -> tuple[DataRequirement, ...]:
    try:
        return parse_data_requirements(value, field=field)
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc


def _parse_nodeset_providers(value: Any, *, field: str) -> tuple[DataProvider, ...]:
    try:
        return parse_data_providers(value, field=field)
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc


def _parse_max_steps(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GraphConfigError("pipeline.max_steps must be an integer >= 1")
    return value


def _parse_entry_mode(value: Any, *, field: str) -> str:
    mode = str(value or ENTRY_MODE_SYNC).strip()
    if mode not in ENTRY_MODES:
        raise GraphConfigError(
            f"{field} must be one of {sorted(ENTRY_MODES)}"
        )
    return mode


def _parse_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise GraphConfigError(f"{field} must be a boolean")


def _parse_execution_lock(value: Any, *, field: str) -> ExecutionLockSpec | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    unknown = sorted(set(str(key) for key in value) - {"key"})
    if unknown:
        raise GraphConfigError(f"{field} contains unsupported keys: {unknown}")
    key = value.get("key")
    if not isinstance(key, str) or not key.strip():
        raise GraphConfigError(f"{field}.key must be a non-empty string")
    normalized = key.strip()
    if normalized.startswith("vibeflow."):
        raise GraphConfigError(
            f"{field}.key uses reserved prefix 'vibeflow.'"
        )
    return ExecutionLockSpec(normalized)


def _parse_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    return {str(key): item for key, item in value.items()}


def _parse_status(value: Any, *, field: str) -> str:
    status = str(value).strip()
    if status not in STATUSES:
        raise GraphConfigError(f"{field} must be 'planned' or 'implemented'")
    return status


def _parse_node_async(item: Mapping[str, Any], *, index: int, provides: tuple[DataProvider, ...]) -> tuple[str, str]:
    async_mode = _parse_async_mode(item.get("async", ""), field=f"pipeline.nodes[{index}].async")
    result_key = str(item.get("result_key", "")).strip()
    if async_mode == "result_key" and not result_key:
        raise GraphConfigError(f"pipeline.nodes[{index}].result_key is required for async result_key")
    if async_mode != "result_key" and result_key:
        raise GraphConfigError(f"pipeline.nodes[{index}].result_key requires async='result_key'")
    return async_mode, result_key


def _parse_join_policy(value: Any, *, field: str) -> str:
    policy = str(value or JOIN_POLICY_SAFE_ANY).strip()
    if policy not in JOIN_POLICIES:
        raise GraphConfigError(f"{field} must be one of {sorted(JOIN_POLICIES)}")
    return policy


def _parse_async_mode(value: Any, *, field: str) -> str:
    mode = str(value).strip()
    if mode in {"", "detached", "result_key"}:
        return mode
    raise GraphConfigError(f"{field} must be 'detached' or 'result_key'")


def _parse_node_params(item: Mapping[str, Any], *, reserved: set[str], field: str) -> dict[str, Any]:
    raw_config = item.get("config", {})
    if raw_config in (None, {}):
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    inline = {str(k): v for k, v in item.items() if k not in reserved}
    return {**{str(k): v for k, v in raw_config.items()}, **inline}


def _parse_node_metadata(item: Mapping[str, Any]) -> NodeMetadata:
    for removed in ("category", "version", "purity"):
        if removed in item:
            raise GraphConfigError(f"node metadata field {removed!r} is removed; use display_name and description")
    display_name = _optional_string(item.get("display_name", ""))
    description = _optional_string(item.get("description", ""))
    if not display_name:
        raise GraphConfigError(
            "node display_name must be a non-empty string describing this call instance"
        )
    if not description:
        raise GraphConfigError(
            "node description must be a non-empty string describing this call instance"
        )
    return NodeMetadata(display_name=display_name, description=description)


def _optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_node_style(value: Any, *, field: str) -> NodeStyle:
    if value in (None, {}):
        return NodeStyle()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    unknown = sorted(set(str(key) for key in value) - set(NODE_STYLE_FIELDS))
    if unknown:
        raise GraphConfigError(f"{field} contains unknown keys: {unknown}")
    parsed: dict[str, str] = {}
    for key in NODE_STYLE_FIELDS:
        if key not in value:
            continue
        color = value[key]
        if not is_hex_color(color):
            raise GraphConfigError(f"{field}.{key} must be a #RRGGBB color")
        normalized = normalize_hex_color(str(color))
        if is_reserved_system_color(normalized):
            raise GraphConfigError(f"{field}.{key} uses reserved VibeFlow system color: {normalized}")
        parsed[key] = normalized
    return NodeStyle(fill=parsed.get("fill", ""), stroke=parsed.get("stroke", ""), text=parsed.get("text", ""))


def _parse_node_similarity(value: Any, *, field: str) -> NodeSimilarity:
    if value in (None, {}):
        return NodeSimilarity()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field} must be an object")
    unknown = sorted(set(str(key) for key in value) - {"node", "relationship", "reason"})
    if unknown:
        raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field} contains unknown keys: {unknown}")
    node = str(value.get("node", "")).strip()
    relationship = str(value.get("relationship", "")).strip()
    reason = str(value.get("reason", "")).strip()
    if not node:
        raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}.node must be a non-empty string")
    if relationship not in SIMILAR_TO_RELATIONSHIPS:
        raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}.relationship must be variant or copy")
    if not reason:
        raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}.reason must be a non-empty string")
    return NodeSimilarity(node=node, relationship=relationship, reason=reason)


def _validate_node_similarity_targets(nodes: tuple[NodeSpec, ...], *, field: str) -> None:
    names = {node.id for node in nodes}
    for index, node in enumerate(nodes):
        target = node.similar_to.node
        if not target:
            continue
        if target == node.id:
            raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}[{index}].similar_to.node cannot reference itself")
        if target not in names:
            raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}[{index}].similar_to.node references unknown node: {target}")


def _validate_loop_targets(nodes: tuple[NodeSpec, ...], nodesets: set[str], *, field: str) -> None:
    for index, node in enumerate(nodes):
        if node.type_used not in LOOP_NODE_TYPES:
            continue
        if not node.loop.body:
            raise GraphConfigError(f"{field}[{index}].loop.body must be a non-empty nodeset name")
        if node.loop.body not in nodesets:
            raise GraphConfigError(
                f"{field}[{index}] loop node '{node.id}' references unknown nodeset loop body: {node.loop.body}"
            )


def _validate_nodeset_call_targets(nodes: tuple[NodeSpec, ...], nodesets: set[str], *, field: str) -> None:
    for index, node in enumerate(nodes):
        if node.status == STATUS_PLANNED or node.type_used not in nodesets:
            continue


def _parse_node_config_overrides(value: Any, *, field: str) -> dict[str, dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    out: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        text_key = str(key).strip()
        if not text_key:
            raise GraphConfigError(f"{field} keys must be non-empty strings")
        if not isinstance(item, Mapping):
            raise GraphConfigError(f"{field}.{text_key} must be an object")
        out[text_key] = {str(k): v for k, v in item.items()}
    return out


def _nodeset_reference_targets(nodes: tuple[NodeSpec, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for node in nodes:
        if node.type_used in LOOP_NODE_TYPES and node.loop.body:
            refs.append(node.loop.body)
    return tuple(sorted(set(refs)))


__all__ = ["parse_graph_config_data"]
