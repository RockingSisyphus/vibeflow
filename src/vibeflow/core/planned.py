"""Portable planned-node behavior declarations.

Python stub loading and AST validation deliberately remain outside Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping


PLANNED_BEHAVIOR_BLOCKING = "blocking"
PLANNED_BEHAVIOR_TRANSPARENT = "transparent"
PLANNED_BEHAVIOR_PYTHON_STUB = "python_stub"
PLANNED_BEHAVIOR_KINDS = frozenset(
    {
        PLANNED_BEHAVIOR_BLOCKING,
        PLANNED_BEHAVIOR_TRANSPARENT,
        PLANNED_BEHAVIOR_PYTHON_STUB,
    }
)


@dataclass(frozen=True)
class PlannedBehavior:
    kind: str = PLANNED_BEHAVIOR_BLOCKING
    stub_module: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        if self.stub_module:
            payload["stub_module"] = self.stub_module
        return payload


def blocking_planned_behavior() -> PlannedBehavior:
    return PlannedBehavior()


def parse_planned_behavior(value: Any, *, field: str) -> PlannedBehavior:
    if value in (None, ""):
        return blocking_planned_behavior()
    if isinstance(value, str):
        kind = value.strip()
        if kind in {PLANNED_BEHAVIOR_BLOCKING, PLANNED_BEHAVIOR_TRANSPARENT}:
            return PlannedBehavior(kind=kind)
        raise ValueError(
            f"{field} must be 'blocking', 'transparent', or a python_stub object"
        )
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a string or object")
    kind = str(value.get("kind", "")).strip()
    if kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        raise ValueError(f"{field}.kind must be 'python_stub'")
    stub_module = str(value.get("stub_module", "")).strip()
    if not stub_module:
        raise ValueError(f"{field}.stub_module is required for python_stub")
    path_error = validate_stub_module_ref(stub_module)
    if path_error:
        raise ValueError(f"{field}.stub_module {path_error}")
    return PlannedBehavior(kind=kind, stub_module=stub_module)


def validate_stub_module_ref(value: str) -> str:
    text = str(value).strip().replace("\\", "/")
    if not text:
        return "must be a non-empty project-relative path"
    if ":" in PurePosixPath(text).parts[0]:
        return "must not use a drive-qualified path"
    path = PurePosixPath(text)
    if path.is_absolute():
        return "must not be an absolute path"
    if any(part in {"", ".", ".."} for part in path.parts):
        return "must not contain '.', '..', or empty path segments"
    if any(part.startswith(".") for part in path.parts):
        return "must not contain hidden path segments"
    if not (
        len(path.parts) >= 2
        and path.parts[0] == "stubs"
        or len(path.parts) >= 3
        and path.parts[0] == "project"
        and path.parts[1] == "stubs"
    ):
        return "must be under stubs/ or project/stubs/"
    if path.suffix != ".py":
        return "must point to a .py file"
    return ""


def planned_behavior_label(behavior: PlannedBehavior) -> str:
    return f"planned {behavior.kind}"


def planned_participates_in_flow(item: object) -> bool:
    return _status(item) != "planned" or _behavior(item).kind in {
        PLANNED_BEHAVIOR_TRANSPARENT,
        PLANNED_BEHAVIOR_PYTHON_STUB,
    }


def effective_planned_behavior(
    node: object,
    nodeset: object | None = None,
) -> PlannedBehavior:
    node_behavior = _behavior(node)
    nodeset_behavior = _behavior(nodeset)
    if _status(node) == "planned" and node_behavior.kind != PLANNED_BEHAVIOR_BLOCKING:
        return node_behavior
    if (
        nodeset is not None
        and _status(nodeset) == "planned"
        and nodeset_behavior.kind != PLANNED_BEHAVIOR_BLOCKING
    ):
        return nodeset_behavior
    if _status(node) == "planned":
        return node_behavior
    if nodeset is not None and _status(nodeset) == "planned":
        return nodeset_behavior
    return blocking_planned_behavior()


def _status(item: object | None) -> str:
    return str(getattr(item, "status", "implemented"))


def _behavior(item: object | None) -> PlannedBehavior:
    behavior = getattr(item, "planned_behavior", None)
    return (
        behavior
        if isinstance(behavior, PlannedBehavior)
        else blocking_planned_behavior()
    )


__all__ = [
    "PLANNED_BEHAVIOR_BLOCKING",
    "PLANNED_BEHAVIOR_KINDS",
    "PLANNED_BEHAVIOR_PYTHON_STUB",
    "PLANNED_BEHAVIOR_TRANSPARENT",
    "PlannedBehavior",
    "blocking_planned_behavior",
    "effective_planned_behavior",
    "parse_planned_behavior",
    "planned_behavior_label",
    "planned_participates_in_flow",
    "validate_stub_module_ref",
]
