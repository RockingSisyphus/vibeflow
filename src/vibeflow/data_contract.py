from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


CARDINALITY_EXACTLY_ONE = "exactly_one"
CARDINALITY_OPTIONAL_ONE = "optional_one"
CARDINALITY_ALL = "all"
CARDINALITIES = frozenset({CARDINALITY_EXACTLY_ONE, CARDINALITY_OPTIONAL_ONE, CARDINALITY_ALL})

_MISSING = object()


@dataclass(frozen=True)
class DataProvider:
    key: str
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "type": self.type}


@dataclass(frozen=True)
class DataRequirement:
    type: str
    cardinality: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "cardinality": self.cardinality}


@dataclass(frozen=True)
class DataEnvelope:
    key: str
    type: str
    value: Any
    source_node: str

    def to_input(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "type": self.type,
            "value": self.value,
            "source_node": self.source_node,
        }

    def summary(self) -> dict[str, str]:
        return {"key": self.key, "type": self.type, "source_node": self.source_node}


class RunResult:
    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = {}
        for key, value in (values or {}).items():
            self.set(str(key), value)

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

    def get(self, key: str, default: Any = _MISSING) -> Any:
        parts = _split_key(key)
        cur: Any = self._data
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                if default is not _MISSING:
                    return default
                raise KeyError(f"missing result key: {key}")
            cur = cur[part]
        return cur

    def exists(self, key: str) -> bool:
        try:
            self.get(key)
            return True
        except KeyError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def json_snapshot(self) -> dict[str, Any]:
        return _json_safe(self._data)

    def iter_flat_items(self) -> Iterator[tuple[str, Any]]:
        yield from _iter_flat(self._data, prefix="")


def parse_data_providers(value: Any, *, field: str) -> tuple[DataProvider, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of provider objects")
    providers = tuple(_parse_provider(item, field=f"{field}[{index}]") for index, item in enumerate(value))
    _assert_unique((provider.key for provider in providers), field=f"{field}.key")
    return providers


def parse_data_requirements(value: Any, *, field: str) -> tuple[DataRequirement, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of requirement objects")
    requirements = tuple(_parse_requirement(item, field=f"{field}[{index}]") for index, item in enumerate(value))
    _assert_unique((requirement.type for requirement in requirements), field=f"{field}.type")
    return requirements


def provider_keys(providers: Iterable[DataProvider]) -> tuple[str, ...]:
    return tuple(provider.key for provider in providers)


def provider_types(providers: Iterable[DataProvider]) -> tuple[str, ...]:
    return tuple(provider.type for provider in providers)


def requirement_types(requirements: Iterable[DataRequirement]) -> tuple[str, ...]:
    return tuple(requirement.type for requirement in requirements)


def providers_to_dicts(providers: Iterable[DataProvider]) -> list[dict[str, str]]:
    return [provider.to_dict() for provider in providers]


def requirements_to_dicts(requirements: Iterable[DataRequirement]) -> list[dict[str, str]]:
    return [requirement.to_dict() for requirement in requirements]


def _parse_provider(item: Any, *, field: str) -> DataProvider:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with key and type")
    allowed = {"key", "type"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    key = _required_text(item.get("key"), field=f"{field}.key")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    return DataProvider(key=key, type=data_type)


def _parse_requirement(item: Any, *, field: str) -> DataRequirement:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with type and cardinality")
    allowed = {"type", "cardinality"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    cardinality = _required_text(item.get("cardinality"), field=f"{field}.cardinality")
    if cardinality not in CARDINALITIES:
        raise ValueError(f"{field}.cardinality must be one of {sorted(CARDINALITIES)}")
    return DataRequirement(type=data_type, cardinality=cardinality)


def _required_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty string")
    return text


def _assert_unique(values: Iterable[str], *, field: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{field} contains duplicate value: {value}")
        seen.add(value)


def _split_key(key: str) -> list[str]:
    text = str(key).strip()
    if not text:
        raise ValueError("result key cannot be empty")
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
    if isinstance(value, DataEnvelope):
        return _json_safe(value.to_input())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    return repr(value)
