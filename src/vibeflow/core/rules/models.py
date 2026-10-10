"""Portable declarations and records for composable review rules.

These objects contain no discovery, language parser, or implementation loading.
Targets supply callables; Tooling supplies the exact check scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from copy import copy
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping

from vibeflow.core.descriptors.models import RuleImplementationDescriptor, ResourceImplementationConflict
from vibeflow.core.findings import Finding


def readonly(value: Any, _memo: dict[int, Any] | None = None) -> Any:
    """Freeze a shared graph while retaining opaque Target services as supplied."""
    memo = {} if _memo is None else _memo
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, Mapping):
        contents = {}
        snapshot = MappingProxyType(contents)
        memo[id(value)] = snapshot
        contents.update({key: readonly(item, memo) for key, item in value.items()})
        return snapshot
    if isinstance(value, (tuple, list)):
        snapshot = tuple(readonly(item, memo) for item in value)
        # A back-reference through a mapping/dataclass may have completed this
        # sequence during recursion. Keep that instance as the shared result.
        return memo.setdefault(id(value), snapshot)
    if isinstance(value, (set, frozenset)):
        snapshot = frozenset(readonly(item, memo) for item in value)
        return memo.setdefault(id(value), snapshot)
    if is_dataclass(value) and not isinstance(value, type):
        snapshot = copy(value)
        memo[id(value)] = snapshot
        for item in fields(value):
            object.__setattr__(snapshot, item.name, readonly(getattr(value, item.name), memo))
        return snapshot
    return value


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [plain(item) for item in sorted(value, key=str)]
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: plain(getattr(value, item.name)) for item in fields(value)}
    return value


def _record_snapshot(value: Any, active: set[int] | None = None, _memo: dict[int, Any] | None = None) -> Any:
    """Output ports contain data, while Target services stay in context facts."""
    if value is None:
        return None
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and isfinite(value):
        return float(value)
    visiting = set() if active is None else active
    memo = {} if _memo is None else _memo
    if id(value) in visiting:
        raise ValueError("record.value cannot contain cyclic data")
    if id(value) in memo:
        return memo[id(value)]
    visiting.add(id(value))
    try:
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("record.value object keys must be strings")
            snapshot = MappingProxyType({str(key): _record_snapshot(item, visiting, memo) for key, item in value.items()})
        elif isinstance(value, (tuple, list)):
            snapshot = tuple(_record_snapshot(item, visiting, memo) for item in value)
        elif isinstance(value, (set, frozenset)):
            snapshot = frozenset(_record_snapshot(item, visiting, memo) for item in value)
        elif is_dataclass(value) and not isinstance(value, type) and type(value).__dataclass_params__.frozen:
            snapshot = copy(value)
            for item in fields(value):
                object.__setattr__(snapshot, item.name, _record_snapshot(getattr(value, item.name), visiting, memo))
        else:
            raise ValueError(f"record.value must contain portable data or frozen dataclasses, got {type(value).__name__}")
        memo[id(value)] = snapshot
        return snapshot
    finally:
        visiting.remove(id(value))


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


@dataclass(frozen=True)
class RuleDescriptor:
    id: str
    display_name: str = ""
    description: str = ""
    implementations: tuple[RuleImplementationDescriptor, ...] = ()
    inputs: Mapping[str, str] = field(default_factory=dict)
    outputs: Mapping[str, str] = field(default_factory=dict)
    params_schema: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    params_defaults: Mapping[str, Any] = field(default_factory=dict)
    handler: str = ""
    scope: str = "call"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "rule.id"))
        if not isinstance(self.scope, str) or self.scope not in {"call", "source"}:
            raise ValueError("rule.scope must be 'call' or 'source'")
        for name in ("inputs", "outputs"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"rule.{name} must be an object")
            object.__setattr__(self, name, readonly({_text(key, name): _text(item, name) for key, item in value.items()}))
        for name in ("params_schema", "params_defaults"):
            if not isinstance(getattr(self, name), Mapping):
                raise ValueError(f"rule.{name} must be an object")
            object.__setattr__(self, name, readonly(getattr(self, name)))
        implementations = tuple(self.implementations)
        if not all(isinstance(item, RuleImplementationDescriptor) for item in implementations):
            raise ValueError("rule.implementations must contain RuleImplementationDescriptor")
        if self.handler and implementations:
            raise ResourceImplementationConflict("rule.handler cannot be combined with an implementation", field_name="rule.handler")
        families = [item.execution_family for item in implementations]
        if len(set(families)) != len(families):
            raise ValueError("rule.implementations contains duplicate execution families")
        object.__setattr__(self, "implementations", implementations)

    def to_dict(self) -> dict[str, object]:
        return {"kind": "rule", "id": self.id, "display_name": self.display_name,
                "description": self.description, "implementations": [item.to_dict() for item in self.implementations],
                "inputs": plain(self.inputs), "outputs": plain(self.outputs),
                "params_schema": plain(self.params_schema), "params_defaults": plain(self.params_defaults),
                "handler": self.handler, "scope": self.scope}


@dataclass(frozen=True)
class RuleCall:
    id: str
    rule_id: str = ""
    ruleset_id: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "call.id"))
        if bool(self.rule_id) == bool(self.ruleset_id):
            raise ValueError("rule call must select exactly one rule_id or ruleset_id")
        if "/" in self.id or self.id == "$self":
            raise ValueError("local call.id cannot contain '/' or be '$self'")
        if not isinstance(self.params, Mapping):
            raise ValueError("call.params must be an object")
        object.__setattr__(self, "params", readonly(self.params))

    def to_dict(self) -> dict[str, object]:
        result = {"id": self.id, "params": plain(self.params)}
        result["rule_id" if self.rule_id else "ruleset_id"] = self.rule_id or self.ruleset_id
        return result


@dataclass(frozen=True)
class RuleRelation:
    source: str
    target: str
    kind: str
    bindings: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)
    replace_rule: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _text(self.source, "relation.source"))
        object.__setattr__(self, "target", _text(self.target, "relation.target"))
        if not isinstance(self.kind, str) or self.kind not in {"includes", "requires", "overrides"}:
            raise ValueError(f"unknown rule relation kind: {self.kind}")
        if not isinstance(self.bindings, Mapping) or not isinstance(self.params, Mapping):
            raise ValueError("relation bindings/params must be objects")
        if self.kind != "requires" and self.bindings:
            raise ValueError("only requires relations can bind records")
        if self.kind != "overrides" and (self.params or self.replace_rule):
            raise ValueError("only overrides relations can replace params/checker")
        for port, output in self.bindings.items():
            _text(port, "relation.bindings port")
            _text(output, "relation.bindings output")
        if self.replace_rule:
            _text(self.replace_rule, "relation.replace_rule")
        object.__setattr__(self, "bindings", readonly(self.bindings))
        object.__setattr__(self, "params", readonly(self.params))

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source, "target": self.target, "kind": self.kind,
                "bindings": plain(self.bindings), "params": plain(self.params), "replace_rule": self.replace_rule}


@dataclass(frozen=True)
class RulesetDescriptor:
    id: str
    calls: tuple[RuleCall, ...] = ()
    relations: tuple[RuleRelation, ...] = ()
    entrypoints: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    display_name: str = ""
    description: str = ""
    workflow_default: bool = False
    graph_scope: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "ruleset.id"))
        if type(self.workflow_default) is not bool:
            raise ValueError("ruleset.workflow_default must be a boolean")
        if self.graph_scope not in {None, "current_graph", "effective_subtree"}:
            raise ValueError("ruleset.graph_scope must be current_graph or effective_subtree")
        calls, relations = tuple(self.calls), tuple(self.relations)
        if not all(isinstance(item, RuleCall) for item in calls):
            raise ValueError("ruleset.calls must contain RuleCall")
        if not all(isinstance(item, RuleRelation) for item in relations):
            raise ValueError("ruleset.relations must contain RuleRelation")
        if len({item.id for item in calls}) != len(calls):
            raise ValueError("ruleset has duplicate local call IDs")
        object.__setattr__(self, "calls", calls)
        object.__setattr__(self, "relations", relations)
        if not isinstance(self.entrypoints, Mapping):
            raise ValueError("ruleset.entrypoints must be an object")
        if set(self.entrypoints) - {"import", "static", "run"}:
            raise ValueError("ruleset.entrypoints keys must be import, static or run")
        for value in self.entrypoints.values():
            if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError("entrypoint must contain a list of non-empty local call IDs")
        object.__setattr__(self, "entrypoints", readonly({key: tuple(value) for key, value in self.entrypoints.items()}))

    def to_dict(self) -> dict[str, object]:
        return {"kind": "ruleset", "id": self.id, "calls": [item.to_dict() for item in self.calls],
                "relations": [item.to_dict() for item in self.relations], "entrypoints": plain(self.entrypoints),
                "display_name": self.display_name, "description": self.description,
                "workflow_default": self.workflow_default, "graph_scope": self.graph_scope}


@dataclass(frozen=True)
class RuleRecord:
    type_id: str
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_id", _text(self.type_id, "record.type_id"))
        object.__setattr__(self, "value", _record_snapshot(self.value))

    def to_dict(self) -> dict[str, object]:
        return {"type_id": self.type_id, "value": plain(self.value)}


@dataclass(frozen=True)
class RuleResult:
    records: Mapping[str, RuleRecord] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    state: str = "completed"

    def __post_init__(self) -> None:
        if not isinstance(self.state, str) or self.state not in {"completed", "failed", "unavailable"}:
            raise ValueError(f"unknown rule result state: {self.state}")
        if not isinstance(self.records, Mapping):
            raise ValueError("rule result records must be an object")
        records = {_text(key, "result port"): value if isinstance(value, RuleRecord) else RuleRecord(**value) for key, value in self.records.items()}
        findings = tuple(self.findings)
        if not all(isinstance(item, Finding) for item in findings):
            raise ValueError("rule result findings must contain Finding")
        object.__setattr__(self, "records", MappingProxyType(records))
        object.__setattr__(self, "findings", tuple(readonly(item) for item in findings))

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state, "records": {key: value.to_dict() for key, value in self.records.items()},
                "findings": [item.to_dict() for item in self.findings]}


@dataclass(frozen=True)
class RuleContext:
    facts: Mapping[str, Any] = field(default_factory=dict)
    subject: Mapping[str, Any] = field(default_factory=dict)
    scope: Mapping[str, Any] = field(default_factory=dict)
    phase: str = "static"
    target: str = "python"
    _snapshots: tuple[Mapping[str, Any], ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        memo = {}
        # dataclasses.replace carries this provenance from the existing context.
        # Seed only owned snapshots, not raw object IDs or arbitrary proxies.
        # The shallow index stays proportional to fact fields, not their graphs.
        for snapshot in self._snapshots:
            memo[id(snapshot)] = snapshot
            memo.update((id(value), value) for value in snapshot.values())
        for name in ("facts", "subject", "scope"):
            if not isinstance(getattr(self, name), Mapping):
                raise ValueError(f"context.{name} must be an object")
            object.__setattr__(self, name, readonly(getattr(self, name), memo))
        object.__setattr__(self, "_snapshots", (self.facts, self.subject, self.scope))

    def require(self, name: str) -> Any:
        if name not in self.facts:
            raise KeyError(f"rule context is missing fact '{name}'")
        return self.facts[name]


EFFECT_POLICY_TYPE = "vibeflow.effect_policy.v1"


def effect_policies(result: Any) -> tuple[Mapping[str, Any], ...]:
    """Read explicit policy outputs; never infer grants from flow_kind."""
    values = result.results.values() if hasattr(result, "results") else (result,)
    unique = {id(item): item for item in values}
    return tuple(record.value for item in unique.values() if item.state == "completed"
                 for record in item.records.values() if record.type_id == EFFECT_POLICY_TYPE and isinstance(record.value, Mapping))


__all__ = ["EFFECT_POLICY_TYPE", "RuleCall", "RuleContext", "RuleDescriptor", "RuleRecord", "RuleRelation", "RuleResult", "RulesetDescriptor", "effect_policies", "plain", "readonly"]
