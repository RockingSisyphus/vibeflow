"""Actual workflow import entrypoints reject before delayed Node execution."""
import json
from dataclasses import replace

import pytest

from tests.fixtures.support.rule_inspection import node_document
from tests.fixtures.support.plugins import write_plugin, resource
from vibeflow.tooling.application.python.project.core import build_workspace_node_registry
from vibeflow.tooling.application.python.execution import CheckedRunError
from vibeflow.tooling.application.python.runner import run_checked
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked, validate_workspace_config_path
from vibeflow.tooling.project.workspace_loader import load_project_workspace, load_workspace_config


def _project(root, *, owner="workflow", state="completed", error=False, needs_compiled=False):
    marker, observations = root / "node-imported", root / "rule-observations.jsonl"
    (root / "leaf.py").write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nclass Leaf:\n    def run_pure(self, inputs, params):\n        return {{}}\n')
    node = node_document(type_key="test.leaf", class_name="Leaf", contract={}, rulesets=[])
    node["implementations"][0]["source"]["ref"] = "leaf.py"
    (root / "plugins/code_plugin").mkdir(parents=True, exist_ok=True)
    (root / "plugins/code_plugin/domain.py").write_text(f'''import json
from pathlib import Path
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleResult
def check(context, inputs, params):
    source = context.require("source_context")
    assert source.nodes[0].descriptor.id == "test.leaf"
    assert context.require("node_definitions")[0].id == "test.leaf"
    assert len(context.require("source_quality").files) == 1
    assert "compiled" not in context.facts and not hasattr(context.require("registry"), "get")
    if params["needs_compiled"]:
        context.require("compiled")
    with Path({str(observations)!r}).open("a") as stream:
        stream.write(json.dumps({{"phase":context.phase,"path":list(context.subject["call_path"]),"nodes":[item.definition_id for item in source.nodes]}})+"\\n")
    findings = ()
    if params["error"] or params["state"] != "completed":
        findings = (HealthFinding(rule_id="TEST.DOMAIN.IMPORT", severity="error" if params["error"] else "warning",
            message="Domain import result.", source_location={{"path":source.files[0].path,"line":2}}),)
    return RuleResult(state=params["state"], findings=findings)
''')
    rule = {"kind":"rule", "id":"test.domain.import", "level":"graph", "params_schema":{"state":{"type":"string"},
        "error":{"type":"boolean"}, "needs_compiled":{"type":"boolean"}},
        "params_defaults":{"state":state,"error":error,"needs_compiled":needs_compiled},
        "implementations":[{"language":"python","source":{"kind":"file","ref":"domain.py","export":"check"}}]}
    selection = {"kind":"ruleset", "id":"test.before_bind", "calls":[
        {"id":"files","rule_id":"vibeflow.graph.source.files","params":{"warn_file_lines":1000}},
        {"id":"domain","rule_id":"test.domain.import"}],
        "entrypoints":{"import":["files","domain"],"static":[],"run":[]}}
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python",
}))
    leaf = {"id":"leaf", "definition_id":"test.leaf", "display_name":"Leaf", "description":"One delayed implementation."}
    plugin = write_plugin(root, [node, rule, selection], target="python")
    data = {"plugins":[plugin], "rulesets":[selection["id"]] if owner == "workflow" else [], "pipeline":{"nodes":[leaf]}}
    if owner != "workflow":
        child = {"type_key":"test.stage", "display_name":"Stage", "description":"The actual child scope.",
            "rulesets":[selection["id"]], "requires":[], "provides":[], "pipeline":{"nodes":[leaf]}}
        (root / "stage.jsonc").write_text(json.dumps(child))
        unused = {**child,"type_key":"test.unused","rulesets":[]}
        (root / "unused.jsonc").write_text(json.dumps(unused))
        data["nodeset_imports"] = ["stage.jsonc","unused.jsonc"]
        call = {"id":"stage", "definition_id":"test.stage", "display_name":"Stage", "description":"Call the child."}
        if owner == "loop":
            call.update(id="loop", definition_id="vibeflow.loop.while",requires=[],provides=[],
                loop={"body":"test.stage","max_iterations":1,"stop_after":1})
        data["pipeline"]["nodes"] = [call]
    workflow = root / "main.jsonc"
    workflow.write_text(json.dumps(data))
    return workflow, marker, observations


@pytest.mark.parametrize("owner", ["workflow", "nodeset", "loop"])
def test_workflow_import_file_rule_rejects_actual_closure_before_node_marker(tmp_path, owner):
    config, marker, observations = _project(tmp_path, owner=owner)
    selection = resource(tmp_path, "ruleset", "test.before_bind")
    data = json.loads(selection.read_text())
    data["calls"][0]["params"]["max_file_lines"] = 2
    selection.write_text(json.dumps(data))
    with pytest.raises(CheckedRunError) as rejected:
        run_checked(config, run_root=tmp_path / "runs", run_id="rejected")
    report = rejected.value.result.health
    finding = next(item for item in report.errors if item.code == "QUALITY.FILE.MAX_LINES")
    assert finding.details["limit"] == 2
    assert finding.details["call_path"] == (() if owner == "workflow" else ("stage" if owner == "nodeset" else "loop",))
    assert not marker.exists()
    assert report.info["rule_phase"] == "import"
    assert all(item["plan"]["entrypoint"] == "import" for item in report.info["rule_executions"])
    assert observations.exists()  # Independent, completed checks still ran with real facts.


@pytest.mark.parametrize("state", ["failed", "unavailable"])
def test_workflow_import_incomplete_warning_blocks_workspace_binding(tmp_path, state):
    config, marker, _ = _project(tmp_path, state=state)
    workspace = load_project_workspace(config)
    with pytest.raises(CheckedRunError) as rejected:
        run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs", run_id="incomplete")
    finding = next(item for item in rejected.value.result.health.errors if item.code == "RULE.EXECUTION.UNAVAILABLE")
    assert finding.details["state"] == state and finding.definition_id == "test.domain.import"
    assert not marker.exists()


def test_workflow_import_completed_error_and_missing_compiled_are_not_fake_success(tmp_path):
    config, marker, _ = _project(tmp_path, error=True)
    workspace = load_project_workspace(config)
    report = validate_workspace_config_path(config, workspace=workspace)
    assert report.status == "FAIL" and report.errors[0].definition_id == "test.domain.import"
    assert not marker.exists()
    rule_path = resource(tmp_path, "rule", "test.domain.import")
    rule = json.loads(rule_path.read_text())
    rule["params_defaults"].update(error=False,needs_compiled=True)
    rule_path.write_text(json.dumps(rule))
    report = validate_workspace_config_path(config, workspace=workspace)
    assert report.status == "FAIL" and any("compiled" in item.message for item in report.errors)
    assert not marker.exists()


@pytest.mark.parametrize("command", ["validate", "review"])
def test_formal_cli_checks_import_entrypoint_before_publication(tmp_path, capsys, command):
    from tests.fixtures.support.strict_support import cli_main as main
    config, marker, _ = _project(tmp_path, error=True)
    output = tmp_path / "review.svg"
    arguments = [command, "--config", str(config)]
    if command == "review":
        project_path = tmp_path / "vibeflow_project.jsonc"
        project = json.loads(project_path.read_text())
        project["architecture"] = {"documents":[{"workflow":"main.jsonc", "document":"ARCHITECTURE.jsonc"}]}
        project_path.write_text(json.dumps(project))
        workspace = tmp_path.parent / "vibeflow_config.jsonc"
        arguments.extend(["--workspace", str(workspace)])
    arguments.extend(["--json"] if command == "validate" else ["--output", str(output)])
    assert main(arguments) == 1
    payload = json.loads(capsys.readouterr().out)
    report = payload if command == "validate" else payload["validation"]
    assert any(item["definition_id"] == "test.domain.import" for item in report["errors"])
    if command == "review":
        assert payload["published"] is False and not output.exists()
    assert not marker.exists()


@pytest.mark.parametrize("owner", ["workflow", "nodeset", "loop"])
def test_workflow_import_completed_empty_domain_result_allows_real_execution(tmp_path, owner):
    config, marker, observations = _project(tmp_path, owner=owner)
    workspace = load_project_workspace(config)
    result = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs", run_id="allowed")
    assert result.health.status == "PASS" and marker.read_text() == "executed"
    expected = [] if owner == "workflow" else ["stage" if owner == "nodeset" else "loop"]
    assert json.loads(observations.read_text())["path"] == expected
    execution = result.health.info["rule_executions"][0]
    assert execution["results"]["domain"]["records"] == {} and execution["results"]["domain"]["state"] == "completed"


def test_repeated_nodeset_workflow_import_keeps_actual_call_paths_and_preview_defaults(tmp_path):
    from vibeflow.tooling.application.rule_review import effective_rule_plans
    config, marker, observations = _project(tmp_path, owner="nodeset")
    data = json.loads(config.read_text())
    first = data["pipeline"]["nodes"][0]
    data["pipeline"]["nodes"] = [{**first,"id":name} for name in ("first","second")]
    config.write_text(json.dumps(data))
    selection = resource(tmp_path, "ruleset", "test.before_bind")
    configured = json.loads(selection.read_text())
    configured["calls"][0]["params"]["max_file_lines"] = 25
    selection.write_text(json.dumps(configured))
    workspace = load_project_workspace(config)
    preview = effective_rule_plans(config, workspace=workspace, phase="import")
    plans = [plan for item in preview["scopes"] for plan in item["plans"]]
    assert all(next(call for call in plan["calls"] if call["rule_id"] == "vibeflow.graph.source.files")["params"]["max_file_lines"] == 25 for plan in plans)
    assert not marker.exists() and not observations.exists()
    report = validate_workspace_config_path(config, workspace=workspace)
    assert report.status == "PASS" and not marker.exists()
    assert [json.loads(line)["path"] for line in observations.read_text().splitlines()] == [["first"],["second"]]
    assert all(next(call for call in item["plan"]["calls"] if call["rule_id"] == "vibeflow.graph.source.files")["params"]["max_file_lines"] == 25 for item in report.info["rule_executions"])
