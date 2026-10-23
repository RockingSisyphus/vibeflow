"""Saved builtin references stay stable across checkout and installed kernels."""
from pathlib import Path

from vibeflow.tooling.presentation import portable_paths as module


def test_saved_paths_include_kernel_project_and_cross_root_references(tmp_path):
    kernel = Path(module.__file__).resolve().parents[2]
    project, shared = tmp_path / "project", tmp_path / "shared"
    document = {"builtin": {"source": str(kernel / "targets/shared/rule_support/plugin.py")},
                "business": str(project / "nodes/add.py"), "dependency": str(shared / "math.py"),
                "external": str(tmp_path / "external.py"), "values": [1, None]}
    assert module.portable_paths(document, roots={"project": project, "shared": shared}, primary_root=project) == {
        "builtin": {"source": "@kernel/targets/shared/rule_support/plugin.py"},
        "business": "nodes/add.py", "dependency": "@shared/math.py",
        "external": str(tmp_path / "external.py"), "values": [1, None]}
