"""Real distribution CLI scenarios for root-scoped quality with sibling resources."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from distribution.build import build_distribution


@pytest.fixture(scope="module")
def distribution_seed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_distribution(
        tmp_path_factory.mktemp("quality-workspace-seed") / "distribution",
        run_self_check=False,
    )


@pytest.fixture
def workspace_case(tmp_path: Path, distribution_seed: Path) -> Path:
    case = tmp_path / "workspace"
    shutil.copytree(distribution_seed, case)
    project = case / "project"
    (case / "python_project").rename(project)
    framework = case / "framework"
    base_lib = framework / "base_lib"
    base_lib.mkdir(parents=True)
    (base_lib / "__init__.py").write_text("", encoding="utf-8")
    (base_lib / "shared_math.py").write_text(
        'def identity(value):\n    return value\n', encoding="utf-8",
    )
    (framework / "vibeflow_project.jsonc").write_text(
        json.dumps({
            "project_target": "python",
            "quality_enabled": True,
        }),
        encoding="utf-8",
    )
    (case / "vibeflow_config.jsonc").write_text(
        json.dumps({"roots": [
            {"id": "framework", "path": "framework"},
            {"id": "project", "path": "project"},
        ]}),
        encoding="utf-8",
    )
    project_config = project / "vibeflow_project.jsonc"
    data = json.loads(project_config.read_text(encoding="utf-8"))
    data.pop("architecture")
    project_config.write_text(json.dumps(data), encoding="utf-8")
    node_source = project / "nodes/workflow_nodes.py"
    source = node_source.read_text(encoding="utf-8")
    source = source.replace('from __future__ import annotations\n', 'from __future__ import annotations\nfrom base_lib.shared_math import identity\n').replace(
        '_value(inputs, "payload.internal")',
        'identity(_value(inputs, "payload.internal"))',
    )
    node_source.write_text(source, encoding="utf-8")
    # Library authorization belongs to each resource, not workflow visibility.
    node_source.write_text(source.replace("'base_libs': []", "'base_libs': ['shared_math']"), encoding="utf-8")
    (framework / "plugin.py").write_text(
        'from vibeflow.targets.python.sdk import Plugin,base_lib,SourceLocator\n'
        'library = base_lib(id="shared_math", display_name="Shared math", description="Sibling helper.", '
        'source=SourceLocator(kind="module",ref="base_lib.shared_math"),implementation_files=["base_lib/__init__.py"],rulesets=["vibeflow.base_lib"])\n'
        'plugin = Plugin(id="framework", resources=[library])\n', encoding="utf-8")
    config = project / "configs/main.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["base_lib"] = {"modules": ["shared_math"]}
    data["plugins"].append({"root":"framework","source":{"kind":"file","ref":"plugin.py"}})
    config.write_text(json.dumps(data), encoding="utf-8")
    return case


def _cli(case: Path, *args: str, source_kernel: bool = False):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if source_kernel:
        repository = Path(__file__).resolve().parents[3]
        environment["PYTHONPATH"] = str(repository / "src")
        command = [sys.executable, "-m", "vibeflow", *args]
    else:
        command = [sys.executable, "run.py", *args]
    completed = subprocess.run(
        command, cwd=case, env=environment, text=True,
        capture_output=True, check=False,
    )
    assert completed.stdout.strip(), completed.stderr
    return completed.returncode, json.loads(completed.stdout)


@pytest.mark.parametrize("entry", ["launcher-default", "launcher-explicit", "module-explicit"])
def test_root_quality_retains_sibling_base_lib_context(workspace_case: Path, entry: str) -> None:
    case = workspace_case
    workspace_args = ("--workspace", "vibeflow_config.jsonc") if entry != "launcher-default" else ()
    validate_code, validated = _cli(case, "validate", "--config", "project/configs/main.jsonc", "--json")
    command = "quality-check" if entry == "module-explicit" else "quality"
    quality_code, quality = _cli(
        case, command, "--path", "project", "--json", *workspace_args,
        source_kernel=entry == "module-explicit",
    )
    assert validate_code == 0 and validated["status"] in {"PASS", "CONCERNS"}, validated
    assert quality_code == 0 and quality["status"] in {"PASS", "CONCERNS"}, quality
    assert len(quality["reports"]) == 1
    report = quality["reports"][0]
    assert report["config"] == str(case / "project/configs/main.jsonc")
    assert report["effective_policy"]["base_lib"]["allowed_modules"] == ["base_lib.shared_math"]
    assert {root["id"] for root in report["info"]["workspace"]["roots"]} == {"framework", "project"}
    assert {item["path"] for item in quality["source_quality"]["files"]} == {
        "__init__.py", "plugins/code_plugin.py", "nodes/__init__.py", "nodes/workflow_nodes.py",
    }


def test_root_selection_does_not_scan_sibling_source_or_workflows(workspace_case: Path) -> None:
    case = workspace_case
    (case / "framework/unregistered.py").write_text("VALUE = 1\n" + "\n" * 501, encoding="utf-8")
    configs = case / "framework/configs"
    configs.mkdir()
    (configs / "invalid.jsonc").write_text(json.dumps({"pipeline": {"nodes": [{
        "id": "missing", "type_used": "missing.implementation",
        "display_name": "Missing implementation", "description": "An invalid sibling workflow.",
    }]}}), encoding="utf-8")
    code, selected = _cli(case, "quality", "--path", "project", "--json")
    assert code == 0 and selected["status"] == "PASS", selected
    assert len(selected["reports"]) == 1
    code, full = _cli(case, "quality", "--json")
    assert code == 1 and full["status"] == "FAIL", full
    assert any(item["rule_id"] == "QUALITY.FILE.MAX_LINES" for item in full["source_quality"]["errors"])
    assert len(full["reports"]) == 2
    assert any(report["status"] in {"FAIL", "ERROR"} for report in full["reports"])


def test_root_quality_preserves_real_undeclared_base_lib_error(workspace_case: Path) -> None:
    case = workspace_case
    source = case / "project/nodes/workflow_nodes.py"
    source.write_text(source.read_text(encoding="utf-8").replace(
        "        # BUSINESS CODE:",
        "        from base_lib.shared_math import identity\n        # BUSINESS CODE:",
    ), encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace("'base_libs': ['shared_math']", "'base_libs': []"), encoding="utf-8")
    config = case / "project/configs/main.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))
    data.pop("base_lib")
    config.write_text(json.dumps(data), encoding="utf-8")
    for args in (
        ("validate", "--config", "project/configs/main.jsonc", "--json"),
        ("quality", "--path", "project", "--json"),
    ):
        code, payload = _cli(case, *args)
        assert code == 1 and payload["status"] == "FAIL", payload
        report = payload.get("reports", [payload])[0]
        assert "VF_IMPORT_LAYER" in {item["rule_id"] for item in report["errors"]}


def test_root_quality_preserves_workspace_policy(workspace_case: Path) -> None:
    case = workspace_case
    workspace = case / "vibeflow_config.jsonc"
    data = json.loads(workspace.read_text(encoding="utf-8"))
    data["policy"] = {"node_source": {"max_lines": 1}}
    workspace.write_text(json.dumps(data), encoding="utf-8")
    validate_code, validated = _cli(case, "validate", "--config", "project/configs/main.jsonc", "--json")
    quality_code, quality = _cli(case, "quality", "--path", "project", "--json")
    assert validate_code == quality_code == 1
    assert validated["effective_policy"]["node_source"]["max_lines"] == 1
    assert quality["reports"][0]["effective_policy"]["node_source"]["max_lines"] == 1
    assert quality["source_quality"]["status"] == "PASS"


@pytest.mark.parametrize("selected", ["project/nodes", "project/nodes/workflow_nodes.py"])
def test_subdirectory_and_file_quality_remain_source_only(workspace_case: Path, selected: str) -> None:
    code, payload = _cli(workspace_case, "quality", "--path", selected, "--json")
    assert code == 0 and payload["status"] in {"PASS", "CONCERNS"}, payload
    assert payload["reports"] == []


def test_disabled_root_does_not_validate_workflows(workspace_case: Path) -> None:
    case = workspace_case
    config = case / "project/vibeflow_project.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["quality_enabled"] = False
    config.write_text(json.dumps(data), encoding="utf-8")
    code, payload = _cli(case, "quality", "--path", "project", "--json")
    assert code == 0 and payload["reports"] == [], payload


def test_standalone_root_without_workspace_keeps_workflow_checks(tmp_path: Path, distribution_seed: Path) -> None:
    case = tmp_path / "standalone"
    shutil.copytree(distribution_seed, case)
    (case / "vibeflow_config.jsonc").unlink()
    config = case / "python_project/vibeflow_project.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))
    data.pop("architecture")
    config.write_text(json.dumps(data), encoding="utf-8")
    code, payload = _cli(case, "quality", "--path", "python_project", "--json")
    assert code == 0 and payload["status"] == "PASS", payload
    assert len(payload["reports"]) == 1
    assert len(payload["reports"][0]["info"]["workspace"]["roots"]) == 1


def test_mixed_workspace_child_quality_retains_sibling_context(workspace_case: Path) -> None:
    case = workspace_case
    workspace = case / "vibeflow_config.jsonc"
    data = json.loads(workspace.read_text(encoding="utf-8"))
    data["roots"].append({"id": "javascript", "path": "javascript_project"})
    workspace.write_text(json.dumps(data), encoding="utf-8")
    config = case / "javascript_project/vibeflow_project.jsonc"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["quality_enabled"] = False
    config.write_text(json.dumps(data), encoding="utf-8")
    code, payload = _cli(case, "quality", "--json")
    assert code == 0 and payload["status"] == "PASS", payload
    project = next(root["report"] for root in payload["roots"] if root["id"] == "project")
    assert len(project["reports"]) == 1
    assert len(project["reports"][0]["info"]["workspace"]["roots"]) == 3
