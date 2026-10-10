"""Portable rule references and resolved selection provenance."""
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RuleReference:
    rule_id: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("selection.rule_id must be a non-empty string")
        if not isinstance(self.params, Mapping):
            raise ValueError("selection.params must be an object")
        object.__setattr__(self, "rule_id", self.rule_id.strip())
        # Freeze recursively using the shared data protocol once imports have settled.
        from vibeflow.core.rules.models import readonly
        object.__setattr__(self, "params", readonly(self.params))

    @property
    def id(self):
        return self.rule_id

    def to_dict(self):
        from vibeflow.core.rules.models import plain
        return {"rule_id": self.rule_id, "params": plain(self.params)}


def selection_refs(value, *, optional=False, field_name="rulesets"):
    """Keep absence distinct from an explicitly empty selection."""
    if value is None and optional:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of Ruleset IDs or Rule references")
    result, seen = [], set()
    for item in value:
        if isinstance(item, str) and item.strip():
            reference, key = item.strip(), ("ruleset", item.strip())
        elif isinstance(item, RuleReference):
            reference, key = item, ("rule", item.rule_id)
        elif isinstance(item, Mapping) and set(item) <= {"rule_id", "params"}:
            reference = RuleReference(item.get("rule_id"), item.get("params", {}))
            key = ("rule", reference.rule_id)
        else:
            raise ValueError(f"{field_name} contains an invalid rule selection")
        if isinstance(reference, RuleReference):
            from vibeflow.core.rules.fingerprint import value_fingerprint
            key = (*key, value_fingerprint(reference.params))
        if key in seen:
            raise ValueError(f"{field_name} contains duplicate resource '{key[1]}'")
        seen.add(key)
        result.append(reference)
    return tuple(result)


def selection_data(value):
    return None if value is None else [item.to_dict() if isinstance(item, RuleReference) else item for item in value]


@dataclass(frozen=True)
class RuleSelection:
    references: tuple
    source: str
    origin: str
    replaced: tuple = ()

    def to_dict(self):
        return {"references": selection_data(self.references), "source": self.source,
                "origin": self.origin, "replaced": selection_data(self.replaced)}
