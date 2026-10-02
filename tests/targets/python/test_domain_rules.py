"""Executable Python domain bundle, using selected Rules and the public facts API."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import pytest

from vibeflow.tooling.application.cli import main
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "sandbox/python/domain_rules"


@pytest.fixture
def domain_project(tmp_path):
    example = tmp_path / "example"
    shutil.copytree(EXAMPLE, example)
    for name in tuple(sys.modules):
        if name == "domain_nodes" or name.startswith("domain_helpers"):
            sys.modules.pop(name)
    yield example / "vibeflow_config.jsonc", example / "project"
    for name in tuple(sys.modules):
        if name == "domain_nodes" or name.startswith("domain_helpers"):
            sys.modules.pop(name)


def _call(capsys, arguments):
    code = main(arguments)
    return code, json.loads(capsys.readouterr().out)


def _common(workspace, project):
    return ["--workspace", str(workspace), "--config", str(project / "configs/model.jsonc")]


def _evidence(payload, node_type):
    for execution in payload["info"]["rule_executions"]:
        for result in execution["results"].values():
            record = result["records"].get("evidence")
            if record and record["value"]["node_type"] == node_type:
                return record["value"]
    raise AssertionError(f"no selected domain Rule evidence for {node_type}")


def _register_architecture(project):
    path = project / "vibeflow_project.jsonc"
    data = json.loads(path.read_text())
    data["architecture"] = {"documents": [{"workflow": "configs/model.jsonc", "document": "ARCHITECTURE.jsonc"}]}
    path.write_text(json.dumps(data))


def _illegal_helper(project):
    helper = project / "domain_helpers/illegal_model.py"
    helper.write_text('"""A model definition in an ordinary transform helper."""\n'
                      'def model_forward(value):\n    return value + 1\n')
    path = project / "domain_nodes.py"
    source = path.read_text().replace("from domain_helpers.arithmetic import scale",
        "from domain_helpers.arithmetic import scale\nfrom domain_helpers.illegal_model import model_forward")
    source = source.replace('return {"result": value + params["offset"]}',
                            'return {"result": model_forward(value) + params["offset"]}')
    path.write_text(source)
    return helper


def test_category_rules_public_ast_helpers_and_actual_numerical_run(domain_project, capsys, tmp_path):
    workspace, project = domain_project
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 0, payload
    evidence = _evidence(payload, "example.model")
    assert evidence["category"] == "model_block"
    assert evidence["ast_kind"] == "ClassDef"
    assert [item["symbol"] for item in evidence["definitions"]] == ["ModelBlock.model_forward"]
    assert {"symbol": "scale", "path": str(project / "domain_helpers/arithmetic.py"),
            "owners": ["example.model"]} in evidence["helpers"]
    result = run_workspace_checked(project / "configs/model.jsonc",
        workspace=load_workspace_config(workspace), initial={"value": 3}, run_root=tmp_path / "runs", run_id="domain")
    assert result.context.get("result")["value"] == 7
    assert result.context.get("runtime.exec_order") == ("start", "model", "transform", "end")
    run_health = json.loads((result.run_dir / "health_report.json").read_text())
    assert _evidence(run_health, "example.model")["definitions"] == evidence["definitions"]


def test_category_style_and_call_override_enter_formal_review(domain_project, capsys, tmp_path, monkeypatch):
    workspace, project = domain_project
    output = tmp_path / "model.mmd"
    assert main(["export-mermaid", *_common(workspace, project), "--output", str(output)]) == 0
    assert "#cceeff" in output.read_text()
    config = project / "configs/model.jsonc"
    document = json.loads(config.read_text())
    document["pipeline"]["nodes"][1]["style"] = {"fill": "#ddeeff"}
    config.write_text(json.dumps(document))
    _register_architecture(project)
    # Rendering is an external browser boundary; the formal review still
    # compiles, generates the architecture, runs selected Rules and publishes.
    import vibeflow.tooling.application.python.presentation.mermaid.review_svg as svg
    def render(graph, compiled, target, **kwargs):
        Path(target).write_text('<svg xmlns="http://www.w3.org/2000/svg" aria-roledescription="flowchart-review-columns"><g class="review-inline-fragment"><g id="model"/></g></svg>')
    monkeypatch.setattr(svg, "render_review_columns_svg", render)
    code, payload = _call(capsys, ["review", *_common(workspace, project), "--output", str(tmp_path / "model.svg")])
    assert code == 0, payload
    assert payload["published"] is True
    from vibeflow.tooling.project.config_loader import strip_jsonc_comments
    architecture = json.loads(strip_jsonc_comments((project / "ARCHITECTURE.jsonc").read_text()))
    model = next(item for item in architecture["workflow"]["nodes"] if item["id"] == "model")
    assert architecture["node_types"]["example.model"]["info"]["category"] == "model_block"
    assert model["presentation"]["values"]["fill"] == "#ddeeff"
    assert model["presentation"]["sources"]["fill"] == "call"
    assert main(["export-mermaid", *_common(workspace, project), "--output", str(output)]) == 0
    assert "#ddeeff" in output.read_text()


@pytest.mark.parametrize("command", ["validate", "quality-check", "review", "run"])
def test_helper_model_location_reaches_every_formal_check(domain_project, capsys, tmp_path, command):
    workspace, project = domain_project
    helper = _illegal_helper(project)
    if command == "quality-check":
        arguments = [command, "--workspace", str(workspace), "--json"]
    elif command == "review":
        _register_architecture(project)
        arguments = [command, *_common(workspace, project), "--output", str(tmp_path / "invalid.svg")]
    elif command == "run":
        arguments = [command, *_common(workspace, project), "--input", str(workspace.parent / "input.json"),
                     "--run-root", str(tmp_path / "runs"), "--run-id", "invalid"]
    else:
        arguments = [command, *_common(workspace, project), "--json"]
    code, payload = _call(capsys, arguments)
    assert code == 1, payload
    if command == "quality-check":
        findings = [finding for report in payload["reports"] for finding in report["errors"]]
    elif command == "review":
        findings = payload["validation"]["errors"]
    elif command == "run":
        findings = payload["health"]["errors"]
    else:
        findings = payload["errors"]
    finding = next(item for item in findings if item["code"] == "EXAMPLE.MODEL.LOCATION")
    assert finding["definition_id"] == "example.model_definition"
    assert finding["source_location"] == {"path": str(helper), "line": 2, "column": 1}
    assert finding["details"]["ownership"] == [{"node_type": "example.transform", "relation": "helper_reference"}]
    assert finding["details"]["calls"] == [{"owner": "pipeline", "node": "transform"}]
    if command == "review":
        assert payload["published"] is False
        assert not (tmp_path / "invalid.svg").exists()
    if command == "run":
        assert not (tmp_path / "runs/invalid/output_summary.json").exists()


def test_one_block_is_a_domain_convention_and_empty_selection_is_unconstrained(domain_project, capsys):
    workspace, project = domain_project
    path = project / "domain_nodes.py"
    source = path.read_text().replace("    def run_pure(self, inputs, params):\n        value = inputs[\"example.input\"]",
        "    def model_forward(self, value, gain):\n        return value * gain\n\n"
        "    def run_pure(self, inputs, params):\n        value = inputs[\"example.input\"]")
    path.write_text(source)
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 1
    finding = next(item for item in payload["errors"] if item["code"] == "EXAMPLE.MODEL.ONE_BLOCK")
    assert finding["definition_id"] == "example.model_definition"
    assert finding["details"]["count"] == 2
    declaration = project / "bundle/nodes/model.jsonc"
    data = json.loads(declaration.read_text())
    data["rulesets"] = []
    declaration.write_text(json.dumps(data))
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 0, payload.get("source_quality", payload).get("errors", payload)
    assert payload["info"]["node_effect_scopes"]["model"] == "unconstrained"
    code, plans = _call(capsys, ["review-rules", *_common(workspace, project), "--node", "model", "--json"])
    assert code == 0
    assert plans["nodes"][0]["constraint_state"] == "unconstrained"


def test_unselected_declarations_and_unreachable_files_are_not_domain_scanned(domain_project, capsys):
    workspace, project = domain_project
    path = project / "bundle/nodes/unused.jsonc"
    data = json.loads((project / "bundle/nodes/model.jsonc").read_text())
    data["type_key"] = "example.unused"
    data["implementations"][0]["source"] = {"kind": "file", "ref": "unused/model.py", "export": "UnusedModel"}
    path.write_text(json.dumps(data))
    unused = project / "unused"
    unused.mkdir()
    (unused / "model.py").write_text("class UnusedModel:\n    def run_pure(self, inputs, params):\n        return {'feature': 1}\n")
    (unused / "unreachable.py").write_text("def model_forward(value):\n    return value\n")
    bundle = project / "bundles/domain.jsonc"
    data = json.loads(bundle.read_text()); data["resources"]["nodes"].append("../bundle/nodes/unused.jsonc")
    bundle.write_text(json.dumps(data))
    code, payload = _call(capsys, ["quality-check", "--workspace", str(workspace), "--json"])
    assert code == 0, payload["source_quality"]["errors"]
    definitions = [item for report in payload["reports"] for item in report["errors"] if item["definition_id"] == "example.model_definition"]
    assert definitions == []
    evidence = _evidence(payload["reports"][0], "example.model")
    assert not any(item["path"].endswith("unreachable.py") for item in evidence["definitions"])


def test_rule_review_does_not_import_node_or_rule_implementations(domain_project, capsys):
    workspace, project = domain_project
    node_marker, rule_marker = project / "node-imported", project / "rule-imported"
    for path, marker in ((project / "domain_nodes.py", node_marker), (project / "rules/model_definition.py", rule_marker)):
        path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\nraise RuntimeError('must not import')\n")
    code, payload = _call(capsys, ["review-rules", *_common(workspace, project), "--node", "model", "--json"])
    assert code == 0, payload
    node = payload["nodes"][0]
    assert node["rulesets"] == ["example.model_domain"]
    assert any(item["rule_id"] == "example.model_definition" for item in node["plans"][0]["calls"])
    interface = next(item for item in node["plans"][0]["calls"] if item["rule_id"] == "vibeflow.node_interface")
    assert interface["params"]["allowed_methods"] == ["model_forward"]
    assert interface["parameter_sources"]["allowed_methods"].startswith("override:")
    assert not node_marker.exists()
    assert not rule_marker.exists()
