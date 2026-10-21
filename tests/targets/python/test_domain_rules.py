"""Executable Python domain bundle, using selected Rules and the public facts API."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import pytest

from tests.fixtures.support.strict_support import cli_main as main
from tests.fixtures.support.plugins import resource, resources
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
            if record and record["value"]["definition_id"] == node_type:
                return record["value"]
    raise AssertionError(f"no selected domain Rule evidence for {node_type}")


def _register_architecture(project):
    path = project / "vibeflow_project.jsonc"
    data = json.loads(path.read_text())
    data["architecture"] = {"documents": [{"workflow": "configs/model.jsonc", "document": "ARCHITECTURE.jsonc"}]}
    path.write_text(json.dumps(data))


def _illegal_helper(project):
    helper = project / "base_lib/domain_helpers/illegal_model.py"
    helper.write_text('"""A model definition in an ordinary transform helper."""\n'
                      'def model_forward(value):\n    return value + 1\n')
    path = project / "nodes/domain_nodes.py"
    source = path.read_text().replace("from ..base_lib.domain_helpers.arithmetic import scale",
        "from ..base_lib.domain_helpers.arithmetic import scale\nfrom ..base_lib.domain_helpers.illegal_model import model_forward")
    source = source.replace('return {"result": value + params["offset"]}',
                            'return {"result": model_forward(value) + params["offset"]}')
    path.write_text(source)
    declaration = resource(project, "node", "example.transform")
    data = json.loads(declaration.read_text())
    data["implementations"][0].setdefault("implementation_files", []).append({"kind":"file", "ref":"base_lib/domain_helpers/illegal_model.py"})
    declaration.write_text(json.dumps(data))
    return helper


def test_category_rules_public_ast_helpers_and_actual_numerical_run(domain_project, capsys, tmp_path):
    workspace, project = domain_project
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 0, payload
    evidence = _evidence(payload, "example.model")
    assert "model_block" in evidence["tags"]
    assert evidence["ast_kind"] == "ClassDef"
    assert [item["symbol"] for item in evidence["definitions"]] == ["ModelBlock.model_forward"]
    assert {"symbol": "scale", "path": str(project / "base_lib/domain_helpers/arithmetic.py"),
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
    assert "model_block" in architecture["node_definitions"]["example.model"]["info"]["tags"]
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
    assert finding["details"]["ownership"] == [{"definition_id": "example.transform", "relation": "helper_reference"}]
    assert finding["details"]["calls"] == [{"owner": "pipeline", "node": "transform"}]
    if command == "review":
        assert payload["published"] is False
        assert not (tmp_path / "invalid.svg").exists()
    if command == "run":
        assert not (tmp_path / "runs/invalid/output_summary.json").exists()


def test_one_block_is_a_domain_convention_and_empty_selection_is_unconstrained(domain_project, capsys):
    workspace, project = domain_project
    path = project / "nodes/domain_nodes.py"
    source = path.read_text().replace("    def run_pure(self, inputs, params):\n        value = inputs[\"example.input\"]",
        "    def model_forward(self, value, gain):\n        return value * gain\n\n"
        "    def run_pure(self, inputs, params):\n        value = inputs[\"example.input\"]")
    path.write_text(source)
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 1
    finding = next(item for item in payload["errors"] if item["code"] == "EXAMPLE.MODEL.ONE_BLOCK")
    assert finding["definition_id"] == "example.model_definition"
    assert finding["details"]["count"] == 2
    declaration = resource(project, 'node', 'example.model')
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
    path = resource(project, 'node', 'example.unused')
    data = json.loads((resource(project, 'node', 'example.model')).read_text())
    data["id"] = "example.unused"
    data["implementations"][0]["source"] = {"kind": "file", "ref": "nodes/unused/model.py", "export": "UnusedModel"}
    path.write_text(json.dumps(data))
    unused = project / "nodes/unused"
    unused.mkdir()
    (unused / "model.py").write_text("class UnusedModel:\n    def run_pure(self, inputs, params):\n        return {'feature': 1}\n")
    (unused / "unreachable.py").write_text("def model_forward(value):\n    return value\n")
    code, payload = _call(capsys, ["quality-check", "--workspace", str(workspace), "--json"])
    assert code == 0, payload["errors"]
    definitions = [item for report in payload["reports"] for item in report["errors"] if item["definition_id"] == "example.model_definition"]
    assert definitions == []
    evidence = _evidence(payload["reports"][0], "example.model")
    assert not any(item["path"].endswith("unreachable.py") for item in evidence["definitions"])


def test_rule_review_does_not_import_node_or_rule_implementations(domain_project, capsys):
    workspace, project = domain_project
    node_marker, rule_marker = project / "node-imported", project / "rule-imported"
    for path, marker in ((project / "nodes/domain_nodes.py", node_marker), (project / "plugins/code_plugin/rules/model_definition.py", rule_marker)):
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


@pytest.mark.parametrize("location", ["module", "ordinary_node"])
def test_same_file_model_definitions_have_precise_domain_ownership(domain_project, capsys, location):
    workspace, project = domain_project
    path = project / "nodes/domain_nodes.py"
    source = path.read_text()
    if location == "module":
        source += "\n\ndef model_forward(value):\n    return value\n"
        symbol = "model_forward"
    else:
        source = source.replace("class DataTransform:\n", "class DataTransform:\n"
            "    def model_forward(self, value):\n        return value\n\n")
        symbol = "DataTransform.model_forward"
    path.write_text(source)
    line = next(index for index, value in enumerate(source.splitlines(), 1)
                if value.lstrip().startswith("def model_forward(") and
                (location == "module" and value.startswith("def ") or
                 location == "ordinary_node" and index > source.splitlines().index("class DataTransform:") + 1))
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 1, payload
    finding = next(item for item in payload["errors"]
                   if item["code"] == "EXAMPLE.MODEL.LOCATION" and item["details"]["symbol"] == symbol)
    assert finding["definition_id"] == ("example.model_files" if location == "module" else "example.model_definition")
    assert finding["source_location"] == {"path": str(path), "line": line, "column": 1}
    if location == "ordinary_node":
        assert finding["details"]["definition_id"] == "example.transform"
        assert finding["details"]["ownership"] == [{"definition_id": "example.transform", "relation": "helper_reference"}]
        assert finding["details"]["calls"] == [{"owner": "pipeline", "node": "transform"}]
    else:
        # Sharing a module with an allowed model implementation does not grant
        # ownership to an unrelated, module-level definition.
        assert finding["details"]["ownership"] == []


@pytest.mark.parametrize("selection", ["default", "terminal", "empty"])
def test_process_print_policy_is_checked_and_executed_through_cli(domain_project, capsys, tmp_path, monkeypatch, selection):
    workspace, project = domain_project
    source = project / "nodes/domain_nodes.py"
    source.write_text(source.read_text().replace('return {"result": value + params["offset"]}',
        'print("domain transform result", value + params["offset"])\n'
        '        return {"result": value + params["offset"]}'))
    declaration = resource(project, 'node', 'example.transform')
    node = json.loads(declaration.read_text())
    assert node["flow_kind"] == "process"
    if selection == "empty":
        node["rulesets"] = []
        declaration.write_text(json.dumps(node))
    elif selection == "terminal":
        ruleset = resource(project, 'ruleset', 'example.data_domain')
        data = json.loads(ruleset.read_text())
        data["relations"] = [{"source": "$self", "target": "native/effects", "kind": "overrides",
                              "params": {"effect_scope": "terminal"}}]
        ruleset.write_text(json.dumps(data))
    import vibeflow.tooling.application.python.workspace_service as service
    results = []
    def capture(*args, **kwargs):
        result = run_workspace_checked(*args, **kwargs)
        results.append(result)
        return result
    monkeypatch.setattr(service, "run_workspace_checked", capture)
    code = main(["run", *_common(workspace, project), "--input", str(workspace.parent / "input.json"),
                 "--run-root", str(tmp_path / "runs"), "--run-id", selection])
    output = capsys.readouterr().out
    printed = "domain transform result 7\n"
    if selection == "default":
        assert code == 1
        assert printed not in output
        payload = json.loads(output)
        finding = next(item for item in payload["health"]["errors"] if item["code"] == "NODE.EFFECT.CALL_FORBIDDEN")
        assert finding["definition_id"] == "vibeflow.no_side_effects"
        assert not (tmp_path / "runs/default/output_summary.json").exists()
        return
    assert code == 0, output
    assert output.startswith(printed)
    payload = json.loads(output[len(printed):])
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    summary = json.loads((run_dir / "output_summary.json").read_text())
    assert summary["result"]["value"] == {"scalar": True, "type": "int"}
    assert results[0].context.get("result")["value"] == 7
    health = json.loads((run_dir / "health_report.json").read_text())
    assert health["info"]["node_effect_scopes"]["transform"] == ("terminal" if selection == "terminal" else "unconstrained")
    assert json.loads(declaration.read_text())["flow_kind"] == "process"


def test_selected_import_interface_rejects_missing_export_before_module_execution(domain_project, capsys, tmp_path):
    workspace, project = domain_project
    marker = project / "business-module-imported"
    path = project / "nodes/domain_nodes.py"
    path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n" + path.read_text())
    for manifest in resources(project, "node"):
        node = json.loads(manifest.read_text())
        node["rulesets"] = []
        if node["id"] == "example.model":
            node["rulesets"] = ["example.prebind_interface"]
            node["implementations"][0]["source"]["export"] = "MissingModel"
        manifest.write_text(json.dumps(node))
    declaration = resource(project, 'ruleset', 'example.prebind_interface')
    declaration.write_text(json.dumps({"kind":"ruleset","id":"example.prebind_interface",
        "calls":[{"id":"interface","rule_id":"vibeflow.node_interface"}],
        "entrypoints":{"import":["interface"],"static":[],"run":[]}}))
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    assert code == 1, payload
    finding = next(item for item in payload["errors"] if item["code"] == "NODE.IMPLEMENTATION.SYMBOL")
    assert finding["definition_id"] == "vibeflow.node_interface"
    assert finding["source_location"]["path"] == str(path)
    assert finding["details"]["calls"] == [{"owner":"pipeline","node":"model"}]
    assert payload["info"]["rule_phase"] == "import"
    assert not marker.exists()
    code, payload = _call(capsys, ["run", *_common(workspace, project),
        "--input", str(workspace.parent / "input.json"), "--run-root", str(tmp_path / "runs"), "--run-id", "prebind-interface"])
    assert code == 1, payload
    assert any(item["definition_id"] == "vibeflow.node_interface" for item in payload["health"]["errors"])
    assert not marker.exists()
    assert not (tmp_path / "runs/prebind-interface/output_summary.json").exists()


@pytest.mark.parametrize("export", ["check", "missing_module_rule"])
def test_module_rule_binding_uses_resolved_source_provenance(domain_project, capsys, export):
    workspace, project = domain_project
    manifest = resource(project, 'rule', 'example.model_definition')
    data = json.loads(manifest.read_text())
    data["implementations"][0]["source"] = {"kind":"module","ref":"plugins.code_plugin.rules.model_definition","export":export}
    manifest.write_text(json.dumps(data))
    code, payload = _call(capsys, ["validate", *_common(workspace, project), "--json"])
    if export == "check":
        assert code == 0, payload
        assert "model_block" in _evidence(payload,"example.model")["tags"]
    else:
        assert code == 1, payload
        finding = next(item for item in payload["errors"] if item["code"] == "RULE.IMPLEMENTATION.LOAD")
        assert finding["definition_id"] == "example.model_definition"
        assert finding["source_location"]["path"] == str(project / "plugins/code_plugin/plugin.py")
        assert finding["source_location"]["line"] > 0
        assert finding["details"]["implementation"] == {"kind":"module","ref":"plugins.code_plugin.rules.model_definition",
            "export":export,"path":str(project / "plugins/code_plugin/rules/model_definition.py")}
