"""Import-side-effect checks for the layered package API."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_root_import_does_not_load_runtime_targets_or_tooling() -> None:
    _run_isolated(
        """
import sys
import vibeflow

forbidden = (
    "vibeflow.runtime",
    "vibeflow.aot",
    "vibeflow.workspace",
    "vibeflow.rendering",
    "vibeflow.targets",
    "vibeflow.tooling",
)
loaded = sorted(
    module_name
    for module_name in sys.modules
    if any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in forbidden
    )
)
assert loaded == [], loaded
assert tuple(vibeflow.__all__) == ()
"""
    )


def test_core_import_does_not_load_runtime_targets_or_tooling() -> None:
    _run_isolated(
        """
import sys
import vibeflow.core

forbidden = (
    "vibeflow.runtime",
    "vibeflow.aot",
    "vibeflow.targets",
    "vibeflow.tooling",
)
loaded = sorted(
    module_name
    for module_name in sys.modules
    if any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in forbidden
    )
)
assert loaded == [], loaded
"""
    )


def test_root_package_exports_no_business_objects() -> None:
    import vibeflow

    namespace: dict[str, object] = {}
    exec("from vibeflow import *", namespace)

    assert tuple(vibeflow.__all__) == ()
    assert set(namespace) == {"__builtins__"}
