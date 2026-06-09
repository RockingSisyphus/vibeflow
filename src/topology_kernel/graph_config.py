from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .boundary import BoundarySpec


@dataclass(frozen=True)
class NodeSpec:
    name: str
    node_type: str
    requires: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    node_config_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeSpec:
    source: str
    target: str
    max_executions: int = 1
    loop: str = ""
    max_executions_declared: bool = False

    @property
    def pair(self) -> tuple[str, str]:
        return (self.source, self.target)


@dataclass(frozen=True)
class LoopSpec:
    name: str
    edges: tuple[tuple[str, str], ...]
    max_iterations: int
    nodes: tuple[str, ...] = ()
    until: str = ""


@dataclass(frozen=True)
class NodesetSpec:
    name: str
    display_name: str
    category: str
    description: str
    version: str
    purity: str
    requires: tuple[str, ...]
    provides: tuple[str, ...]
    exports: tuple[str, ...]
    graph: "GraphConfig"


@dataclass(frozen=True)
class GraphConfig:
    nodes: tuple[NodeSpec, ...]
    edges: tuple[EdgeSpec, ...] = ()
    loops: tuple[LoopSpec, ...] = ()
    nodesets: dict[str, NodesetSpec] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()
    boundary: BoundarySpec | None = None


@dataclass
class GraphConfigError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Graph config error: {self.detail}"


def parse_graph_config(config: Mapping[str, Any]) -> GraphConfig:
    raw = config.get("pipeline", config)
    if not isinstance(raw, Mapping):
        raise GraphConfigError("pipeline config must be an object")

    nodesets = _parse_nodesets(config.get("nodesets", raw.get("nodesets", [])))
    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise GraphConfigError("pipeline.nodes must be a non-empty list")
    nodes = tuple(_parse_node(item, index=index) for index, item in enumerate(nodes_raw))
    names = {node.name for node in nodes}
    if len(names) != len(nodes):
        raise GraphConfigError("duplicate node name")
    edges = tuple(_parse_edge(item, index=index) for index, item in enumerate(raw.get("edges", [])))
    loops = tuple(_parse_loop(item, index=index) for index, item in enumerate(raw.get("loops", [])))
    inputs = _as_tuple(raw.get("inputs", ()), field="pipeline.inputs")

    for edge in edges:
        if edge.source not in names or edge.target not in names:
            raise GraphConfigError(f"edge references unknown node: {edge.source}->{edge.target}")
    for loop in loops:
        if loop.max_iterations < 1:
            raise GraphConfigError(f"loop '{loop.name}' max_iterations must be >= 1")
        for source, target in loop.edges:
            if source not in names or target not in names:
                raise GraphConfigError(f"loop '{loop.name}' references unknown edge node: {source}->{target}")
    boundary = _parse_boundary(config.get("boundary"))
    return GraphConfig(nodes=nodes, edges=edges, loops=loops, nodesets=nodesets, inputs=inputs, boundary=boundary)


def _parse_node(item: Any, *, index: int) -> NodeSpec:
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.nodes[{index}] must be an object")
    name = str(item.get("name", "")).strip()
    node_type = str(item.get("type", item.get("registry_key", ""))).strip()
    if not name or not node_type:
        raise GraphConfigError(f"pipeline.nodes[{index}] requires name and type")
    reserved = {"name", "type", "registry_key", "requires", "provides", "config", "node_configs"}
    return NodeSpec(
        name=name,
        node_type=node_type,
        requires=_as_tuple(item.get("requires", ()), field=f"node[{name}].requires"),
        provides=_as_tuple(item.get("provides", ()), field=f"node[{name}].provides"),
        params=_parse_node_params(item, reserved=reserved, field=f"node[{name}].config"),
        node_config_overrides=_parse_node_config_overrides(item.get("node_configs", {}), field=f"node[{name}].node_configs"),
    )


def _parse_edge(item: Any, *, index: int) -> EdgeSpec:
    if isinstance(item, (list, tuple)) and len(item) == 2:
        return EdgeSpec(source=str(item[0]).strip(), target=str(item[1]).strip(), max_executions=1)
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.edges[{index}] must be [from, to] or object")
    source = str(item.get("from", item.get("source", ""))).strip()
    target = str(item.get("to", item.get("target", ""))).strip()
    if not source or not target:
        raise GraphConfigError(f"pipeline.edges[{index}] requires from/to")
    max_executions_declared = "max_executions" in item or "max" in item
    max_value = item.get("max_executions", item.get("max", 1))
    if isinstance(max_value, bool) or not isinstance(max_value, int):
        raise GraphConfigError(f"pipeline.edges[{index}].max_executions must be an integer >= 1")
    max_executions = max_value
    if max_executions < 1:
        raise GraphConfigError(f"pipeline.edges[{index}].max_executions must be >= 1")
    return EdgeSpec(
        source=source,
        target=target,
        max_executions=max_executions,
        loop=str(item.get("loop", "")).strip(),
        max_executions_declared=max_executions_declared,
    )


def _parse_loop(item: Any, *, index: int) -> LoopSpec:
    if not isinstance(item, Mapping):
        raise GraphConfigError(f"pipeline.loops[{index}] must be an object")
    name = str(item.get("name", "")).strip()
    if not name:
        raise GraphConfigError(f"pipeline.loops[{index}] missing name")
    edges_raw = item.get("edges", [])
    if not isinstance(edges_raw, list) or not edges_raw:
        raise GraphConfigError(f"loop '{name}' requires non-empty edges")
    edges = []
    for edge_index, edge in enumerate(edges_raw):
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise GraphConfigError(f"loop '{name}'.edges[{edge_index}] must be [from, to]")
        edges.append((str(edge[0]).strip(), str(edge[1]).strip()))
    nodes = _as_tuple(item.get("nodes", ()), field=f"loop[{name}].nodes")
    if "max_iterations" not in item and "max_executions" not in item:
        raise GraphConfigError(f"loop '{name}' requires max_iterations or max_executions")
    max_value = item.get("max_iterations", item.get("max_executions"))
    if isinstance(max_value, bool) or not isinstance(max_value, int):
        raise GraphConfigError(f"loop '{name}' max_iterations must be an integer >= 1")
    return LoopSpec(
        name=name,
        edges=tuple(edges),
        max_iterations=max_value,
        nodes=nodes,
        until=str(item.get("until", "")).strip(),
    )


def _parse_nodesets(value: Any) -> dict[str, NodesetSpec]:
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
        pipeline = item.get("pipeline")
        if not isinstance(pipeline, Mapping):
            raise GraphConfigError(f"nodeset '{name}' requires pipeline")
        graph = parse_graph_config({"pipeline": pipeline, "nodesets": value[:index]})
        out[name] = NodesetSpec(
            name=name,
            display_name=str(item.get("display_name", name)),
            category=str(item.get("category", "composite")),
            description=str(item.get("description", "")),
            version=str(item.get("version", "0.1.0")),
            purity=str(item.get("purity", "pure")),
            requires=_as_tuple(item.get("requires", ()), field=f"nodeset[{name}].requires"),
            provides=_as_tuple(item.get("provides", ()), field=f"nodeset[{name}].provides"),
            exports=_as_tuple(item.get("exports", item.get("provides", ())), field=f"nodeset[{name}].exports"),
            graph=graph,
        )
    return out


def _parse_boundary(value: Any) -> BoundarySpec | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise GraphConfigError("boundary must be an object")
    boundary_type = str(value.get("type", "")).strip()
    if not boundary_type:
        raise GraphConfigError("boundary.type must be a non-empty string")
    config = value.get("config", {})
    if not isinstance(config, Mapping):
        raise GraphConfigError("boundary.config must be an object")
    return BoundarySpec(
        boundary_type=boundary_type,
        config={str(key): item for key, item in config.items()},
        consumes=_as_tuple(value.get("consumes", ()), field="boundary.consumes"),
        provides=_as_tuple(value.get("provides", ()), field="boundary.provides"),
        allowed_paths=_as_tuple(value.get("allowed_paths", ()), field="boundary.allowed_paths"),
    )


def _as_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise GraphConfigError(f"{field} must be a list")
    return tuple(str(item).strip() for item in value if str(item).strip())


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
