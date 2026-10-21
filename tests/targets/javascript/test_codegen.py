"""JavaScript Target code generation and published resource interfaces."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"
TARGET_ROOT = SOURCE_ROOT / "vibeflow" / "targets" / "javascript"
FRONTEND_ROOT = TARGET_ROOT / "frontend"

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
"""
    )


def test_target_resource_api_rejects_unknown_resource_paths() -> None:
    from vibeflow.targets.javascript import resources
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


def test_published_sdk_supports_node_declarations_and_types(tmp_path) -> None:
    import json
    from distribution.build import _copy_javascript_sdk

    _copy_javascript_sdk(tmp_path)
    sdk = tmp_path / "kernel/javascript/sdk.mjs"
    program = f'''
import {{strict as assert}} from "node:assert";
import {{defineNode, definePlugin, defineNodeType}} from {json.dumps(sdk.as_uri())};
const node = defineNode({{
  node_type:"vibeflow.node", id: "sample", contract: {{}},
  __origin: {{path: "/example/plugin.mjs", symbol: "sample"}},
  run(inputs) {{return {{value: inputs.value + 1}};}}
}});
assert.deepEqual(node.run({{value: 4}}), {{value: 5}});
assert.equal(node.descriptor.flow_kind, "process");
assert.equal(node.descriptor.display_name, "sample");
assert.equal(node.descriptor.implementations[0].source.export, "sample.run");
assert.equal(definePlugin({{id:"with-node",resources:[node]}}).resources.length,1);
const plugin=definePlugin({{id:"example",resources:[defineNodeType({{id:"shell"}})]}});
assert.equal(plugin.resources[0].descriptor.kind,"node_type");
'''
    result = subprocess.run(["node", "--input-type=module", "--eval", program],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr

    consumer = tmp_path / "consumer.ts"
    consumer.write_text('''import {defineNode, type NodeRunContext} from "./kernel/javascript/sdk";
const node = defineNode({"node_type":"vibeflow.node",id: "sample", contract: {},
    run(inputs: {value: number}, params: {}, context: NodeRunContext) {
        context.trace("sample", {value: inputs.value});
        return {value: inputs.value + 1};
    }});
node.run!({value: 4}, {}, {capabilities: {}, trace() {}, updateInfo() {}});
''')
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    result = subprocess.run([str(toolchain / "node_modules/.bin/tsc"),
                             "--noEmit", "--strict", "--target", "ES2022",
                             "--module", "ES2022", "--moduleResolution", "bundler", str(consumer)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
