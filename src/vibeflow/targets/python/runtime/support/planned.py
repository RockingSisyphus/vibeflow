"""Filesystem and dynamic-loading helpers for Python planned stubs."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from vibeflow.core.planned import validate_stub_module_ref
from vibeflow.targets.python.project.planned import signature_is_run_stub


def resolve_stub_module_path(
    stub_module: str,
    project_root: str | Path | None,
) -> Path:
    root = Path(project_root or Path.cwd()).resolve()
    path_error = validate_stub_module_ref(stub_module)
    if path_error:
        raise ValueError(f"stub_module {path_error}: {stub_module}")
    candidate = (root / stub_module.replace("\\", "/")).resolve()
    parts = PurePosixPath(stub_module.replace("\\", "/")).parts
    allowed_root = (
        (root / "project" / "stubs").resolve()
        if parts[:2] == ("project", "stubs")
        else (root / "stubs").resolve()
    )
    if not _is_relative_to(candidate, allowed_root):
        raise ValueError(
            f"stub_module must resolve under {allowed_root}: {stub_module}"
        )
    return candidate


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_stub_callable(
    path: Path,
) -> Callable[[Mapping[str, object], Mapping[str, object]], Mapping[str, object]]:
    module_name = f"_vibeflow_planned_stub_{hash_file(path)[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load planned stub module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_stub = getattr(module, "run_stub", None)
    if not callable(run_stub):
        raise AttributeError(
            "planned stub module must define run_stub(inputs, params): "
            f"{path}"
        )
    return run_stub


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "hash_file",
    "load_stub_callable",
    "resolve_stub_module_path",
    "signature_is_run_stub",
]
