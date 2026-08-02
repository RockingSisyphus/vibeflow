"""Compatibility adapter for language-neutral configuration scopes."""

from __future__ import annotations

from typing import Mapping

from vibeflow.core.config.scope import (
    ALLOW_CONFIG_OVERRIDE_FIELD,
    CONFIG_VALUES_FIELD,
    OVERRIDE_CHILD_CONFIG_FIELD,
    SCOPED_CONFIG_RESERVED_FIELDS,
    VALUES_FIELD,
    ConfigBindingError,
    ConfigScope,
    attach_global_config,
    config_override_conflicts,
    effective_node_params,
    merge_config_scopes,
    nested_node_config_overrides,
    node_invocation_scope,
    normalize_config_scope,
    normalize_node_config_overrides as _normalize_node_config_overrides,
    scoped_node_params,
)
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError


def normalize_node_config_overrides(
    value: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    try:
        return _normalize_node_config_overrides(value)
    except ConfigBindingError as exc:
        raise PipelineRuntimeError(str(exc)) from exc


__all__ = [
    "ALLOW_CONFIG_OVERRIDE_FIELD",
    "CONFIG_VALUES_FIELD",
    "ConfigScope",
    "OVERRIDE_CHILD_CONFIG_FIELD",
    "SCOPED_CONFIG_RESERVED_FIELDS",
    "VALUES_FIELD",
    "attach_global_config",
    "config_override_conflicts",
    "effective_node_params",
    "merge_config_scopes",
    "nested_node_config_overrides",
    "node_invocation_scope",
    "normalize_config_scope",
    "normalize_node_config_overrides",
    "scoped_node_params",
]
