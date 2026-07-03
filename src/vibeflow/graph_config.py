from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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

STATUS_PLANNED = "planned"
STATUS_IMPLEMENTED = "implemented"
STATUSES = frozenset({STATUS_PLANNED, STATUS_IMPLEMENTED})


@dataclass(frozen=True)
class NodeSpec:
    name: str
    node_type: str
    requires: tuple[DataRequirement, ...] = ()
    provides: tuple[DataProvider, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    node_config_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    allow_config_override: bool = False
    status: str = STATUS_IMPLEMENTED
    flow_kind: str = ""
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)
    async_mode: str = ""
    result_key: str = ""


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
    name: str
    display_name: str
    category: str
    description: str
    version: str
    purity: str
    requires: tuple[DataRequirement, ...]
    provides: tuple[DataProvider, ...]
    exports: tuple[DataProvider, ...]
    graph: "GraphConfig"
    global_config: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_IMPLEMENTED
    flow_kind: str = FLOW_KIND_PREDEFINED
    planned_behavior: PlannedBehavior = field(default_factory=blocking_planned_behavior)


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
    raw = config.get("pipeline", config)
    if not isinstance(raw, Mapping):
        raise GraphConfigError("pipeline config must be an object")
    if "boundary" in config or "boundary" in raw:
        raise GraphConfigError("boundary is removed; use terminal/io/data_store/document nodes")
    if "loops" in raw:
        raise GraphConfigError("pipeline.loops is removed; model cycles with decision routing")

    root_text = str(Path(project_root).resolve()) if project_root is not None else ""
    nodesets = _parse_nodesets(config.get("nodesets", raw.get("nodesets", [])), project_root=root_text)
    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise GraphConfigError("pipeline.nodes must be a non-empty list")
    nodes = tuple(_parse_node(item, index=index) for index, item in enumerate(nodes_raw))
    names = {node.name for node in nodes}
    if len(names) != len(nodes):
        raise GraphConfigError("duplicate node name")
    edges = tuple(_parse_edge(item, index=index) for index, item in enumerate(raw.get("edges", [])))
    try:
        inputs = parse_data_providers(raw.get("inputs", ()), field="pipeline.inputs")
        outputs = parse_data_requirements(raw.get("outputs", ()), field="pipeline.outputs")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    max_steps = _parse_max_steps(raw.get("max_steps", 1000))

    for edge in edges:
        if edge.source not in names or edge.target not in names:
            raise GraphConfigError(f"edge references unknown node: {edge.source}->{edge.target}")
    return GraphConfig(nodes=nodes, edges=edges, nodesets=nodesets, inputs=inputs, outputs=outputs, max_steps=max_steps, project_root=root_text)


def _parse_node(item: Any, *, index: int) -> NodeSpec:
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.nodes[{index}] must be an object")
    name = str(item.get("name", "")).strip()
    status = _parse_status(item.get("status", STATUS_IMPLEMENTED), field=f"pipeline.nodes[{index}].status")
    node_type = str(item.get("type", item.get("registry_key", ""))).strip()
    if not name:
        raise GraphConfigError(f"pipeline.nodes[{index}] requires name")
    if status == STATUS_IMPLEMENTED and "planned_behavior" in item:
        raise GraphConfigError(f"pipeline.nodes[{index}].planned_behavior is only allowed for planned nodes")
    if not node_type:
        if status != STATUS_PLANNED:
            raise GraphConfigError(f"pipeline.nodes[{index}] requires type")
        node_type = f"planned.{name}"
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
        requires = parse_data_requirements(item.get("requires", ()), field=f"node[{name}].requires")
        provides = parse_data_providers(item.get("provides", ()), field=f"node[{name}].provides")
    except ValueError as exc:
        raise GraphConfigError(str(exc)) from exc
    async_mode, result_key = _parse_node_async(item, index=index, provides=provides)
    reserved = {
        "name",
        "type",
        "registry_key",
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
    }
    return NodeSpec(
        name=name,
        node_type=node_type,
        requires=requires,
        provides=provides,
        params=_parse_node_params(item, reserved=reserved, field=f"node[{name}].config"),
        node_config_overrides=_parse_node_config_overrides(item.get("node_configs", {}), field=f"node[{name}].node_configs"),
        allow_config_override=_parse_bool(item.get("allow_config_override", item.get("override_child_config", False)), field=f"node[{name}].allow_config_override"),
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


def _parse_nodesets(value: Any, *, project_root: str = "") -> dict[str, NodesetSpec]:
    if value is None:
        return {}
    if not isinstance(value, list):
        raise GraphConfigError("nodesets must be a list")
    out: dict[str, NodesetSpec] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise GraphConfigError(f"nodesets[{index}] must be an object")
        name = str(item.get("name", "")).strip()
        if not name:
            raise GraphConfigError(f"nodesets[{index}] missing name")
        if name in out:
            raise GraphConfigError(f"duplicate nodeset: {name}")
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
        pipeline = item.get("pipeline")
        if pipeline is None and status == STATUS_PLANNED:
            graph = GraphConfig(nodes=(), project_root=project_root)
        elif not isinstance(pipeline, Mapping):
            raise GraphConfigError(f"nodeset '{name}' requires pipeline")
        else:
            graph = parse_graph_config({"pipeline": pipeline, "nodesets": value[:index]}, project_root=project_root)
        out[name] = NodesetSpec(
            name=name,
            display_name=str(item.get("display_name", name)),
            category=str(item.get("category", "composite")),
            description=str(item.get("description", "")),
            version=str(item.get("version", "0.1.0")),
            purity=str(item.get("purity", "pure")),
            requires=_parse_nodeset_requirements(item.get("requires", ()), field=f"nodeset[{name}].requires"),
            provides=_parse_nodeset_providers(item.get("provides", ()), field=f"nodeset[{name}].provides"),
            exports=_parse_nodeset_providers(item.get("exports", item.get("provides", ())), field=f"nodeset[{name}].exports"),
            graph=graph,
            global_config=_parse_mapping(item.get("global_config", {}), field=f"nodeset[{name}].global_config"),
            status=status,
            flow_kind=flow_kind,
            planned_behavior=planned_behavior,
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
