from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from vibeflow.health.types import HealthFinding

def _resolve_paths(values: tuple[str, ...], *, base_path: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            path = base_path / path
        paths.append(str(path.resolve()))
    return tuple(dict.fromkeys(paths))

@contextmanager
def _module_search_path(module_name: str, paths: tuple[str, ...]) -> Iterator[None]:
    first = module_name.split(".", 1)[0]
    additions: list[str] = []
    for value in paths:
        path = Path(value)
        candidate = path.parent if path.name == first else path
        additions.append(str(candidate.resolve()))
    for value in reversed(tuple(dict.fromkeys(additions))):
        if value not in sys.path:
            sys.path.insert(0, value)
    try:
        yield
    finally:
        for value in additions:
            try:
                sys.path.remove(value)
            except ValueError:
                pass

def _finding(rule_id: str, message: str, object_id: str, failure_layer: str) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type=failure_layer,
        object_id=object_id,
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
    )
