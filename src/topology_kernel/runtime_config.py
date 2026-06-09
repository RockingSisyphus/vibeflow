from __future__ import annotations

from typing import Mapping

from .graph_config import NodeSpec
from .runtime_errors import PipelineRuntimeError


def effective_node_params(spec: NodeSpec, overrides: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    return {**dict(spec.params), **dict(overrides.get(spec.name, {}))}


def nested_node_config_overrides(
    spec: NodeSpec,
    parent_overrides: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    nested = _copy_overrides(spec.node_config_overrides)
    for path, value in parent_overrides.items():
        prefix = f"{spec.name}."
        if path.startswith(prefix):
            stripped = path.removeprefix(prefix)
            nested[stripped] = {**nested.get(stripped, {}), **dict(value)}
    return nested


def normalize_node_config_overrides(value: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key, item in value.items():
        if not isinstance(item, Mapping):
            raise PipelineRuntimeError(f"node config override for '{key}' must be an object")
        out[str(key)] = dict(item)
    return out


def _copy_overrides(value: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]:
    return {str(key): dict(item) for key, item in value.items()}
