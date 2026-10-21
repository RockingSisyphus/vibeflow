"""Extracted distribution checks use the same project governance as source commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from distribution.build import build_distribution
from tests.tooling.test_shared_resource_execution import shared_project


@pytest.fixture(scope="module")
def distribution_seed(tmp_path_factory):
    return build_distribution(tmp_path_factory.mktemp("quality-workspace-seed") / "distribution", run_self_check=False)


@pytest.fixture
def workspace_case(tmp_path, distribution_seed):
    case = tmp_path / "workspace"
    shutil.copytree(distribution_seed, case)
    for name in ("python_project", "javascript_project"):
        shutil.rmtree(case / name)
    shared_project(case)
    return case


def _cli(case, *args, source_kernel=False):
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE":"1"}
    environment.pop("PYTHONPATH", None)
    if source_kernel:
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "src")
    command = [sys.executable, "-B", *( ["-m", "vibeflow"] if source_kernel else ["run.py"]), *args]
    result = subprocess.run(command, cwd=case, env=environment, capture_output=True, text=True)
    assert result.stdout.strip(), result.stderr
    return result.returncode, json.loads(result.stdout)


@pytest.mark.parametrize("source_kernel", [False, True])
def test_quality_keeps_shared_resources_and_all_registered_roots(workspace_case, source_kernel):
    code, payload = _cli(workspace_case, "quality-check", "--path", "desktop", "--json", source_kernel=source_kernel)
    assert code == 0, payload
    assert {item["root"] for item in payload["reports"]} == {"desktop", "backend"}
    assert not payload["errors"]
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    architecture = load_raw_config_document(workspace_case / "PROJECT_ARCHITECTURE.jsonc").data
    assert architecture


def test_local_build_ignores_sibling_but_full_quality_reports_damaged_workflow(workspace_case):
    case = workspace_case
    (case / "backend/configs/broken.jsonc").write_text('{"pipeline":')
    code, selected = _cli(case, "validate", "--config", "desktop/configs/main.jsonc", "--json")
    assert code == 0, selected
    code, full = _cli(case, "quality-check", "--path", "desktop", "--json")
    assert code == 1 and full["status"] == "FAIL", full
    assert any(item["root_id"] == "backend" for item in full["errors"])
    assert any(item["rule_id"] == "PROJECT.USAGE.INCOMPLETE" for item in full["errors"])


def test_root_rule_parameters_are_honored_by_packaged_validate_and_quality(workspace_case):
    case = workspace_case
    (case / "desktop/root_rules.jsonc").write_text(json.dumps({"rulesets":[{"rule_id":"vibeflow.root.files"}],
        "rule_params":{"vibeflow.root.files":{"max_file_lines":1}}}))
    for args in (("validate","--config","desktop/configs/main.jsonc"),("quality-check","--path","desktop")):
        code, payload = _cli(case, *args, "--json")
        assert code == 1, payload
        assert any(item["rule_id"] == "QUALITY.FILE.MAX_LINES" for item in payload["errors"])


def test_empty_optional_root_rules_do_not_skip_workflow_validation(workspace_case):
    case = workspace_case
    (case / "desktop/root_rules.jsonc").write_text('{"rulesets":[]}')
    config = case / "desktop/configs/main.jsonc"
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][0]["definition_id"] = "missing.node"
    config.write_text(json.dumps(data))
    code, payload = _cli(case,"quality-check","--path","desktop","--json")
    assert code == 1 and payload["status"] == "FAIL", payload
    assert any(item["root"] == "desktop" and item["status"] in {"FAIL","ERROR"} for item in payload["reports"])


@pytest.mark.parametrize("selected", ["desktop/nodes", "desktop/nodes/local.py"])
def test_quality_path_locates_project_without_source_only_bypass(workspace_case, selected):
    code, payload = _cli(workspace_case,"quality-check","--path",selected,"--json")
    assert code == 0, payload
    assert len(payload["reports"]) == 2


def test_missing_project_metadata_is_rejected_in_extracted_distribution(workspace_case):
    (workspace_case / "vibeflow_config.jsonc").unlink()
    code, payload = _cli(workspace_case,"quality-check","--path","desktop","--json")
    assert code == 1 and payload["code"] in {"WORKSPACE.CONFIG.MISSING","WORKSPACE.ROOT.UNREGISTERED"}, payload
