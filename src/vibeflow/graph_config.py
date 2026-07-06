from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

from .data_contract import (
    DataProvider,
    DataRequirement,
    parse_data_providers,
    parse_data_requirements,
    provider_keys,
)
from .node import FLOW_KINDS, FLOW_KIND_PREDEFINED
from .planned_behavior import PlannedBehavior, blocking_planned_behavior, parse_planned_behavior
from .visual_style import NODE_STYLE_FIELDS, is_hex_color, is_reserved_system_color, normalize_hex_color

STATUS_PLANNED = "planned"
STATUS_IMPLEMENTED = "implemented"
STATUSES = frozenset({STATUS_PLANNED, STATUS_IMPLEMENTED})
SIMILAR_TO_RELATIONSHIPS = frozenset({"variant", "copy"})
JOIN_POLICY_SAFE_ANY = "safe_any"
JOIN_POLICY_ANY_ACTIVE = "any_active"
JOIN_POLICY_ALL = "all"
JOIN_POLICIES = frozenset({JOIN_POLICY_SAFE_ANY, JOIN_POLICY_ANY_ACTIVE, JOIN_POLICY_ALL})
LOOP_WHILE_TYPE = "vibeflow.loop.while"
LOOP_NODE_TYPES = frozenset({LOOP_WHILE_TYPE})


@dataclass(frozen=True)
class NodeMetadata:
    display_name: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "display_name": self.display_name,
            "description": self.description,
        }


@dataclass(frozen=True)
class NodeStyle:
    fill: str = ""
    stroke: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in (("fill", self.fill), ("stroke", self.stroke), ("text", self.text)) if value}


@dataclass(frozen=True)
class NodeSimilarity:
    node: str = ""
    relationship: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        if not self.node:
            return {}
        return {
            "node": self.node,
            "relationship": self.relationship,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LoopCarrySpec:
    source: str
    target: str
    update: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "update": self.update}


@dataclass(frozen=True)
class LoopCollectSpec:
    source: str
    target: str
    mode: str = "all"

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target, "mode": self.mode}


@dataclass(frozen=True)
class LoopOutputSpec:
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.source, "as": self.target}


@dataclass(frozen=True)
class LoopStopWhenSpec:
    source: str = ""
    equals: bool = True

    def to_dict(self) -> dict[str, Any]:
        if not self.source:
            return {}
        return {"from": self.source, "equals": self.equals}


@dataclass(frozen=True)
class LoopSpec:
    body: str = ""
    max_iterations: int = 1000
    stop_after: int = 0
    stop_when: LoopStopWhenSpec = field(default_factory=LoopStopWhenSpec)
    carry: tuple[LoopCarrySpec, ...] = ()
    collect: tuple[LoopCollectSpec, ...] = ()
    outputs: tuple[LoopOutputSpec, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        if not self.body:
            return {}
        payload: dict[str, Any] = {
            "body": self.body,
            "max_iterations": self.max_iterations,
        }
        if self.stop_after:
            payload["stop_after"] = self.stop_after
        if self.stop_when.source:
            payload["stop_when"] = self.stop_when.to_dict()
        if self.carry:
            payload["carry"] = [item.to_dict() for item in self.carry]
        if self.collect:
            payload["collect"] = [item.to_dict() for item in self.collect]
        if self.outputs:
            payload["outputs"] = [item.to_dict() for item in self.outputs]
        return payload


@dataclass(frozen=True)
class NodeSpec:
    id: str
    type_used: str
    requires: tuple[DataRequirement, ...] = ()
    provides: tuple[DataProvider, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    metadata: NodeMetadata = field(default_factory=NodeMetadata)
    style: NodeStyle = field(default_factory=NodeStyle)
    similar_to: NodeSimilarity = field(default_factory=NodeSimilarity)
    join_policy: str = JOIN_POLICY_SAFE_ANY
    loop: LoopSpec = field(default_factory=LoopSpec)
    node_config_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    allow_config_override: bool = False
    status: str = STATUS_IMPLEMENTED
    flow_kind: str = ""
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)
    async_mode: str = ""
    result_key: str = ""

    @property
    def name(self) -> str:
        return self.id

    @property
    def node_type(self) -> str:
        return self.type_used


@dataclass(frozen=True)
class EdgeSpec:
    source: str
    target: str
    when: str = ""

    @property
    def pair(self) -> tuple[str, str]:
        return (self.source, self.target)


@dataclass(frozen=True)
class NodesetSpec:
    type_key: str
    display_name: str
    description: str
    requires: tuple[DataRequirement, ...]
    provides: tuple[DataProvider, ...]
    graph: "GraphConfig"
    global_config: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_IMPLEMENTED
    flow_kind: str = FLOW_KIND_PREDEFINED
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)

    @property
    def name(self) -> str:
        return self.type_key

    @property
    def exports(self) -> tuple[DataProvider, ...]:
        return self.provides


@dataclass(frozen=True)
class GraphConfig:
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...] = ()
    nodesets: dict[str, NodesetSpec] = field(default_factory=dict)
    inputs: tuple[DataProvider, ...] = ()
    outputs: tuple[DataRequirement, ...] = ()
    max_steps: int = 1000
    project_root: str = ""


@dataclass
class GraphConfigError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Graph config error: {self.detail}"


def parse_graph_config(config: Mapping[str, Any], *, project_root: str | Path | None = None) -> GraphConfig:
    started = time.perf_counter()
    raw = config.get("pipeline", config)
    root_text = str(Path(project_root).resolve()) if project_root is not None else ""
    if not isinstance(raw, Mapping):
        raise GraphConfigError("pipeline config must be an object")
    if "boundary" in config:
        raise GraphConfigError("boundary is removed; use terminal/io/data_store/document nodes")
    nodesets = _parse_nodesets(config.get("nodesets", raw.get("nodesets", [])), project_root=root_text)
    graph = _parse_graph_body(raw, nodesets=nodesets, known_nodesets=set(nodesets), project_root=root_text, field="pipeline")
    _trace_config_parse(f"parsed graph nodes={len(graph.nodes)} nodesets={len(nodesets)} elapsed={_elapsed_ms(started)}ms")
    return graph


def _parse_graph_body(
    raw: Mapping[str, Any],
    *,
    nodesets: dict[str, NodesetSpec],
    known_nodesets: set[str],
    project_root: str,
    field: str,
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
        inputs = parse_data_providers(raw.get("inputs", ()), field=f"{field}.inputs")
        outputs = parse_data_requirements(raw.get("outputs", ()), field=f"{field}.outputs")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    max_steps = _parse_max_steps(raw.get("max_steps", 1000))

    for edge in edges:
        if edge.source not in names or edge.target not in names:
            raise GraphConfigError(f"edge references unknown node: {edge.source}->{edge.target}")
    return GraphConfig(nodes=nodes, edges=edges, nodesets=nodesets, inputs=inputs, outputs=outputs, max_steps=max_steps, project_root=project_root)


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
    try:
        requires = parse_data_requirements(item.get("requires", ()), field=f"node[{node_id}].requires")
        provides = parse_data_providers(item.get("provides", ()), field=f"node[{node_id}].provides")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    async_mode, result_key = _parse_node_async(item, index=index, provides=provides)
    join_policy = _parse_join_policy(item.get("join_policy", JOIN_POLICY_SAFE_ANY), field=f"pipeline.nodes[{index}].join_policy")
    loop = _parse_loop_spec(item.get("loop", {}), type_used=type_used, provides=provides, field=f"pipeline.nodes[{index}].loop")
    reserved = {
        "id",
        "type_used",
        "requires",
        "provides",
        "config",
        "node_configs",
        "allow_config_override",
        "override_child_config",
        "status",
        "flow_kind",
        "planned_behavior",
        "async",
        "result_key",
        "display_name",
        "description",
        "style",
        "similar_to",
        "join_policy",
        "loop",
    }
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
        node_config_overrides=_parse_node_config_overrides(item.get("node_configs", {}), field=f"node[{node_id}].node_configs"),
        allow_config_override=_parse_bool(item.get("allow_config_override", item.get("override_child_config", False)), field=f"node[{node_id}].allow_config_override"),
        status=status,
        flow_kind=flow_kind,
        planned_behavior=planned_behavior,
        async_mode=async_mode,
        result_key=result_key,
    )


def _parse_edge(item: Any, *, index: int) -> EdgeSpec:
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return EdgeSpec(source=str(item[0]).strip(), target=str(item[1]).strip())
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.edges[{index}] must be [from, to] or object")
    source = str(item.get("from", item.get("source", ""))).strip()
    target = str(item.get("to", item.get("target", ""))).strip()
    if not source or not target:
        raise GraphConfigError(f"pipeline.edges[{index}] requires from/to")
    for field in ("max_executions", "max", "loop"):
        if field in item:
            raise GraphConfigError(f"pipeline.edges[{index}].{field} is removed; use when/max_steps")
    when = str(item.get("when", "")).strip()
    if when:
        _validate_when_expression(when, field=f"pipeline.edges[{index}].when")
    return EdgeSpec(source=source, target=target, when=when)


@dataclass(frozen=True)
class _RawNodeset:
    index: int
    type_key: str
    item: Mapping[str, Any]
    status: str
    planned_behavior: PlannedBehavior
    flow_kind: str


def _parse_nodesets(value: Any, *, project_root: str = "") -> dict[str, NodesetSpec]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise GraphConfigError("nodesets must be a list")
    raw_nodesets: list[_RawNodeset] = []
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
        raw_nodesets.append(_RawNodeset(index=index, type_key=type_key, item=item, status=status, planned_behavior=planned_behavior, flow_kind=flow_kind))

    out: dict[str, NodesetSpec] = {}
    started = time.perf_counter()
    for raw_nodeset in raw_nodesets:
        item = raw_nodeset.item
        pipeline = item.get("pipeline")
        nodeset_started = time.perf_counter()
        if pipeline is None and raw_nodeset.status == STATUS_PLANNED:
            graph = GraphConfig(nodes=(), nodesets=out, project_root=project_root)
        elif not isinstance(pipeline, Mapping):
            raise GraphConfigError(f"nodeset '{raw_nodeset.type_key}' requires pipeline")
        else:
            graph = _parse_graph_body(
                pipeline,
                nodesets=out,
                known_nodesets=type_keys,
                project_root=project_root,
                field=f"nodesets[{raw_nodeset.index}].pipeline",
            )
        out[raw_nodeset.type_key] = NodesetSpec(
            type_key=raw_nodeset.type_key,
            display_name=str(item.get("display_name", raw_nodeset.type_key)),
            description=str(item.get("description", "")),
            requires=_parse_nodeset_requirements(item.get("requires", ()), field=f"nodeset[{raw_nodeset.type_key}].requires"),
            provides=_parse_nodeset_providers(item.get("provides", ()), field=f"nodeset[{raw_nodeset.type_key}].provides"),
            graph=graph,
            global_config=_parse_mapping(item.get("global_config", {}), field=f"nodeset[{raw_nodeset.type_key}].global_config"),
            status=raw_nodeset.status,
            flow_kind=raw_nodeset.flow_kind,
            planned_behavior=raw_nodeset.planned_behavior,
        )
        _trace_config_parse(
            f"parsed nodeset type_key={raw_nodeset.type_key} index={raw_nodeset.index} "
            f"nodes={len(graph.nodes)} refs={','.join(_nodeset_reference_targets(graph.nodes)) or '-'} "
            f"elapsed={_elapsed_ms(nodeset_started)}ms"
        )
    _trace_config_parse(f"parsed nodeset registry count={len(out)} elapsed={_elapsed_ms(started)}ms")
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


def _parse_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise GraphConfigError(f"{field} must be a boolean")


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
    if async_mode == "result_key" and result_key not in provider_keys(provides):
        raise GraphConfigError(f"pipeline.nodes[{index}].result_key must be declared in provides")
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


def _validate_when_expression(value: str, *, field: str) -> None:
    operators = [operator for operator in ("==", "!=") if operator in value]
    if len(operators) != 1:
        raise GraphConfigError(f"{field} must use == or !=")
    left, right = (part.strip() for part in value.split(operators[0], 1))
    if not left or not right:
        raise GraphConfigError(f"{field} must compare a key to a literal")
    if right in {"true", "false"}:
        return
    if len(right) >= 2 and right[0] == right[-1] and right[0] in {"'", '"'}:
        return
    raise GraphConfigError(f"{field} literal must be true, false, or quoted string")


def _parse_node_params(item: Mapping[str, Any], *, reserved: set[str], field: str) -> dict[str, Any]:
    raw_config = item.get("config", {})
    if raw_config in (None, {}):
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    inline = {str(k): v for k, v in item.items() if k not in reserved}
    return {**{str(k): v for k, v in raw_config.items()}, **inline}


def _parse_node_metadata(item: Mapping[str, Any]) -> NodeMetadata:
    for removed in ("category", "version"):
        if removed in item:
            raise GraphConfigError(f"node metadata field {removed!r} is removed; use display_name and description")
    return NodeMetadata(
        display_name=_optional_string(item.get("display_name", "")),
        description=_optional_string(item.get("description", "")),
    )


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


def _parse_loop_spec(value: Any, *, type_used: str, provides: tuple[DataProvider, ...], field: str) -> LoopSpec:
    if type_used not in LOOP_NODE_TYPES:
        if value not in (None, {}):
            raise GraphConfigError(f"{field} is only allowed on VibeFlow loop nodes")
        return LoopSpec()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    allowed = {"body", "max_iterations", "stop_after", "stop_when", "carry", "collect", "outputs"}
    unknown = sorted(set(str(key) for key in value) - allowed)
    if unknown:
        raise GraphConfigError(f"{field} contains unsupported loop keys: {unknown}")
    body = _parse_required_text(value.get("body"), field=f"{field}.body")
    max_iterations = _parse_positive_int(value.get("max_iterations", 1000), field=f"{field}.max_iterations")
    has_stop_after = "stop_after" in value
    has_stop_when = "stop_when" in value
    if has_stop_after == has_stop_when:
        raise GraphConfigError(f"{field} must declare exactly one of stop_after or stop_when")
    stop_after = _parse_positive_int(value.get("stop_after"), field=f"{field}.stop_after") if has_stop_after else 0
    if stop_after and stop_after > max_iterations:
        raise GraphConfigError(f"{field}.stop_after must be <= max_iterations")
    stop_when = _parse_loop_stop_when(value.get("stop_when"), field=f"{field}.stop_when") if has_stop_when else LoopStopWhenSpec()
    carry = tuple(_parse_loop_carry_item(item, field=f"{field}.carry[{index}]") for index, item in enumerate(_parse_list(value.get("carry", ()), field=f"{field}.carry")))
    collect = tuple(_parse_loop_collect_item(item, field=f"{field}.collect[{index}]") for index, item in enumerate(_parse_list(value.get("collect", ()), field=f"{field}.collect")))
    outputs = tuple(_parse_loop_output_item(item, field=f"{field}.outputs[{index}]") for index, item in enumerate(_parse_list(value.get("outputs", ()), field=f"{field}.outputs")))
    if not outputs:
        outputs = tuple(LoopOutputSpec(source=provider.key, target=provider.key) for provider in provides)
    return LoopSpec(
        body=_normalize_loop_body(body),
        max_iterations=max_iterations,
        stop_after=stop_after,
        stop_when=stop_when,
        carry=carry,
        collect=collect,
        outputs=outputs,
    )


def _parse_loop_stop_when(value: Any, *, field: str) -> LoopStopWhenSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    equals = value.get("equals", True)
    if not isinstance(equals, bool):
        raise GraphConfigError(f"{field}.equals must be a boolean")
    return LoopStopWhenSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        equals=equals,
    )


def _parse_loop_carry_item(value: Any, *, field: str) -> LoopCarrySpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    return LoopCarrySpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
        update=_parse_required_text(value.get("update"), field=f"{field}.update"),
    )


def _parse_loop_collect_item(value: Any, *, field: str) -> LoopCollectSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    mode = str(value.get("mode", "all")).strip()
    if mode != "all":
        raise GraphConfigError(f"{field}.mode must be 'all'")
    return LoopCollectSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
        mode=mode,
    )


def _parse_loop_output_item(value: Any, *, field: str) -> LoopOutputSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    return LoopOutputSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
    )


def _parse_required_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GraphConfigError(f"{field} must be a non-empty string")
    return text


def _parse_positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GraphConfigError(f"{field} must be an integer >= 1")
    return value


def _parse_list(value: Any, *, field: str) -> list[Any]:
    if value in (None, ()):
        return []
    if isinstance(value, str) or not isinstance(value, list):
        raise GraphConfigError(f"{field} must be a list")
    return value


def _normalize_loop_body(value: str) -> str:
    if value.startswith("nodeset."):
        raise GraphConfigError("loop.body must use the nodeset type_key directly, not nodeset.<name>")
    return value


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


def _trace_config_parse(message: str) -> None:
    if str(os.environ.get("VIBEFLOW_CONFIG_TRACE", "")).lower() not in {"1", "true", "yes", "on"}:
        return
    print(f"[vibeflow config] {message}", file=sys.stderr)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
