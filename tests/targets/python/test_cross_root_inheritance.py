"""Inherited source checks must not depend on the consuming workflow root."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests/fixtures/python/cross_root_inheritance"


def invoke(work, *args):
    result = subprocess.run(
        [sys.executable, "-B", "-m", "vibeflow", *args], cwd=work,
        env={**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True,
    )
    return result


@pytest.mark.parametrize("variant", ["relative", "qualified"])
@pytest.mark.parametrize("root", ["vibetrain", "task"])
@pytest.mark.parametrize("violation", ["", "signature", "effect", "input_write"])
def test_inherited_workflow(tmp_path, variant, root, violation):
    work = tmp_path / "project"
    shutil.copytree(FIXTURE, work)
    node = work / "vibetrain/nodes/workflow_nodes.py"
    if variant == "relative":
        node.write_text(node.read_text().replace(
            "from vibetrain.base_lib.core import ProcessBase", "from ..base_lib.core import ProcessBase"))
    parent = work / "vibetrain/base_lib/core.py"
    text = parent.read_text()
    if violation == "signature":
        text = text.replace("self, inputs, params", "self, inputs")
    elif violation == "effect":
        text = text.replace("        return", '        print("forbidden")\n        return')
    elif violation == "input_write":
        text = text.replace("        return", '        inputs["payload.internal"] = {}\n        return')
    parent.write_text(text)
    config = f"{root}/configs/main.jsonc"
    checked = invoke(work, "validate", "--config", config)
    output = checked.stdout + checked.stderr
    if violation:
        assert checked.returncode != 0, output
        expected = {"signature": "NODE.CONTRACT.RUN_PURE_SIGNATURE",
                    "effect": "NODE.EFFECT.CALL_FORBIDDEN", "input_write": "NODE.PURITY.INPUT_MUTATION"}[violation]
        assert expected in output, output
        assert "NODE.CONTRACT.MISSING_RUN_PURE" not in output, output
        assert "RULE.SOURCE.UNAVAILABLE" not in output, output
        return
    assert checked.returncode == 0, output
    # The supplied fixture only covers validate; review additionally requires registration.
    (work / root / "vibeflow_project.jsonc").write_text(json.dumps({
        "project_target": "python", "architecture": {"documents": [
            {"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"}]}}))
    for command, extra in (
        ("review", ["--workspace", str(work / "vibeflow_config.jsonc")]),
        ("run", ["--input", str(work / "task/probe_input.json"), "--run-root", str(tmp_path / "runs")]),
        ("build", ["--workspace", str(work / "vibeflow_config.jsonc"), "--out-dir", str(tmp_path / "bundle")]),
    ):
        result = invoke(work, command, "--config", config, *extra)
        assert result.returncode == 0, result.stdout + result.stderr
    shutil.copy2(work / "task/probe_input.json", tmp_path / "input.json")
    shutil.rmtree(work)
    result = subprocess.run([sys.executable, "-B", str(tmp_path / "bundle/run.py"), "run",
        "--input", str(tmp_path / "input.json"), "--run-root", str(tmp_path / "aot-runs")],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("statement", ["from ..base_lib.core import Parent", "from provider.base_lib.core import Parent"])
def test_parent_resolution_uses_physical_files_and_visible_import_roots(statement):
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context
    path = "/project/provider/nodes/child.py"
    files = [
        PythonSourceFile.parse(path, "nodes.child", statement + "\nclass Child(Parent): pass\n"),
        PythonSourceFile.parse("/project/provider/base_lib/core.py", "base_lib.core",
            "class Parent:\n    def run_pure(self, inputs, params): return {}\n"),
        PythonSourceFile.parse("/project/consumer/base_lib/core.py", "base_lib.core",
            "class Parent:\n    def unrelated(self): pass\n"),
    ]
    sources = build_python_source_context((), files, source_roots=(Path("/project/consumer"), Path("/project")))
    method = sources.class_members(sources.symbol(path, "Child"))["run_pure"]
    assert method.path == "/project/provider/base_lib/core.py"
    assert [item.path for item in sources.import_closure(path)] == [files[1].path, path]
