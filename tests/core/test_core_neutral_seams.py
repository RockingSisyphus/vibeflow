"""Core model and adapter boundary tests."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.core.config.scope import ConfigBindingError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def test_runtime_config_adapter_preserves_error_contract() -> None:
    from vibeflow.targets.python.runtime.config import normalize_node_config_overrides
    from vibeflow.targets.python.runtime.errors import PipelineRuntimeError

    with pytest.raises(
        PipelineRuntimeError,
        match=(
            r"^Pipeline runtime error: node config override for 'bad' "
            r"must be an object$"
        ),
    ):
        normalize_node_config_overrides({"bad": 1})  # type: ignore[dict-item]


def test_core_config_binding_uses_neutral_error() -> None:
    from vibeflow.core.config.scope import normalize_node_config_overrides

    with pytest.raises(
        ConfigBindingError,
        match=r"^node config override for 'bad' must be an object$",
    ):
        normalize_node_config_overrides({"bad": 1})  # type: ignore[dict-item]


def test_importing_core_config_does_not_load_outer_layers() -> None:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(SOURCE_ROOT), current_pythonpath) if item
    )
    source = """
import json
import sys
import vibeflow.core.config.scope
import vibeflow.core.findings
import vibeflow.core.config.node
import vibeflow.core.nodeset_dependencies

forbidden = (
    'vibeflow.aot',
    'vibeflow.graph_config',
    'vibeflow.health',
    'vibeflow.targets.python.project.node_config',
    'vibeflow.runtime',
    'vibeflow.targets',
    'vibeflow.tooling',
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden)
)
print(json.dumps(loaded))
"""
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "[]"
