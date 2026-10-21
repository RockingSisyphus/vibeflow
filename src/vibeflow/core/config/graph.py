from __future__ import annotations
from dataclasses import replace

from typing import Any, Mapping

from vibeflow.core.contracts import (
    DataProvider,
    DataRequirement,
    parse_data_providers,
    parse_data_requirements,
    parse_pipeline_inputs,
    parse_pipeline_outputs,
)
from vibeflow.core.flow import (
    ExecutionLockSpec,
    GraphConfig,
    GraphConfigError,
    JOIN_POLICIES,
    JOIN_POLICY_SAFE_ANY,
    ENTRY_MODES,
    ENTRY_MODE_SYNC,
    LOOP_DEFINITION_IDS,
    NodeMetadata,
    NodeSimilarity,
    NodeCallSpec,
    NodeStyle,
    NodesetTypeSpec,
    SIMILAR_TO_RELATIONSHIPS,
    STATUSES,
    STATUS_IMPLEMENTED,
    STATUS_PLANNED,
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
    nodeset_types = _parse_nodeset_types(
        config.get("nodeset_types", raw.get("nodeset_types", [])),
        project_root=root_text,
        root_id=root_id,
        root_path=actual_root_path,
    )
    graph = _parse_graph_body(
        raw,
        nodeset_types=nodeset_types,
        known_nodeset_types=set(nodeset_types),
        project_root=root_text,
        field="pipeline",
        root_id=root_id,
        root_path=actual_root_path,
        source_path=actual_source_path,
    )
    from vibeflow.core.workflows.targets import parse_targets
    try:
        targets = parse_targets(config.get("workflow_targets", {}))
    except ValueError as error:
        raise GraphConfigError(str(error), "CONFIG.WORKFLOW_TARGET.INVALID") from error
    return replace(graph, rulesets=_parse_rulesets(config.get("rulesets"), explicit="rulesets" in config), workflow_targets=targets)


def _parse_graph_body(
    raw: Mapping[str, Any],
    *,
    nodeset_types: dict[str, NodesetTypeSpec],
    known_nodeset_types: set[str],
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
    _validate_loop_targets(nodes, known_nodeset_types, field=f"{field}.nodes")
    _validate_nodeset_call_targets(nodes, known_nodeset_types, field=f"{field}.nodes")
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
    from vibeflow.core.workflows.entries import parse_entries
    try:
        entries = parse_entries(raw.get("entries", {}), node_ids=names,
            default=raw.get("default_entry", ""), field=field + ".entries")
    except ValueError as error:
        raise GraphConfigError(str(error), "CONFIG.ENTRY.INVALID") from error
    return GraphConfig(
        nodes=nodes,
        edges=edges,
        nodeset_types=nodeset_types,
        inputs=inputs,
        outputs=outputs,
        max_steps=max_steps,
        entry_mode=entry_mode,
        entries=entries, default_entry=raw.get("default_entry", ""),
        project_root=project_root,
        root_id=root_id,
        root_path=root_path,
        source_path=source_path,
        execution_lock=execution_lock,
        rulesets=_parse_rulesets(raw.get("rulesets"), explicit="rulesets" in raw),
    )


def _parse_node(item: Any, *, index: int) -> NodeCallSpec:
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.nodes[{index}] must be an object")
    if "name" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].name is removed; use id")
    if "type" in item or "registry_key" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].type is removed; use definition_id")
    if "expand" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].expand belongs on the Nodeset definition")
    node_id = str(item.get("id", "")).strip()
    status = _parse_status(item.get("status", STATUS_IMPLEMENTED), field=f"pipeline.nodes[{index}].status")
    definition_id = str(item.get("definition_id", "")).strip()
    if not node_id:
        raise GraphConfigError(f"pipeline.nodes[{index}] requires id")
    if status == STATUS_IMPLEMENTED and "planned_behavior" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].planned_behavior is only allowed for planned nodes")
    if not definition_id:
        if status != STATUS_PLANNED:
            raise GraphConfigError(f"pipeline.nodes[{index}] requires definition_id")
        definition_id = f"planned.{node_id}"
    if definition_id.startswith("nodeset."):
        raise GraphConfigError(f"pipeline.nodes[{index}].definition_id must use the nodeset type_key directly, not nodeset.<name>")
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
    if "io" in item or definition_id == "vibeflow.io":
        raise GraphConfigError("replace native io with ordinary SDK nodes, explicit contracts and vibeflow.port Capability; add terminal boundaries", "GRAPH.IO.MIGRATION")
    explicit_contract = status == STATUS_PLANNED or definition_id in LOOP_DEFINITION_IDS
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
                    f"pipeline.nodes[{index}].{field_name} is derived from definition_id and must not be declared"
                )
    try:
        requires = parse_data_requirements(item.get("requires", ()), field=f"node[{node_id}].requires")
        provides = parse_data_providers(item.get("provides", ()), field=f"node[{node_id}].provides")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    _reject_removed_async_fields(item)
    join_policy = _parse_join_policy(item.get("join_policy", JOIN_POLICY_SAFE_ANY), field=f"pipeline.nodes[{index}].join_policy")
    from vibeflow.core.config.loop import _parse_loop_spec

    loop = _parse_loop_spec(item.get("loop", {}), definition_id=definition_id, provides=provides, field=f"pipeline.nodes[{index}].loop")
    execution_lock = _parse_execution_lock(
        item.get("execution_lock"),
        field=f"pipeline.nodes[{index}].execution_lock",
    )
    if "task_targets" in item:
        raise GraphConfigError("GRAPH.TASK.MIGRATION: declare ordinary pipeline nodes and edges with an explicit downstream join", "GRAPH.TASK.MIGRATION")
    reserved = {"task_targets", "rulesets", "id", "definition_id", "requires", "provides", "config", "node_configs", "allow_config_override", "override_child_config", "status", "flow_kind", "planned_behavior", "async", "result_key", "execution_lock", "display_name", "description", "style", "similar_to", "join_policy", "loop", "io"}
    return NodeCallSpec(
        id=node_id,
        rulesets=_parse_rulesets(item.get("rulesets"), explicit="rulesets" in item),
        definition_id=definition_id,
        requires=requires,
        provides=provides,
        params=_parse_node_params(item, reserved=reserved, field=f"node[{node_id}].config"),
        metadata=_parse_node_metadata(item),
        style=_parse_node_style(item.get("style", {}), field=f"pipeline.nodes[{index}].style"),
        similar_to=_parse_node_similarity(item.get("similar_to", {}), field=f"pipeline.nodes[{index}].similar_to"),
        join_policy=join_policy,
        loop=loop,
        node_config_overrides=_parse_node_config_overrides(item.get("node_configs", {}), field=f"node[{node_id}].node_configs"),
        allow_config_override=_parse_bool(item.get("allow_config_override", item.get("override_child_config", False)), field=f"node[{node_id}].allow_config_override"),
        status=status,
        flow_kind=flow_kind,
        planned_behavior=planned_behavior,
        execution_lock=execution_lock,
    )




def _parse_nodeset_types(value: Any, *, project_root: str = "", root_id: str = "", root_path: str = "") -> dict[str, NodesetTypeSpec]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise GraphConfigError("nodeset_types must be a list")
    raw_nodesets: list[tuple[int, str, Mapping[str, Any], str, PlannedBehavior, str, bool]] = []
    type_keys: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise GraphConfigError(f"nodeset_types[{index}] must be an object")
        for removed in ("name", "category", "version", "purity", "exports"):
            if removed in item:
                raise GraphConfigError(f"nodeset_types[{index}].{removed} is removed from nodeset definitions")
        type_key = str(item.get("type_key", "")).strip()
        if not type_key:
            raise GraphConfigError(f"nodeset_types[{index}] missing type_key")
        for field_name in ("display_name", "description"):
            raw_text = item.get(field_name)
            if not isinstance(raw_text, str) or not raw_text.strip():
                raise GraphConfigError(
                    f"nodeset_types[{index}].{field_name} must be a non-empty string"
                )
        for field_name in ("requires", "provides"):
            if field_name not in item:
                raise GraphConfigError(
                    f"nodeset_types[{index}].{field_name} is required"
                )
        if type_key in type_keys:
            raise GraphConfigError(f"duplicate nodeset type_key: {type_key}")
        type_keys.add(type_key)
        status = _parse_status(item.get("status", STATUS_IMPLEMENTED), field=f"nodeset_types[{index}].status")
        if status == STATUS_IMPLEMENTED and "planned_behavior" in item:
            raise GraphConfigError(f"nodeset_types[{index}].planned_behavior is only allowed for planned nodes")
        try:
            planned_behavior = parse_planned_behavior(item.get("planned_behavior", None), field=f"nodeset_types[{index}].planned_behavior")
        except ValueError as exc:
            raise GraphConfigError(str(exc)) from exc
        flow_kind = str(item.get("flow_kind", FLOW_KIND_PREDEFINED)).strip() or FLOW_KIND_PREDEFINED
        if flow_kind not in FLOW_KINDS:
            raise GraphConfigError(f"nodeset_types[{index}].flow_kind must be one of {sorted(FLOW_KINDS)}")
        expand = _parse_bool(item.get("expand", True), field=f"nodeset_types[{index}].expand")
        raw_nodesets.append((index, type_key, item, status, planned_behavior, flow_kind, expand))

    out: dict[str, NodesetTypeSpec] = {}
    for nodeset_index, type_key, item, status, planned_behavior, flow_kind, expand in raw_nodesets:
        pipeline = item.get("pipeline")
        nodeset_root_id = str(item.get("__vibeflow_root_id__", root_id)).strip()
        nodeset_root_path = str(item.get("__vibeflow_root_path__", root_path)).strip()
        nodeset_source_path = str(item.get("__vibeflow_source_path__", "")).strip()
        nodeset_project_root = nodeset_root_path or project_root
        if pipeline is None and status == STATUS_PLANNED:
            graph = GraphConfig(
                nodes=(),
                nodeset_types=out,
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
                nodeset_types=out,
                known_nodeset_types=type_keys,
                project_root=nodeset_project_root,
                field=f"nodeset_types[{nodeset_index}].pipeline",
                root_id=nodeset_root_id,
                root_path=nodeset_root_path,
                source_path=nodeset_source_path,
            )
        graph = replace(graph, rulesets=_parse_rulesets(item.get("rulesets"), explicit="rulesets" in item))
        out[type_key] = NodesetTypeSpec(
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
            expand=expand,
        )
    return out


def _parse_rulesets(value, *, explicit=False):
    if value is None and explicit:
        raise GraphConfigError("rulesets must be a list, not null")
    from vibeflow.core.rules.selection.models import selection_refs
    try:
        return selection_refs(value, optional=True)
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc


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


def _reject_removed_async_fields(item: Mapping[str, Any]) -> None:
    if "async" in item or "result_key" in item:
        raise GraphConfigError("GRAPH.ASYNC.MIGRATION: use ordinary nodes, explicit edges and join_policy=all; async/result_key/detached calls have been removed", "GRAPH.ASYNC.MIGRATION")


def _parse_join_policy(value: Any, *, field: str) -> str:
    policy = str(value or JOIN_POLICY_SAFE_ANY).strip()
    if policy not in JOIN_POLICIES:
        raise GraphConfigError(f"{field} must be one of {sorted(JOIN_POLICIES)}")
    return policy


def _parse_node_params(item: Mapping[str, Any], *, reserved: set[str], field: str) -> dict[str, Any]:
    from vibeflow.core.config.node import NodeConfigError, node_config_from_call_params

    try:
        from vibeflow.core.config.concurrency import dispatch_limit
        params = node_config_from_call_params(item, reserved=reserved)
        dispatch_limit(params)
        return params
    except NodeConfigError as error:
        raise GraphConfigError(f"{field}: {error}") from error


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
    from vibeflow.core.style import NODE_PRESENTATION_FIELDS, NODE_SHAPES
    if value in (None, {}):
        return NodeStyle()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    unknown = sorted(set(str(key) for key in value) - set(NODE_PRESENTATION_FIELDS))
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
    for key in ("shape", "icon"):
        if key not in value:
            continue
        item = value[key]
        if not isinstance(item, str) or not item.strip():
            raise GraphConfigError(f"{field}.{key} must be a non-empty string")
        if key == "shape" and item not in NODE_SHAPES:
            raise GraphConfigError(f"{field}.shape must be one of {sorted(NODE_SHAPES)}")
        parsed[key] = item
    return NodeStyle(**parsed)


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


def _validate_node_similarity_targets(nodes: tuple[NodeCallSpec, ...], *, field: str) -> None:
    names = {node.id for node in nodes}
    for index, node in enumerate(nodes):
        target = node.similar_to.node
        if not target:
            continue
        if target == node.id:
            raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}[{index}].similar_to.node cannot reference itself")
        if target not in names:
            raise GraphConfigError(f"CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID: {field}[{index}].similar_to.node references unknown node: {target}")


def _validate_loop_targets(nodes: tuple[NodeCallSpec, ...], nodeset_types: set[str], *, field: str) -> None:
    for index, node in enumerate(nodes):
        if node.definition_id not in LOOP_DEFINITION_IDS:
            continue
        if not node.loop.body:
            raise GraphConfigError(f"{field}[{index}].loop.body must be a non-empty nodeset name")
        if node.loop.body not in nodeset_types:
            raise GraphConfigError(
                f"{field}[{index}] loop node '{node.id}' references unknown nodeset loop body: {node.loop.body}"
            )


def _validate_nodeset_call_targets(nodes: tuple[NodeCallSpec, ...], nodeset_types: set[str], *, field: str) -> None:
    for index, node in enumerate(nodes):
        if node.status == STATUS_PLANNED or node.definition_id not in nodeset_types:
            continue


def _parse_node_config_overrides(value: Any, *, field: str) -> dict[str, dict[str, Any]]:
    from vibeflow.core.config.scope import normalize_node_config_overrides, ConfigBindingError
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
    try:
        return normalize_node_config_overrides(out)
    except ConfigBindingError as error:
        raise GraphConfigError(f"{field}: {error}") from error


def _nodeset_reference_targets(nodes: tuple[NodeCallSpec, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for node in nodes:
        if node.definition_id in LOOP_DEFINITION_IDS and node.loop.body:
            refs.append(node.loop.body)
    return tuple(sorted(set(refs)))


__all__ = ["parse_graph_config_data"]
