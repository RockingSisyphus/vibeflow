from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json


def js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Expression:
    source: str


@dataclass(frozen=True)
class SharedValue:
    source: str


class StaticData:
    """Pool repeated immutable values without sharing node parameter objects."""

    def __init__(self):
        self.uses: Counter[str] = Counter()
        self.indices: dict[str, int] = {}

    @staticmethod
    def share(value: object) -> SharedValue:
        return SharedValue(js(value))

    def count_uses(self, value: object) -> None:
        if isinstance(value, SharedValue):
            self.uses[value.source] += 1
        elif isinstance(value, (tuple, list)):
            for item in value:
                self.count_uses(item)
        elif isinstance(value, dict):
            for item in value.values():
                self.count_uses(item)

    def write(self, value: object) -> str:
        if isinstance(value, Expression):
            return value.source
        if isinstance(value, SharedValue):
            source = value.source
            count = self.uses[source]
            ref = f"__vfData[{self.indices.get(source, len(self.indices))}]"
            if count > 1 and count * (len(source) - len(ref)) > len(source) + 1:
                self.indices.setdefault(source, len(self.indices))
                return ref
            return _safe_json(source)
        if isinstance(value, (tuple, list)):
            return "[" + ",".join(map(self.write, value)) + "]"
        if isinstance(value, dict):
            return "{" + ",".join(
                f"{'[' + js(key) + ']' if key == '__proto__' else js(key)}:{self.write(item)}"
                for key, item in value.items()
            ) + "}"
        return js(value)

    def declaration(self) -> str:
        return "const __vfData = deepFreeze([" + ",".join(map(_safe_json, self.indices)) + "]);"


def _safe_json(source: str) -> str:
    if '"__proto__":' in source:
        return f"JSON.parse({js(source)})"
    return source


def private_params(value: object) -> Expression:
    return Expression(_safe_json(js(value)))
