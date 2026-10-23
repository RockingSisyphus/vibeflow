"""Real SDK declarations require Kill even when a call also has Wait."""
import json
import os
from pathlib import Path

import pytest

from tests.fixtures.support.workflow_cooperation import prepare
from vibeflow.tooling.project.workspace_loader import load_workspace_config


@pytest.mark.parametrize("language", ["python", "javascript"])
@pytest.mark.parametrize("mode, warned", [("unobserved", True), ("wait", True),
                                         ("call_and_wait", True), ("kill", False), ("background", False)])
def test_call_cleanup_warning_requires_kill_or_explicit_background(tmp_path, language, mode, warned):
    fixture = Path(__file__).resolve().parents[2] / f"sandbox/{language}/workflow_cooperation_math"
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) if language == "javascript" else None
    prepare(fixture, tmp_path, language, toolchain)
    path = tmp_path / "project/configs/a.jsonc"
    config = json.loads(path.read_text())
    config.pop("nodeset_imports", None)
    original = {node["id"]: node for node in config["pipeline"]["nodes"]}
    call = original["call"]
    if mode == "call_and_wait":
        call["definition_id"] = "example.callandwait"
    if mode == "background":
        call["config"]["allow_background"] = True
    nodes = [original["start"], call]
    if mode in {"wait", "kill"}:
        nodes.append({"id":"cleanup", "definition_id":"example."+mode,
                      "display_name":"Cleanup", "description":"Explicit completion policy",
                      **({"config":{"workflow":{"root":"cooperation","path":"configs/b.jsonc","entry":"calculate"}}} if mode == "kill" else {})})
    nodes.append(original["end"])
    config["pipeline"].update(nodes=nodes, inputs=[], outputs=[],
        edges=[[a["id"], b["id"]] for a, b in zip(nodes, nodes[1:])])
    path.write_text(json.dumps(config))
    if language == "python":
        from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
        report = validate_workspace_config_path(path, workspace=load_workspace_config(tmp_path / "vibeflow_config.jsonc"))
        assert not report.errors, report.to_dict()
        findings = report.warnings
    else:
        from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, prepare_project_build
        prepared = prepare_project_build(ProjectBuildRequest(tmp_path / "vibeflow_config.jsonc", path,
                                                            tmp_path / "artifacts/probe", "browser", "single-esm"))
        findings = prepared.rule_report.findings
    warnings = [item for item in findings if item.rule_id == "WORKFLOW.CALL.UNOBSERVED"]
    assert bool(warnings) == warned, [item.to_dict() for item in findings]
    assert all(item.severity == "warning" for item in warnings)
