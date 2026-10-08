from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.fixtures.support.declarations import write_node_plugin
from tests.fixtures.support.plugins import resource, append_resource, resource_declarations, write_plugin
from vibeflow.tooling.application.cli import main
from vibeflow.tooling.application.rule_review import effective_rule_plans, rule_plans_mermaid


def _project(tmp_path):
    selection = write_node_plugin(tmp_path, [("test.seed", "SeedNode", {}, {})])
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({
        "project_target": "python"}))
    # Neither implementation nor arbitrary Rule code is imported by review-rules.
    marker = tmp_path / "imported"
    (tmp_path / "fixture_nodes.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\nraise RuntimeError('must not import')\n")
    config = tmp_path / "main.jsonc"
    config.write_text(json.dumps({"plugins": [selection], "rulesets": [], "pipeline": {"nodes": [{
        "id": "seed", "type_used": "test.seed", "display_name": "Seed",
        "description": "Inspect the declared rules without executing the seed."}]}}))
    return config, marker


def test_rule_review_reads_declarations_without_importing_business_code(tmp_path):
    config, marker = _project(tmp_path)
    payload = effective_rule_plans(config, node_path="seed")
    assert payload["workflow"] == []
    assert payload["nodes"][0]["rulesets"] == ["vibeflow.process"]
    assert any(call["rule_id"] == "vibeflow.no_side_effects" for call in payload["nodes"][0]["plans"][0]["calls"])
    assert not marker.exists()
    assert "vibeflow.process" in rule_plans_mermaid(payload)


def test_rule_review_cli_preserves_explicit_empty_selection(tmp_path, capsys):
    config, marker = _project(tmp_path)
    manifest = resource(tmp_path, "node", "test.seed")
    data = json.loads(manifest.read_text())
    data["rulesets"] = []
    manifest.write_text(json.dumps(data))
    assert main(["review-rules", "--config", str(config), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["nodes"][0]["constraint_state"] == "unconstrained"
    assert payload["nodes"][0]["plans"] == []
    assert not marker.exists()


def test_rule_review_rejects_unknown_call_path(tmp_path, capsys):
    config, marker = _project(tmp_path)
    assert main(["review-rules", "--config", str(config), "--node", "missing"]) == 1
    assert "unknown Node call path" in json.loads(capsys.readouterr().out)["error"]
    assert not marker.exists()


def test_rule_review_diagram_shows_origins_and_parameter_sources():
    payload = {"workflow": [{
        "ruleset_id": "project.domain",
        "calls": [{
            "id": "native/interface", "rule_id": "vibeflow.node_interface",
            "origins": ["project.domain", "vibeflow.process"],
            "params": {"allowed_methods": ['model"<forward>&']},
            "parameter_sources": {"allowed_methods": "override:$self"},
        }],
        "relations": [{"source": "$self", "target": "native/interface", "kind": "overrides"}],
    }], "nodes": []}
    diagram = rule_plans_mermaid(payload)
    assert "origin: project.domain → vibeflow.process" in diagram
    assert "source: override:$self" in diagram
    assert "allowed_methods=" in diagram
    assert r"model\u0022\u003cforward\u003e\u0026" in diagram
    assert "&quot;" not in diagram
    assert '-->|"overrides"|' in diagram


def test_rule_review_preserves_repeated_nodeset_invocation_paths_and_scope_selection(tmp_path):
    config, marker = _project(tmp_path)
    data = json.loads(config.read_text())
    seed = data["pipeline"]["nodes"][0]
    nodeset = {
        "type_key": "project.stage", "display_name": "Stage",
        "description": "One declared child, with an explicit empty scope selection.",
        "rulesets": [], "pipeline": {"nodes": [seed]},
    }
    (tmp_path / "stage.jsonc").write_text(json.dumps(nodeset))
    data["nodeset_imports"] = ["stage.jsonc"]
    data["pipeline"]["nodes"] = [
        {"id": name, "type_used": "project.stage", "flow_kind": "nodeset",
         "display_name": name, "description": "Invoke the shared definition at a distinct call path."}
        for name in ("first", "second")
    ]
    config.write_text(json.dumps(data))
    payload = effective_rule_plans(config)
    assert {item["call"] for item in payload["nodes"]} == {"first/seed", "second/seed"}
    assert [(item["call"], item["constraint_state"]) for item in payload["scopes"]] == [
        ("first", "unconstrained"), ("second", "unconstrained")]
    selected = effective_rule_plans(config, node_path="second/seed")
    assert [item["call"] for item in selected["nodes"]] == ["second/seed"]
    assert [item["call"] for item in selected["scopes"]] == ["second"]
    assert "second/seed" in rule_plans_mermaid(selected)
    assert not marker.exists()


@pytest.mark.parametrize("target,section", [("python", "runtime"), ("javascript", "javascript")])
def test_rule_review_uses_project_depth_defaults_and_preserves_local_override(tmp_path, target, section):
    config, marker = _project(tmp_path)
    project_config = tmp_path / "vibeflow_project.jsonc"
    project = json.loads(project_config.read_text())
    project.update({"project_target": target, section: {"nodeset_max_depth": 7}})
    project_config.write_text(json.dumps(project))
    append_resource(tmp_path, {
        "kind": "ruleset", "id": "example.depth",
        "calls": [{"id": "base", "ruleset_id": "vibeflow.workflow"}],
        "relations": [{"source": "$self", "target": "base/workflow", "kind": "overrides",
                       "params": {"nodeset_max_depth": 9}}],
    })
    _select_target(tmp_path, config, target)
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow", "example.depth"]
    config.write_text(json.dumps(data))
    plans = effective_rule_plans(config)["workflow"]
    assert plans[0]["calls"][0]["params"]["nodeset_max_depth"] == 7
    assert plans[1]["calls"][0]["params"]["nodeset_max_depth"] == 9
    assert not marker.exists()


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_rule_review_source_defaults_match_target_and_local_parameters(tmp_path, target):
    config, marker = _project(tmp_path)
    project_config = tmp_path / "vibeflow_project.jsonc"
    project = json.loads(project_config.read_text())
    project["project_target"] = target
    project_config.write_text(json.dumps(project))
    append_resource(tmp_path, {
        "kind": "ruleset", "id": "example.files",
        "calls": [{"id": "files", "rule_id": "vibeflow.quality.files",
                   "params": {"max_file_lines": 13}}],
    })
    _select_target(tmp_path, config, target)
    data = json.loads(config.read_text())
    data["rulesets"] = ["example.files"]
    if target == "python":
        data["policy"] = {"node_source": {"max_lines": 17}}
    config.write_text(json.dumps(data))
    payload = effective_rule_plans(config)
    defaults = payload["project_rule_defaults"]
    assert defaults["vibeflow.quality.files"]["max_file_lines"] == (17 if target == "python" else 500)
    conventions = defaults["vibeflow.quality.structure"]["structure_conventions"]
    assert conventions["source_extension"] == (".py" if target == "python" else ".ts")
    assert payload["workflow"][0]["calls"][0]["params"]["max_file_lines"] == 13
    assert not marker.exists()



def _select_target(project, config, target):
    if target != "javascript":
        return
    (project / "node_modules").symlink_to(Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) / "node_modules", target_is_directory=True)
    values = resource_declarations(project)
    for value in values:
        for implementation in value.get("implementations", []):
            implementation.update(language="typescript", targets=["node", "browser"])
            implementation["source"]["ref"] = "fixture_nodes.ts"
    selection = write_plugin(project, values, target=target, plugin_id="fixture.review")
    data = json.loads(config.read_text())
    data["plugins"] = [selection]
    config.write_text(json.dumps(data))
