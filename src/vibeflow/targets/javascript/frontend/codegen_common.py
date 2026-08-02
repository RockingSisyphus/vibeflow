from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.emission_protocol import EmissionWorkflow


@dataclass(frozen=True)
class WorkflowCode:
    workflow: EmissionWorkflow
    payload: Mapping[str, Any]
    index: int
    metadata_name: str
    function_name: str
    node_names: Mapping[str, str]
    activate_names: Mapping[str, str]
    execute_names: Mapping[str, str]
    children: Mapping[str, "WorkflowCode"]


def edge_identity(source: str, target: str) -> str:
    return f"{source}\0{target}"


def js(value: object) -> str:
    """Emit a JSON value without object-literal prototype special cases."""

    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if isinstance(value, (dict, list)):
        return f"JSON.parse({json.dumps(canonical, ensure_ascii=False)})"
    return canonical


def constant(name: str, value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        f"const {name} = Object.freeze(JSON.parse("
        f"{json.dumps(canonical, ensure_ascii=False)}));"
    )


__all__ = ["WorkflowCode", "constant", "edge_identity", "js"]
