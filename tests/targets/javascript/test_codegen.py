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
RESOURCE_SHA256 = {'plugin_abi.d.ts': '1e3536feb02310d31f5f58cd95ce57f40d6f1c5814651107655df600739f08cb',
 'plugin_worker.mjs': '1c424fdb2eac74309c748cd0ba7c5afc9039dfd509cf1e385b150317d190b698',
 'rule_abi.d.ts': 'aaeba26699c078d6340b0e243cbe0f3e7fc53eea167956e99f85155f2574f2bb',
 'runtime_helpers.mjs': '77747ef8c71c76054639bedcb4852836ec72920ec9f3f88c09dcbdd1bc3b1bcd',
 'sdk.d.ts': '2095b92ce510f2596bed8a269ab5d424a719597510139b047be8b1582a06bbf6',
 'sdk.mjs': 'e6a93d5f5cf5e2af4e7a1c0295bc29ee445ce249abdc8f499b46c51b806ae728',
 'sdk_loader.mjs': 'd9a5f18235a5d881fc0abff6683887c0400c18e621f041bbfbdae16df596d2d9',
 'toolchain_driver.mjs': 'de6b73fe8ed46d375fa9c1c85df63fde616de3ca70aab36dbb6de659434922c6'}


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
