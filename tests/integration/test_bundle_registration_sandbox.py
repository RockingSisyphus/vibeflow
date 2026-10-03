"""Both Targets register contributed declarations through the public CLI."""

from __future__ import annotations

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
    from tests.fixtures.support.code_plugins import copy_archival_inputs
    copy_archival_inputs(ROOT / f"sandbox/{target}/domain_rules", example)
    project = example / "project"
    if target == "javascript":
        toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
        if not (toolchain / "node_modules/typescript").is_dir():
            pytest.skip("requires the pinned TypeScript/esbuild toolchain")
        (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for manifest in (project / "bundle/nodes").glob("*.jsonc"):
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
        manifest = project / "bundle/nodes/model.jsonc"
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
    from tests.fixtures.support.code_plugins import migrate_fixture
    migrate_fixture(project)
    code = main(["validate", "--workspace", str(workspace),
                 "--config", str(project / "configs/model.jsonc"), "--json"])
    return code, json.loads(capsys.readouterr().out)


def _extra_bundle(project, resources):
    path = project / "bundles/extra.jsonc"
    _write(path, {"kind": "bundle", "id": "example.extra", "resources": resources})
    return path


@pytest.mark.parametrize("route", ["shared", "transitive"])
def test_multiple_bundles_share_one_canonical_declaration_and_keep_its_origin(registered_project, capsys, route):
    target, workspace, project, imported, executed = registered_project
    if route == "shared":
        _extra_bundle(project, {"nodes": ["../bundle/nodes/model.jsonc"],
                                "rules": ["../bundle/rules/model-definition.jsonc"]})
    else:
        _extra_bundle(project, {"bundles": ["domain.jsonc"]})
    code, payload = _validate(capsys, workspace, project)
    assert code == 0, payload
    catalogs = load_workflow_catalogs(project, workflow_config=project / "configs/model.jsonc")
    assert catalogs.nodes.source_for("example.model") == str(project / ("code_plugin.py" if target == "python" else "code_plugin.ts"))
    assert catalogs.rules.source_for("example.model_definition") == str(project / ("code_plugin.py" if target == "python" else "code_plugin.ts"))
    assert sum(item.type_key == "example.model" for item in catalogs.nodes) == 1
    assert sum(item.id == "example.model_definition" for item in catalogs.rules) == 1
    assert not imported.exists()
    assert not executed.exists()


@pytest.mark.parametrize("resource", ["nodes", "rules"])
@pytest.mark.parametrize("different", [False, True], ids=["duplicate", "conflict"])
def test_different_declaration_files_with_same_id_are_rejected_before_node_import(registered_project, capsys, resource, different):
    target, workspace, project, imported, executed = registered_project
    original = project / ("bundle/nodes/model.jsonc" if resource == "nodes" else "bundle/rules/model-definition.jsonc")
    data = json.loads(original.read_text())
    if different:
        data["description"] += " A conflicting contribution."
    duplicate = project / "contribution" / original.name
    _write(duplicate, data)
    _extra_bundle(project, {resource: ["../contribution/" + original.name]})
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    prefix = "RULE.RESOURCE" if resource == "rules" else "DESCRIPTOR"
    assert (prefix + (".CONFLICT" if different else ".DUPLICATE")) in diagnostic
    assert str(project / ("code_plugin.py" if target == "python" else "code_plugin.ts")) in diagnostic
    origins = payload.get("diagnostics",payload.get("errors",[]))[0]["details"]["origins"]
    assert origins["current"]["line"] != origins["previous"]["line"]
    assert ("example.model" if resource == "nodes" else "example.model_definition") in diagnostic
    assert not imported.exists()
    assert not executed.exists()


def test_dangling_bundle_resource_is_rejected_with_its_resource_path(registered_project, capsys):
    _, workspace, project, imported, executed = registered_project
    missing = project / "contribution/missing.jsonc"
    missing.parent.mkdir()
    _extra_bundle(project, {"nodes": ["../contribution/missing.jsonc"]})
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert "PLUGIN.DECLARATION.LOAD" in diagnostic or "VF_PLUGIN_PROCESS" in diagnostic
    assert "missing" in diagnostic
    assert not imported.exists() and not executed.exists()


def test_unknown_selected_ruleset_rejects_before_node_import(registered_project, capsys):
    _, workspace, project, imported, executed = registered_project
    manifest = project / "bundle/nodes/model.jsonc"
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
    manifest = project / "bundle/nodes/model.jsonc"
    data = json.loads(manifest.read_text())
    source = data["implementations"][0]["source"]
    if failure == "source":
        missing = project / ("missing_node.py" if target == "python" else "nodes/missing_node.ts")
        source["ref"] = str(missing.relative_to(project))
    else:
        source["export"] = "MissingNodeExport"
    _write(manifest, data)
    from tests.fixtures.support.code_plugins import migrate_fixture
    migrate_fixture(project)
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
    rule_manifest = project / "bundle/rules/model-definition.jsonc"
    data = json.loads(rule_manifest.read_text())
    source = data["implementations"][0]["source"]
    if failure == "source":
        missing = project / ("rules/missing_rule.py" if target == "python" else "rules/missing_rule.ts")
        source["ref"] = str(missing.relative_to(project))
    else:
        source["export"] = "missing_rule_export"
    _write(rule_manifest, data)
    _write(project / "bundle/rulesets/registration.jsonc", {"kind": "ruleset", "id": "example.registration",
        "calls": [{"id": "check", "rule_id": "example.model_definition"}],
        "entrypoints": {"import": ["check"], "static": ["check"], "run": ["check"]}})
    _extra_bundle(project, {"rulesets": ["../bundle/rulesets/registration.jsonc"]})
    manifest = project / "bundle/nodes/model.jsonc"
    node = json.loads(manifest.read_text())
    node["rulesets"] = ["example.registration"]
    _write(manifest, node)
    code, payload = _validate(capsys, workspace, project)
    assert code == 1, payload
    diagnostic = json.dumps(payload)
    assert (str(missing) if failure == "source" else "missing_rule_export") in diagnostic
    assert "example.model_definition" in diagnostic
    assert not imported.exists() and not executed.exists()
