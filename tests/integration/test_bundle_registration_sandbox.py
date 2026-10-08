"""Both Targets register contributed declarations through the public CLI."""

from __future__ import annotations
from tests.fixtures.support.plugins import resource as resource_ref, copy_sdk_inputs, write_plugin, resources

import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from vibeflow.tooling.application.cli import main
from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs


ROOT = Path(__file__).resolve().parents[2]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture(params=["python", "javascript"])
def registered_project(tmp_path, request):
    target = request.param
    example = tmp_path / target
    shutil.copytree(ROOT / f"sandbox/{target}/domain_rules", example,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".artifacts"))
    copy_sdk_inputs(ROOT / f"sandbox/{target}/domain_rules", example)
    project = example / "project"
    if target == "javascript":
        toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
        if not (toolchain / "node_modules/typescript").is_dir():
            pytest.skip("requires the pinned TypeScript/esbuild toolchain")
        (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for manifest in resources(project, "node"):
        data = json.loads(manifest.read_text())
        data["rulesets"] = []
        _write(manifest, data)
    config = project / "configs/model.jsonc"
    graph = json.loads(config.read_text())
    graph["rulesets"] = []
    _write(config, graph)
    imported, executed = project / "node-imported", project / "node-executed"
    if target == "python":
        source = project / "registration_node.py"
        source.write_text(f"from pathlib import Path\nPath({str(imported)!r}).write_text('imported')\n" +
            (project / "domain_nodes.py").read_text().replace('return {"feature": self.model_forward(value, params["gain"])}',
                f"Path({str(executed)!r}).write_text('executed')\n"
                '        return {"feature": self.model_forward(value, params["gain"])}'))
        manifest = resource_ref(project, 'node', 'example.model')
        data = json.loads(manifest.read_text())
        data["implementations"][0]["source"]["ref"] = "registration_node.py"
        _write(manifest, data)
    else:
        source = project / "nodes/model.ts"
        source.write_text('import {writeFileSync} from "node:fs";\n' +
            f"writeFileSync({json.dumps(str(imported))}, 'imported');\n" +
            source.read_text().replace(
                "  return ", f"  writeFileSync({json.dumps(str(executed))}, 'executed');\n  return "))
    for name in tuple(sys.modules):
        if name in {"domain_nodes", "registration_node"} or name.startswith("domain_helpers"):
            sys.modules.pop(name)
    yield target, example / "vibeflow_config.jsonc", project, imported, executed
    for name in tuple(sys.modules):
        if name in {"domain_nodes", "registration_node"} or name.startswith("domain_helpers"):
            sys.modules.pop(name)


def _validate(capsys, workspace, project):
    code = main(["validate", "--workspace", str(workspace),
                 "--config", str(project / "configs/model.jsonc"), "--json"])
    return code, json.loads(capsys.readouterr().out)


def _select(project, selection):
    config = project / "configs/model.jsonc"
    data = json.loads(config.read_text())
    data["plugins"].append(selection)
    _write(config, data)


@pytest.mark.parametrize("resource", ["nodes", "rules"])
@pytest.mark.parametrize("different", [False, True], ids=["duplicate", "conflict"])
def test_different_declaration_files_with_same_id_are_rejected_before_node_import(registered_project, capsys, resource, different):
    target, workspace, project, imported, executed = registered_project
    original = resource_ref(project, "node" if resource == "nodes" else "rule", "example.model" if resource == "nodes" else "example.model_definition")
    data = json.loads(original.read_text())
    if different:
        data["description"] += " A conflicting contribution."
    selection = write_plugin(project, [data], target=target, plugin_id="fixture.additional", filename="additional_plugin.py" if target == "python" else "additional_plugin.ts")
    _select(project, selection)
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    prefix = "RULE.RESOURCE" if resource == "rules" else "DESCRIPTOR"
    assert (prefix + (".CONFLICT" if different else ".DUPLICATE")) in diagnostic
    assert str(project / ("code_plugin.py" if target == "python" else "code_plugin.ts")) in diagnostic
    origins = payload.get("diagnostics",payload.get("errors",[]))[0]["details"]["origins"]
    assert origins["current"]["path"] != origins["previous"]["path"]
    assert ("example.model" if resource == "nodes" else "example.model_definition") in diagnostic
    assert not imported.exists()
    assert not executed.exists()


def test_missing_selected_sdk_plugin_is_rejected_with_its_source(registered_project, capsys):
    target, workspace, project, imported, executed = registered_project
    missing = "missing_plugin.py" if target == "python" else "missing_plugin.ts"
    _select(project, {"source": {"kind":"file", "ref":missing, "export":"plugin"}})
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert missing in diagnostic
    assert not imported.exists() and not executed.exists()


def test_unknown_selected_ruleset_rejects_before_node_import(registered_project, capsys):
    _, workspace, project, imported, executed = registered_project
    manifest = resource_ref(project, 'node', 'example.model')
    data = json.loads(manifest.read_text())
    data["rulesets"] = ["example.missing_ruleset"]
    _write(manifest, data)
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert "RULE.RESOURCE.UNKNOWN" in diagnostic
    assert "example.missing_ruleset" in diagnostic
    assert "example.model" in diagnostic
    assert not imported.exists() and not executed.exists()


@pytest.mark.parametrize("failure", ["source", "export"])
def test_native_node_binding_failure_preserves_real_import_boundary(registered_project, capsys, failure):
    target, workspace, project, imported, executed = registered_project
    manifest = resource_ref(project, 'node', 'example.model')
    data = json.loads(manifest.read_text())
    source = data["implementations"][0]["source"]
    if failure == "source":
        missing = project / ("missing_node.py" if target == "python" else "nodes/missing_node.ts")
        source["ref"] = str(missing.relative_to(project))
    else:
        source["export"] = "MissingNodeExport"
    _write(manifest, data)
    if failure == "source":
        code, payload = _validate(capsys, workspace, project)
    elif target == "python":
        code = main(["run", "--workspace", str(workspace), "--config", str(project / "configs/model.jsonc"),
            "--input", str(workspace.parent / "input.json"), "--run-root", str(project / "runs"), "--run-id", "invalid-export"])
        payload = json.loads(capsys.readouterr().out)
        assert not (project / "runs/invalid-export/output_summary.json").exists()
    else:
        output = project / "invalid-aot"
        code = main(["build", "--workspace", str(workspace), "--config", str(project / "configs/model.jsonc"),
            "--target", "node", "--profile", "single-esm", "--out-dir", str(output)])
        payload = json.loads(capsys.readouterr().out)
        assert not output.exists()
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert (str(missing) if failure == "source" else "MissingNodeExport") in diagnostic
    assert not executed.exists()
    # Python [] explicitly permits dynamic exports. Import is necessary to
    # discover the actual binding; a failed export never calls the Node.
    assert imported.exists() is (target == "python" and failure == "export")


@pytest.mark.parametrize("failure", ["source", "export"])
def test_selected_rule_binding_failure_never_imports_the_business_node(registered_project, capsys, failure):
    target, workspace, project, imported, executed = registered_project
    rule_manifest = resource_ref(project, 'rule', 'example.model_definition')
    data = json.loads(rule_manifest.read_text())
    source = data["implementations"][0]["source"]
    if failure == "source":
        missing = project / ("rules/missing_rule.py" if target == "python" else "rules/missing_rule.ts")
        source["ref"] = str(missing.relative_to(project))
    else:
        source["export"] = "missing_rule_export"
    _write(rule_manifest, data)
    _write(resource_ref(project, "ruleset", "example.registration"), {"kind": "ruleset", "id": "example.registration",
        "calls": [{"id": "check", "rule_id": "example.model_definition"}],
        "entrypoints": {"import": ["check"], "static": ["check"], "run": ["check"]}})
    manifest = resource_ref(project, 'node', 'example.model')
    node = json.loads(manifest.read_text())
    node["rulesets"] = ["example.registration"]
    _write(manifest, node)
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert (str(missing) if failure == "source" else "missing_rule_export") in diagnostic
    assert "example.model_definition" in diagnostic
    assert not imported.exists() and not executed.exists()
