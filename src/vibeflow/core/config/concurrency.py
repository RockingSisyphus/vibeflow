"""Node-call scheduling configuration, separate from business parameters."""

from __future__ import annotations

from typing import Mapping

from .node import NodeConfigError, NodeConfigSpec, merge_node_config

DEFAULT_MAX_CONCURRENCY = 8
MAX_CONCURRENCY = "max_concurrency"


def dispatch_limit(config: Mapping[str, object]) -> int:
    value = config.get(MAX_CONCURRENCY, DEFAULT_MAX_CONCURRENCY)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise NodeConfigError("max_concurrency must be a positive integer")
    return value


def business_config(config: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in config.items() if key != MAX_CONCURRENCY}


def scheduling_config(config: Mapping[str, object]) -> dict[str, object]:
    dispatch_limit(config)
    return {MAX_CONCURRENCY: config[MAX_CONCURRENCY]} if MAX_CONCURRENCY in config else {}


def merge_call_config(
    spec: NodeConfigSpec,
    overrides: Mapping[str, object] | None,
) -> dict[str, object]:
    """Use the normal contract checker after extracting scheduler-owned config."""
    if MAX_CONCURRENCY in spec.schema:
        raise NodeConfigError("max_concurrency is reserved for node-call scheduling")
    if overrides is None or not isinstance(overrides, Mapping):
        return merge_node_config(spec, overrides)
    control = scheduling_config(overrides)
    return {**merge_node_config(spec, business_config(overrides)), **control}
