"""Boundary and behavior tests for Python source-analysis modules."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    environment = os.environ.copy()
    current = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), current) if part
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


def test_python_analysis_target_imports_do_not_load_removed_or_tooling() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.python.quality.rules.base_lib_effects
import vibeflow.targets.python.project.planned
import vibeflow.targets.python.quality.source_analysis

forbidden = sorted(
    name for name in sys.modules
    if name == "vibeflow.tooling"
    or name.startswith("vibeflow.tooling.")
    or name == "vibeflow.purity"
    or name.startswith("vibeflow.purity.")
    or name == "vibeflow.graph_config"
    or name.startswith("vibeflow.graph_config.")
)
assert forbidden == [], forbidden
"""
    )




def test_planned_file_validation_matches_source_validation(
    tmp_path: Path,
) -> None:
    from vibeflow.core.planned import PlannedBehavior
    from vibeflow.targets.python.project.planned import (
        signature_is_run_stub,
        validate_python_stub_source,
    )
    from vibeflow.targets.python.project.planned_files import validate_python_stub_file

    stub_dir = tmp_path / "project" / "stubs"
    stub_dir.mkdir(parents=True)
    path = stub_dir / "demo.py"
    source = "import subprocess\n\ndef run_stub(inputs, params):\n    return {}\n"
    path.write_text(source, encoding="utf-8")
    behavior = PlannedBehavior(
        kind="python_stub",
        stub_module="project/stubs/demo.py",
    )

    from_file = validate_python_stub_file(
        behavior,
        project_root=tmp_path,
        object_type="node",
        object_id="demo",
    )
    from_source = validate_python_stub_source(
        source,
        path=str(path),
        object_type="node",
        object_id="demo",
    )

    assert from_file == from_source
    assert {finding.rule_id for finding in from_source} == {
        "GRAPH.PLANNED.STUB_UNSAFE_IMPORT"
    }
    assert signature_is_run_stub(lambda inputs, params: {})
    assert not signature_is_run_stub(lambda inputs, params=None: {})
