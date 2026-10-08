"""Public loaders and commands share the retired project Host contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibeflow.tooling.application.cli import main
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.workspace_loader import (
    load_project_target,
    load_project_workspace,
    load_workspace_config,
)


@pytest.mark.parametrize("old_hosts", [[], ["old.host"], None])
def test_retired_project_host_field_is_rejected_by_loaders_preview_and_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], old_hosts: object,
) -> None:
    project = tmp_path / "vibeflow_project.jsonc"
    project.write_text(json.dumps({
        "project_target": "javascript", "javascript": {"host_extensions": old_hosts},
    }), encoding="utf-8")
    workspace = tmp_path / "vibeflow_config.jsonc"
    workspace.write_text(json.dumps({"roots": [{"id": "main", "path": "."}]}), encoding="utf-8")
    workflow = tmp_path / "workflow.jsonc"
    workflow.write_text(json.dumps({"rulesets": [], "host_extensions": [], "pipeline": {"nodes": [{
        "id": "input", "type_used": "vibeflow.io", "display_name": "Input",
        "description": "Receive native input", "requires": [],
        "provides": [{"key": "data.in", "type": "data.in", "display_name": "Input data"}],
        "io": {"operation": "receive", "port": "in"},
    }]}}), encoding="utf-8")
    expected = "javascript.host_extensions was removed; select host_extensions in the workflow"
    for loader, path in (
        (load_project_target, project),
        (load_project_workspace, project),
        (load_workspace_config, workspace),
    ):
        with pytest.raises(WorkspaceConfigError) as captured:
            loader(path)
        assert captured.value.rule_id == "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT"
        assert captured.value.message == expected
        assert captured.value.source_location == {
            "path": str(project.resolve()), "field": "javascript.host_extensions",
        }

    for command in ("review-rules", "validate"):
        for scope in ([], ["--workspace", str(workspace)]):
            assert main([command, "--config", str(workflow), "--json", *scope]) == 1
            payload = json.loads(capsys.readouterr().out)
            assert payload["status"] == "ERROR"
            assert payload["code"] == "WORKSPACE.PROJECT_CONFIG.JAVASCRIPT"
            assert payload["error"] == expected
