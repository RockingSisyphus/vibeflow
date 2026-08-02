"""Isolation and resource gates for JavaScript Target code generation."""

from __future__ import annotations

import ast
from hashlib import sha256
from importlib.resources import files
import os
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"
TARGET_ROOT = SOURCE_ROOT / "vibeflow" / "targets" / "javascript"
FRONTEND_ROOT = TARGET_ROOT / "frontend"

RESOURCE_SHA256 = {
    "plugin_abi.d.ts": (
        "20b4ee4f6a69c6dcdbde0d72a4b5a4edb1d01015b3a39e1f70b37ad814201ddf"
    ),
    "plugin_worker.mjs": (
        "4a2e92555a7b761517ad141e0cf5068af01e4fde8b56751fcae7ce2bed2e918f"
    ),
    "runtime_helpers.mjs": (
        "ea5692cc46b40f8b1f04ace8e8068684e311cb5019e13e4338a96d837a1b3cde"
    ),
    "toolchain_driver.mjs": (
        "ffe86e7fde3438415a3c4a9626d8807d4029cf79143e6f35823f6fa4493c1f16"
    ),
}


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


def test_codegen_target_import_does_not_load_removed_or_python_layers() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.javascript.frontend.emitter

forbidden = (
    "vibeflow.aot",
    "vibeflow.targets.python",
    "vibeflow.tooling",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert loaded == [], loaded
assert "vibeflow.targets.javascript.frontend.codegen_generator" in sys.modules
assert "vibeflow.targets.javascript.frontend.templates" in sys.modules
"""
    )


@pytest.mark.parametrize("name", tuple(RESOURCE_SHA256))
def test_target_resources_match_frozen_hashes(name: str) -> None:
    canonical = files("vibeflow.targets.javascript.resources").joinpath(
        name
    ).read_bytes()

    assert sha256(canonical).hexdigest() == RESOURCE_SHA256[name]


def test_target_resource_api_is_closed_and_templates_use_canonical_runtime() -> None:
    from vibeflow.targets.javascript import resources
    from vibeflow.targets.javascript.frontend.templates import RUNTIME_SOURCE

    assert resources.RESOURCE_NAMES == frozenset(RESOURCE_SHA256)
    assert RUNTIME_SOURCE == resources.read_text("runtime_helpers.mjs").strip()
    with pytest.raises(ValueError, match="unknown JavaScript Target resource"):
        resources.resource("../runtime_helpers.mjs")


def test_codegen_modules_import_only_allowed_layers_or_stdlib() -> None:
    paths = (
        FRONTEND_ROOT / "emitter.py",
        FRONTEND_ROOT / "templates.py",
        FRONTEND_ROOT / "codegen_common.py",
        FRONTEND_ROOT / "codegen_generator.py",
        FRONTEND_ROOT / "codegen_nodes.py",
        FRONTEND_ROOT / "codegen_scheduler.py",
        TARGET_ROOT / "resources/__init__.py",
    )
    allowed_vibeflow = (
        "vibeflow.targets.javascript",
        "vibeflow.block_compiler",
        "vibeflow.core",
    )
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = (node.module or "",)
            for name in names:
                root = name.partition(".")[0]
                if name == "__future__" or root in sys.stdlib_module_names:
                    continue
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_vibeflow
                ):
                    continue
                violations.append(f"{path.name}:{node.lineno}:{name}")

    assert violations == []


def test_wheel_package_data_includes_canonical_resources_only() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"targets/javascript/resources/*.mjs"' in pyproject
    assert '"aot/resources/*.mjs"' not in pyproject
