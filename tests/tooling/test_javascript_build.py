"""Import-boundary gates for workspace-aware JavaScript AOT Tooling."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def test_importing_project_tooling_does_not_load_removed_aot_package() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(SOURCE_ROOT), environment.get("PYTHONPATH", ""))
        if part
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
import vibeflow.tooling.application.javascript_build
loaded = sorted(
    name for name in sys.modules
    if name == "vibeflow.aot" or name.startswith("vibeflow.aot.")
)
assert loaded == [], loaded
""",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
