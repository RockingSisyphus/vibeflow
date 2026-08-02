"""Python Target Context behavior and import-boundary gates."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import vibeflow.targets.python.project.context as target_context


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_context_container_and_error_contract() -> None:
    context = target_context.Context({"nested.value": 3})
    assert context.to_dict() == {"nested": {"value": 3}}
    assert str(target_context.ContextKeyError("nested.missing")) == (
        "missing context key: nested.missing"
    )


def test_context_json_snapshot_preserves_path_conversion_semantics(
    tmp_path: Path,
) -> None:
    context = target_context.Context(
        {
            "root": tmp_path,
            "nested.path": tmp_path / "child",
            "paths": (Path("relative"), Path("other")),
        }
    )

    assert context.to_dict()["root"] == tmp_path
    assert context.json_snapshot() == {
        "root": str(tmp_path),
        "nested": {"path": str(tmp_path / "child")},
        "paths": ["relative", "other"],
    }
    assert list(context.iter_flat_items()) == [
        ("root", tmp_path),
        ("nested.path", tmp_path / "child"),
        ("paths", (Path("relative"), Path("other"))),
    ]


def test_context_target_and_neutral_entrypoints_keep_import_boundaries() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.python.project.context

forbidden = (
    "vibeflow.runtime",
    "vibeflow.tooling",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert loaded == [], loaded
"""
    )
    _run_isolated(
        """
import sys
import vibeflow
import vibeflow.core
import vibeflow.block_compiler

loaded = sorted(
    name
    for name in sys.modules
    if name == "vibeflow.targets" or name.startswith("vibeflow.targets.")
)
assert loaded == [], loaded
"""
    )
