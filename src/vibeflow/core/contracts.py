from __future__ import annotations

from dataclasses import dataclass, field
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
    display_name: str = field(default="", compare=False)

    def to_dict(self) -> dict[str, str]:
        payload = {"key": self.key, "type": self.type}
        if self.display_name:
            payload["display_name"] = self.display_name
        return payload


@dataclass(frozen=True)
class DataRequirement:
    type: str
    cardinality: str
    display_name: str = field(default="", compare=False)

    def to_dict(self) -> dict[str, str]:
        payload = {"type": self.type, "cardinality": self.cardinality}
        if self.display_name:
            payload["display_name"] = self.display_name
        return payload


@dataclass(frozen=True)
class PipelineInputSpec:
    """A public workflow input.

    ``required=None`` is intentionally retained for legacy Python workflows.
    AOT targets must reject that ambiguous state before emitting code.
    """

    key: str
    type: str
    display_name: str = field(default="", compare=False)
    required: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"key": self.key, "type": self.type}
        if self.display_name:
            payload["display_name"] = self.display_name
        if self.required is not None:
            payload["required"] = self.required
        return payload

    def to_provider(self) -> DataProvider:
        return DataProvider(self.key, self.type, self.display_name)


@dataclass(frozen=True)
class PipelineOutputSpec:
    """A public workflow output while preserving the internal type contract."""

    type: str
    cardinality: str
    display_name: str = field(default="", compare=False)
    alias: str = field(default="", compare=False)

    @property
    def public_name(self) -> str:
        return self.alias or self.type

    def to_dict(self) -> dict[str, str]:
        payload = {"type": self.type, "cardinality": self.cardinality}
        if self.display_name:
            payload["display_name"] = self.display_name
        if self.alias:
            payload["as"] = self.alias
        return payload

    def to_requirement(self) -> DataRequirement:
        return DataRequirement(self.type, self.cardinality, self.display_name)


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


def parse_pipeline_inputs(value: Any, *, field: str) -> tuple[PipelineInputSpec, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of pipeline input objects")
    inputs = tuple(_parse_pipeline_input(item, field=f"{field}[{index}]") for index, item in enumerate(value))
    _assert_unique((item.key for item in inputs), field=f"{field}.key")
    return inputs


def parse_pipeline_outputs(value: Any, *, field: str) -> tuple[PipelineOutputSpec, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of pipeline output objects")
    outputs = tuple(_parse_pipeline_output(item, field=f"{field}[{index}]") for index, item in enumerate(value))
    _assert_unique((item.type for item in outputs), field=f"{field}.type")
    _assert_unique((item.public_name for item in outputs), field=f"{field}.as")
    return outputs


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


def pipeline_inputs_to_dicts(inputs: Iterable[PipelineInputSpec]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in inputs]


def pipeline_outputs_to_dicts(outputs: Iterable[PipelineOutputSpec]) -> list[dict[str, str]]:
    return [item.to_dict() for item in outputs]


def _parse_provider(item: Any, *, field: str) -> DataProvider:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with key and type")
    allowed = {"key", "type", "display_name"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    key = _required_text(item.get("key"), field=f"{field}.key")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    display_name = _required_text(item.get("display_name"), field=f"{field}.display_name")
    return DataProvider(key=key, type=data_type, display_name=display_name)


def _parse_requirement(item: Any, *, field: str) -> DataRequirement:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with type and cardinality")
    allowed = {"type", "cardinality", "display_name"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    cardinality = _required_text(item.get("cardinality"), field=f"{field}.cardinality")
    if cardinality not in CARDINALITIES:
        raise ValueError(f"{field}.cardinality must be one of {sorted(CARDINALITIES)}")
    display_name = _required_text(item.get("display_name"), field=f"{field}.display_name")
    return DataRequirement(type=data_type, cardinality=cardinality, display_name=display_name)


def _parse_pipeline_input(item: Any, *, field: str) -> PipelineInputSpec:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with key and type")
    allowed = {"key", "type", "display_name", "required"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    key = _required_text(item.get("key"), field=f"{field}.key")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    display_name = _required_text(item.get("display_name"), field=f"{field}.display_name")
    required = item.get("required")
    if required is not None and not isinstance(required, bool):
        raise ValueError(f"{field}.required must be a boolean")
    return PipelineInputSpec(key=key, type=data_type, display_name=display_name, required=required)


def _parse_pipeline_output(item: Any, *, field: str) -> PipelineOutputSpec:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object with type and cardinality")
    allowed = {"type", "cardinality", "display_name", "as"}
    extra = sorted(str(key) for key in item if str(key) not in allowed)
    if extra:
        raise ValueError(f"{field} contains unknown fields: {extra}")
    data_type = _required_text(item.get("type"), field=f"{field}.type")
    cardinality = _required_text(item.get("cardinality"), field=f"{field}.cardinality")
    if cardinality not in CARDINALITIES:
        raise ValueError(f"{field}.cardinality must be one of {sorted(CARDINALITIES)}")
    display_name = _required_text(item.get("display_name"), field=f"{field}.display_name")
    alias = str(item.get("as", "") or "").strip()
    if "as" in item and not alias:
        raise ValueError(f"{field}.as must be a non-empty string")
    return PipelineOutputSpec(
        type=data_type,
        cardinality=cardinality,
        display_name=display_name,
        alias=alias,
    )


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
    return repr(value)


__all__ = [
    "CARDINALITIES",
    "CARDINALITY_ALL",
    "CARDINALITY_EXACTLY_ONE",
    "CARDINALITY_OPTIONAL_ONE",
    "DataEnvelope",
    "DataProvider",
    "DataRequirement",
    "PipelineInputSpec",
    "PipelineOutputSpec",
    "RunResult",
    "parse_data_providers",
    "parse_data_requirements",
    "parse_pipeline_inputs",
    "parse_pipeline_outputs",
    "pipeline_inputs_to_dicts",
    "pipeline_outputs_to_dicts",
    "provider_keys",
    "provider_types",
    "providers_to_dicts",
    "requirement_types",
    "requirements_to_dicts",
]
