from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vibeflow.data_contract import DataProvider, DataRequirement
from vibeflow.node import FLOW_KIND_PREDEFINED
from vibeflow.graph_config.planned_behavior import PlannedBehavior, blocking_planned_behavior

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
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

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
    root_id: str = ""
    root_path: str = ""
    source_path: str = ""

@dataclass
class GraphConfigError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Graph config error: {self.detail}"
