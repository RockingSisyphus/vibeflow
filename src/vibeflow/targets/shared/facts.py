"""Command-local identities for prepared, immutable Target facts.

Targets supply source/declaration keys. No AST, Registry or worker enters this
module; unknown mutable additions deliberately do not qualify for reuse.
"""
from dataclasses import dataclass, fields, is_dataclass, replace
import json
from uuid import uuid4

from vibeflow.core.rules import RuleContext


def fact_key(value, *, opaque_types=()):
    """Include portable data and retain the identity of opaque Target services."""
    from collections.abc import Mapping
    memo = {}
    def encode(item):
        if item is None or type(item) in {str,bool,int,float}:
            return item
        if isinstance(item, opaque_types):
            return f"{type(item).__module__}.{type(item).__qualname__}@{id(item)}"
        if id(item) in memo:
            return ["ref",memo[id(item)]]
        memo[id(item)] = len(memo)
        if isinstance(item,Mapping):
            return ["mapping",[(encode(key),encode(value)) for key,value in item.items()]]
        if isinstance(item,(tuple,list)):
            return ["sequence",[encode(value) for value in item]]
        if isinstance(item,(set,frozenset)):
            return ["set",[encode(value) for value in sorted(item,key=str)]]
        if is_dataclass(item) and not isinstance(item,type):
            return ["dataclass",type(item).__module__,type(item).__qualname__,id(type(item)),
                    [(value.name,encode(getattr(item,value.name))) for value in fields(item)]]
        return f"{type(item).__module__}.{type(item).__qualname__}@{id(item)}"
    return json.dumps(encode(value), sort_keys=True, allow_nan=False)


def stable_facts(value, active=None, memo=None, *, opaque_types=()):
    """Unknown extra objects may change without changing their Python identity."""
    from collections.abc import Mapping
    if value is None or type(value) in {str,bool,int,float}:
        return True
    if isinstance(value,opaque_types):
        return True
    active = set() if active is None else active
    memo = {} if memo is None else memo
    if id(value) in memo:
        return memo[id(value)]
    if id(value) in active:
        return False
    active.add(id(value))
    try:
        if isinstance(value,Mapping):
            stable = all(stable_facts(key,active,memo,opaque_types=opaque_types) and stable_facts(item,active,memo,opaque_types=opaque_types) for key,item in value.items())
        elif isinstance(value,(tuple,list,set,frozenset)):
            stable = all(stable_facts(item,active,memo,opaque_types=opaque_types) for item in value)
        elif is_dataclass(value) and not isinstance(value,type):
            stable = all(stable_facts(getattr(value,item.name),active,memo,opaque_types=opaque_types) for item in fields(value))
        else:
            stable = False
        memo[id(value)] = stable
        return stable
    finally:
        active.remove(id(value))


@dataclass(frozen=True)
class FactView:
    _store: object
    token: int
    _namespace: str
    _base: RuleContext

    @property
    def identity(self):
        return self._namespace, self._store.target, self.token

    @property
    def facts(self):
        return self._base.facts

    @property
    def scope(self):
        return self._base.scope

    def derive(self, additions, *, key=None):
        return self._store.capture({**self.facts, **additions},
            key=(self.identity, self._store.additions_key(additions) if key is None else key),
            scope=self.scope, base=self._base)

    def context(self, phase, subject=None, scope=None):
        return replace(self._base, subject=subject or {},
            scope=self.scope if scope is None else scope, phase=phase)


class FactStore:
    def __init__(self, target, *, opaque_types=()):
        self.target = target
        self.opaque_types = opaque_types
        self.namespace = uuid4().hex
        self.views = {}

    def additions_key(self, facts):
        if not stable_facts(facts, opaque_types=self.opaque_types):
            return object()
        return fact_key(facts, opaque_types=self.opaque_types)

    def capture(self, facts, *, key=None, scope=None, base=None):
        scope = {} if scope is None else scope
        key = (self.additions_key(facts) if key is None else key, fact_key(scope))
        if key not in self.views:
            self.views[key] = FactView(self, len(self.views) + 1, self.namespace,
                RuleContext(facts=facts, scope=scope, target=self.target,
                    _snapshots=base._snapshots if base is not None else ()))
        return self.views[key]

    def clear(self):
        self.views.clear()
        self.namespace = uuid4().hex
