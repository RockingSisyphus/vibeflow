"""Expand local rule graphs and resolve configuration before execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from vibeflow.core.algorithms import strongly_connected_components
from vibeflow.core.config.node import merge_node_config, normalize_node_config_spec
from vibeflow.core.rules.models import RuleCall, RuleDescriptor, RuleRelation, RulesetDescriptor, plain, readonly


@dataclass
class RuleGraphError(ValueError):
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return self.code

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class RuleInvocation:
    id: str
    rule: RuleDescriptor
    params: Mapping[str, Any]
    dependencies: tuple[str, ...] = ()
    inputs: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    origins: tuple[str, ...] = ()
    parameter_sources: Mapping[str, str] = field(default_factory=dict)
    original_rule_id: str = ""

    def __post_init__(self) -> None:
        for name in ("params", "inputs", "parameter_sources"):
            object.__setattr__(self, name, readonly(getattr(self, name)))

    @property
    def rule_id(self) -> str:
        return self.rule.id

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "rule_id": self.rule.id, "original_rule_id": self.original_rule_id or self.rule.id,
                "params": plain(self.params), "dependencies": list(self.dependencies), "inputs": plain(self.inputs),
                "origins": list(self.origins), "parameter_sources": plain(self.parameter_sources)}


@dataclass(frozen=True)
class RulePlan:
    ruleset_id: str
    entrypoint: str
    invocations: tuple[RuleInvocation, ...]
    relations: tuple[RuleRelation, ...] = ()

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.invocations)

    def to_dict(self) -> dict[str, object]:
        return {"ruleset_id": self.ruleset_id, "entrypoint": self.entrypoint, "order": list(self.order),
                "calls": [item.to_dict() for item in self.invocations],
                "relations": [item.to_dict() for item in self.relations]}


def _lookup(catalog: Any, key: str, kind: str) -> Any:
    value = catalog.get(key) if catalog is not None else None
    if value is None:
        raise RuleGraphError("RULE.RESOURCE.UNKNOWN", f"unknown {kind} '{key}'", {"id": key, "kind": kind})
    return value


def _cycles(adjacency: Mapping[str, list[str]], kind: str) -> None:
    for component in strongly_connected_components(adjacency):
        if len(component) > 1 or (component and component[0] in adjacency.get(component[0], ())):
            raise RuleGraphError(f"RULE.{kind.upper()}.CYCLE", f"{kind} relation cycle: {' -> '.join(sorted(component))}", {"members": sorted(component)})


class _Expansion:
    def __init__(self, rules: Any, rulesets: Any, entrypoint: str):
        self.rules, self.rulesets, self.entrypoint = rules, rulesets, entrypoint
        self.calls: dict[str, tuple[RuleCall, RuleDescriptor, tuple[str, ...]]] = {}
        self.groups: dict[str, tuple[str, ...]] = {}
        self.entries: dict[str, tuple[str, ...]] = {}
        self.includes: dict[str, list[str]] = {}
        self.relations: list[RuleRelation] = []

    def expand(self, descriptor: RulesetDescriptor, prefix: str = "", stack: tuple[str, ...] = ()) -> None:
        if descriptor.id in stack:
            raise RuleGraphError("RULE.INCLUDES.CYCLE", "ruleset inclusion cycle: " + " -> ".join((*stack, descriptor.id)))
        origin = (*stack, descriptor.id)
        group_id = prefix.rstrip("/") or "$self"
        members = tuple(prefix + item.id for item in descriptor.calls)
        self.groups[group_id] = members
        selected = descriptor.entrypoints.get(self.entrypoint)
        if selected is None:
            selected = tuple(item.id for item in descriptor.calls) if self.entrypoint == "static" else ()
        self.entries[group_id] = tuple(group_id if item == "$self" else prefix + item for item in selected)
        for call in descriptor.calls:
            qualified = prefix + call.id
            if call.ruleset_id:
                if call.params:
                    raise RuleGraphError("RULE.PARAMS.GROUP", f"ruleset call '{qualified}' uses params; bind member params with a local overrides relation")
                self.expand(_lookup(self.rulesets, call.ruleset_id, "ruleset"), qualified + "/", origin)
            else:
                self.calls[qualified] = (call, _lookup(self.rules, call.rule_id, "rule"), origin)
        for relation in descriptor.relations:
            source = group_id if relation.source == "$self" else prefix + relation.source
            target = group_id if relation.target == "$self" else prefix + relation.target
            self.relations.append(RuleRelation(source, target, relation.kind, relation.bindings, relation.params, relation.replace_rule))

    def selected(self) -> set[str]:
        known = set(self.calls) | set(self.groups)
        includes: dict[str, list[str]] = {key: [] for key in known}
        explicit_groups: set[str] = set()
        for relation in self.relations:
            if relation.source not in known or relation.target not in known:
                raise RuleGraphError("RULE.RELATION.UNKNOWN", f"unknown endpoint in {relation.source} -> {relation.target}")
            if relation.kind == "includes":
                if relation.source not in self.groups:
                    raise RuleGraphError("RULE.INCLUDES.SUBJECT", f"rule '{relation.source}' cannot include members")
                includes[relation.source].append(relation.target)
                explicit_groups.add(relation.source)
        for group, members in self.groups.items():
            if group not in explicit_groups:
                includes[group].extend(members)
        _cycles(includes, "includes")
        self.includes = includes
        chosen: set[str] = set()
        visiting: set[str] = set()

        def select(key: str, follow_entries: bool = True) -> None:
            if key not in known:
                raise RuleGraphError("RULE.ENTRYPOINT.UNKNOWN", f"entrypoint references unknown call '{key}'")
            if key in self.calls:
                chosen.add(key)
                return
            if key in visiting:
                return
            visiting.add(key)
            entries = self.entries[key]
            if key in explicit_groups and self.entrypoint == "static" and entries == self.groups[key]:
                entries = tuple(includes[key])
            for child in entries if follow_entries else includes[key]:
                if child == key:
                    for included in includes[key]:
                        select(included)
                else:
                    select(child)
            visiting.remove(key)

        select("$self")
        # A selected consumer also selects its declared providers.
        changed = True
        while changed:
            before = set(chosen)
            for relation in self.relations:
                if relation.kind == "requires" and self.members(relation.source, chosen):
                    select(relation.target)
            changed = chosen != before
        return chosen

    def members(self, key: str, selected: set[str]) -> tuple[str, ...]:
        if key in self.calls:
            return (key,) if key in selected else ()
        members, seen, pending = set(), set(), [key]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if current in self.calls:
                if current in selected:
                    members.add(current)
            else:
                pending.extend(self.includes.get(current, ()))
        return tuple(sorted(members))


def _dominates(source: str, other: str, adjacency: Mapping[str, list[str]]) -> bool:
    seen, pending = set(), [source]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if current == other:
            return True
        pending.extend(adjacency.get(current, ()))
    return False


def _winner(target: str, key: str, candidates: list[tuple[str, Any]], adjacency: Mapping[str, list[str]]) -> tuple[Any, str]:
    survivors = [(source, value) for source, value in candidates if not any(
        other != source and _dominates(other, source, adjacency) for other, _ in candidates)]
    value = survivors[0][1]
    if any(item != value for _, item in survivors[1:]):
        raise RuleGraphError("RULE.OVERRIDE.CONFLICT", f"unordered overrides conflict on '{target}.{key}'",
                             {"target": target, "field": key, "sources": sorted(source for source, _ in survivors)})
    return value, "override:" + ",".join(sorted({source for source, _ in survivors}))


def _effective_calls(expansion: _Expansion, selected: set[str]) -> dict[str, tuple[RuleDescriptor, Mapping[str, Any], Mapping[str, str]]]:
    overrides = [item for item in expansion.relations if item.kind == "overrides"]
    precedence: dict[str, list[str]] = {key: [] for key in (*expansion.calls, *expansion.groups)}
    for relation in overrides:
        precedence[relation.source].append(relation.target)
    _cycles(precedence, "overrides")
    effective = {}
    for call_id in sorted(selected):
        call, original, _ = expansion.calls[call_id]
        candidates: dict[str, list[tuple[str, Any]]] = {}
        for relation in overrides:
            source_active = bool(expansion.members(relation.source, selected))
            if not source_active or call_id not in expansion.members(relation.target, selected):
                continue
            values = {**plain(relation.params)}
            if relation.replace_rule:
                values["$checker"] = relation.replace_rule
            for key, value in values.items():
                candidates.setdefault(key, []).append((relation.source, value))
        updates, sources = {}, {key: f"default:{original.id}" for key in original.params_defaults}
        sources.update({key: f"call:{call_id}" for key in call.params})
        for key, choices in candidates.items():
            updates[key], sources[key] = _winner(call_id, key, choices, precedence)
        replacement = updates.pop("$checker", original.id)
        rule = _lookup(expansion.rules, replacement, "replacement rule")
        if replacement != original.id:
            for port, record_type in original.outputs.items():
                if rule.outputs.get(port) != record_type:
                    raise RuleGraphError("RULE.REPLACEMENT.INTERFACE", f"replacement '{rule.id}' does not preserve output '{port}: {record_type}' of '{original.id}'")
        try:
            spec = normalize_node_config_spec(plain(rule.params_schema), plain(rule.params_defaults))
            params = merge_node_config(spec, {**plain(call.params), **updates})
        except ValueError as exc:
            raise RuleGraphError("RULE.PARAMS.SCHEMA", f"invalid params for '{call_id}': {exc}") from exc
        effective[call_id] = (rule, readonly(params), readonly(sources))
    return effective


def compile_ruleset(ruleset: str | RulesetDescriptor, *, rules: Any, rulesets: Any = None, entrypoint: str = "static") -> RulePlan:
    """Build a portable executable plan; graph direction is consumer -> provider."""
    if entrypoint not in {"import", "static", "run"}:
        raise RuleGraphError("RULE.ENTRYPOINT.INVALID", f"unknown rule entrypoint: {entrypoint!r}")
    descriptor = _lookup(rulesets, ruleset, "ruleset") if isinstance(ruleset, str) else ruleset
    if not isinstance(descriptor, RulesetDescriptor):
        raise TypeError("ruleset must be RulesetDescriptor or registered ID")
    expansion = _Expansion(rules, rulesets, entrypoint)
    expansion.expand(descriptor)
    selected = expansion.selected()
    effective = _effective_calls(expansion, selected)
    dependencies: dict[str, set[str]] = {key: set() for key in selected}
    inputs: dict[str, dict[str, tuple[str, str]]] = {key: {} for key in selected}
    for relation in expansion.relations:
        if relation.kind != "requires":
            continue
        consumers, providers = expansion.members(relation.source, selected), expansion.members(relation.target, selected)
        for consumer in consumers:
            dependencies[consumer].update(providers)
            for input_name, output_name in relation.bindings.items():
                wanted = effective[consumer][0].inputs.get(input_name)
                matches = [provider for provider in providers if effective[provider][0].outputs.get(output_name) == wanted and wanted is not None]
                if len(matches) != 1:
                    raise RuleGraphError("RULE.INPUT.BINDING", f"'{consumer}.{input_name}' requires one provider of '{output_name}: {wanted}', found {len(matches)}")
                binding = (matches[0], output_name)
                if input_name in inputs[consumer] and inputs[consumer][input_name] != binding:
                    raise RuleGraphError("RULE.INPUT.CONFLICT", f"multiple bindings for '{consumer}.{input_name}'")
                inputs[consumer][input_name] = binding
    for call_id, (rule, _, _) in effective.items():
        missing = sorted(set(rule.inputs) - set(inputs[call_id]))
        if missing:
            raise RuleGraphError("RULE.INPUT.UNBOUND", f"'{call_id}' has unbound required inputs: {missing}")
    _cycles({key: sorted(value) for key, value in dependencies.items()}, "requires")
    order: list[str] = []
    remaining = set(selected)
    while remaining:
        ready = sorted(key for key in remaining if not dependencies[key].intersection(remaining))
        order.extend(ready)
        remaining.difference_update(ready)
    invocations = tuple(RuleInvocation(key, effective[key][0], effective[key][1], tuple(sorted(dependencies[key])),
                                       inputs[key], expansion.calls[key][2], effective[key][2], expansion.calls[key][1].id) for key in order)
    return RulePlan(descriptor.id, entrypoint, invocations, tuple(expansion.relations))


__all__ = ["RuleGraphError", "RuleInvocation", "RulePlan", "compile_ruleset"]
