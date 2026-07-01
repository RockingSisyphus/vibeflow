from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


_MISSING = object()


@dataclass
class ContextKeyError(KeyError):
    key: str

    def __str__(self) -> str:
        return f"missing context key: {self.key}"


class Context:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = {}
        for key, value in (initial or {}).items():
            if "." in str(key):
                self.set(str(key), deepcopy(value))
            else:
                self._data[str(key)] = deepcopy(value)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def exists(self, key: str) -> bool:
        try:
            self.get(key)
            return True
        except ContextKeyError:
            return False

    def require(self, keys: str | Iterable[str]) -> None:
        if isinstance(keys, str):
            keys = (keys,)
        for key in keys:
            if not self.exists(key):
                raise ContextKeyError(str(key))

    def get(self, key: str, default: Any = _MISSING) -> Any:
        parts = _split_key(key)
        cur: Any = self._data
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                if default is not _MISSING:
                    return default
                raise ContextKeyError(key)
            cur = cur[part]
        return cur

    def set(self, key: str, value: Any) -> None:
        parts = _split_key(key)
        cur = self._data
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def update_flat(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def iter_flat_items(self) -> Iterator[tuple[str, Any]]:
        yield from _iter_flat(self._data, prefix="")

    def json_snapshot(self) -> dict[str, Any]:
        return _json_safe(self._data)


def _split_key(key: str) -> list[str]:
    text = str(key).strip()
    if not text:
        raise ValueError("context key cannot be empty")
    return [part for part in text.split(".") if part]


def _iter_flat(value: dict[str, Any], *, prefix: str) -> Iterator[tuple[str, Any]]:
    for key, item in value.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            yield from _iter_flat(item, prefix=full)
        else:
            yield full, item


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    return repr(value)
