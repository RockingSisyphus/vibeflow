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

# Plugin ABI v3 ships the code SDK and its binding loader.
RESOURCE_SHA256 = {'analysis_program.mjs': '3c640186cbb5b74238fa8a9822980bbdecc8295390c238722a2b1e8c518b83e5',
 'node_observation.mjs': '59da6bb0d8be799ae53dec1607c283df842cf57ec73ef153e35216400215510e',
 'plugin_abi.d.ts': '1e3536feb02310d31f5f58cd95ce57f40d6f1c5814651107655df600739f08cb',
 'plugin_worker.mjs': 'ff518a0a319a7cdd9746d959a16e4a72147279f8a2ef8c3831577ff3eec84ce6',
 'rule_abi.d.ts': '3655d61c8d22a693d16beb188f278fd18629d0267fbf6696fdb738e2b5f4f7eb',
 'runtime_helpers.mjs': '4fd27ff8fc2880c72444f24b87ff3eba4da23f3a61332c8127c94259f787c6fd',
 'sdk.d.ts': 'ff0d9556f9fc4febe2baa8930fd1bd41b4f381a09963cbc4ac06c201761ed2c0',
 'sdk.mjs': 'e90d8d02537a3af9d5592f23c1a9c296ab66da098443ea1980801a749ed062d2',
 'sdk_loader.mjs': 'c6774773501c5f4f6190baeb6d0f2bc6707da632f2035e5fd646da94edbda5c8',
 'source_ownership.mjs': '957310161d44b100c0ef78b47aa21a7a2623a225d8512a20b9330237f8a94ce7',
 'status_helpers.mjs': 'ab9bc7282b17d669ed17fe78c8c254b510abaf139762e15f5558aa0accf53c60',
 'toolchain_driver.mjs': 'ef6e021a7fcbaffe1bd6cf47a0d5181355bf17e61ced3425ac479f9acb56e657'}


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
    assert RUNTIME_SOURCE == (resources.read_text("runtime_helpers.mjs").strip() + "\n"
                              + resources.read_text("status_helpers.mjs"))
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
