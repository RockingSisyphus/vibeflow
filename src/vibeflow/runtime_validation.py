from __future__ import annotations

import json
from typing import Any, Mapping

from .node import NodeContract
from .runtime_errors import PipelineRuntimeError


def assert_runtime_output_snapshot(value: Any, *, contract: object, node_name: str, key: str) -> None:
    if _output_allows_opaque_snapshot(contract, key):
        return
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PipelineRuntimeError(f"node '{node_name}' output '{key}' is not JSON snapshot serializable: {exc}") from exc


def _output_allows_opaque_snapshot(contract: object, key: str) -> bool:
    if not isinstance(contract, NodeContract):
        return False
    schema = contract.output_schema.get(key)
    return isinstance(schema, Mapping) and schema.get("snapshot") == "opaque"
