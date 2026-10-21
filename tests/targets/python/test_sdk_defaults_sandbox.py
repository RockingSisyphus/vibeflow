"""Public SDK defaults through formal checks and native workflow execution."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tests.fixtures.python.sdk_defaults.runtime_isolation_probe import observe
from tests.fixtures.python.sdk_defaults.validate_probe import CASES, execute, write_project
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


ROOT = Path(__file__).resolve().parents[3]


def test_all_sdk_default_types_and_merge_isolation(tmp_path):
    script = ROOT / "tests/fixtures/python/sdk_defaults/default_types_probe.py"
    result = subprocess.run([sys.executable, "-B", str(script)], cwd=tmp_path,
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["summary"] == {"cases": 14, "registered": 14, "registration_failures": 0}
    for case in report["cases"]:
        assert case["status"] == "PASS", case
        assert case["descriptor_json_roundtrip"], case
        assert case["registered_config"]["default_types"] == case["native_json_control"]["default_types"], case
        assert case["registered_config"]["override_types"] == case["native_json_control"]["override_types"], case
        assert case["native_json_control"].get("default_isolation", {"status": "PASS"})["status"] == "PASS", case


@pytest.mark.parametrize("case_id,schema_type,value", CASES)
def test_formal_cli_and_actual_node_receive_native_json(tmp_path, case_id, schema_type, value):
    root = tmp_path / case_id
    write_project(root, schema_type, value)
    validation = execute(root, "validate", tmp_path)
    assert validation["status"] == "PASS", validation
    workspace = load_workspace_config(root.parent / "vibeflow_config.jsonc")
    result = run_workspace_checked(root / "workflow.jsonc", workspace=workspace, run_root=tmp_path / "runs")
    output = result.context.get("inspection")["value"]
    assert output["native_type"] == type(value).__name__
    assert output["value"] == value
    assert type(output["value"]) is type(value)


@pytest.mark.parametrize("mode", ["plan", "block", "compiled"])
@pytest.mark.parametrize("selection", ["defaults", "call_override", "runtime_override"])
def test_actual_nested_parameters_remain_isolated_across_runs(tmp_path, mode, selection):
    result = observe(tmp_path / f"{mode}.{selection}", mode, selection)
    assert result["status"] == "PASS", result
