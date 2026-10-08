"""Content fingerprints for internal keys without expanding shared data into JSON."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from hashlib import sha256
import json
from typing import Any


def cacheable_record_value(value: Any, _memo=None) -> bool:
    """Native typed records remain ineligible, even when their JSON would match."""
    if value is None or type(value) in {str, bool, int, float}:
        return True
    memo = {} if _memo is None else _memo
    identity = id(value)
    if identity in memo:
        return memo[identity]
    memo[identity] = False
    if isinstance(value, Mapping):
        valid = all(type(key) is str and cacheable_record_value(item, memo) for key, item in value.items())
    elif isinstance(value, tuple):
        valid = all(cacheable_record_value(item, memo) for item in value)
    else:
        valid = False
    memo[identity] = valid
    return valid


class _ContentDigest:
    def __init__(self):
        self.memo = {}
        self.active = set()
        self.projections = []

    def visit(self, value):
        if value is None or isinstance(value, (str, bool, int, float)):
            # JSON distinguishes booleans, integers, floats, and signed zero.
            return sha256(json.dumps(value, allow_nan=False).encode("utf-8")).digest()
        identity = id(value)
        if identity in self.active:
            raise ValueError("fingerprint data cannot contain cycles")
        if identity in self.memo:
            return self.memo[identity]
        self.active.add(identity)
        try:
            result = self._container(value)
            self.memo[identity] = result
            return result
        finally:
            self.active.remove(identity)

    def _container(self, value):
        if isinstance(value, Mapping):
            # Match plain()'s string-key projection and JSON sort_keys order.
            items = {str(key): item for key, item in value.items()}
            digest = sha256(b"object")
            digest.update(str(len(items)).encode("ascii"))
            for key in sorted(items):
                digest.update(self.visit(key))
                digest.update(self.visit(items[key]))
            return digest.digest()
        if isinstance(value, (tuple, list, set, frozenset)):
            items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
            digest = sha256(b"array")
            digest.update(str(len(items)).encode("ascii"))
            for item in items:
                digest.update(self.visit(item))
            return digest.digest()
        if hasattr(value, "to_dict"):
            projection = value.to_dict()
            self.projections.append(projection)
            return self.visit(projection)
        if is_dataclass(value) and not isinstance(value, type):
            projection = {field.name: getattr(value, field.name) for field in fields(value)}
            self.projections.append(projection)
            return self.visit(projection)
        opaque = f"{type(value).__module__}.{type(value).__qualname__}@{id(value)}"
        return self.visit(opaque)


def value_fingerprint(value: Any) -> str:
    """Preserve portable value semantics; sharing affects cost, not the key."""
    return _ContentDigest().visit(value).hex()


def record_inputs_fingerprint(inputs: Mapping[str, Any]) -> str | None:
    memo = {}
    if not all(cacheable_record_value(record.value, memo) for record in inputs.values()):
        return None
    return value_fingerprint({name: {"type_id": record.type_id, "value": record.value}
                              for name, record in inputs.items()})
