"""Executable SDK domain resources: styling, ownership, Rule diagnostics and runtime."""
from __future__ import annotations

from tests.fixtures.support.plugins import resource as sdk_resource

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "sandbox/javascript/domain_rules"


@pytest.fixture
def domain_project(tmp_path: Path) -> tuple[Path, Path]:
    toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules").is_dir():
        pytest.skip("requires the project-local TypeScript/esbuild toolchain")
    example = tmp_path / "example"
    shutil.copytree(EXAMPLE, example)
    project = example / "project"
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    return example / "vibeflow_config.jsonc", project


def test_domain_sdk_presentation_and_actual_numerical_execution(domain_project, tmp_path: Path) -> None:
    workspace, project = domain_project
    config = project / "configs/model.jsonc"
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    node = next(item for item in audited.architecture["workflow"]["nodes"] if item["id"] == "model")
    assert node["presentation"]["values"]["fill"] == "#cceeff"
    assert node["presentation"]["sources"]["fill"] == "node"
    assert "model_block" in node["tags"]
    assert "#cceeff" in render_mermaid(audited)
    assert audited.rule_report.results["example.model"][-1].plan.ruleset_id == "example.model_domain"
    built = build_project_aot(ProjectBuildRequest(workspace, config, tmp_path / "dist", "node", "single-esm"))
    completed = subprocess.run(["node", "--input-type=module", "--eval", f"import {{pathToFileURL}} from 'node:url'; const w=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(w.runWorkflow({{value: 3}})));"], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"result": 7}


def test_domain_rule_rejects_helper_model_definition_with_precise_ownership(domain_project) -> None:
    workspace, project = domain_project
    helper = project / "nodes/transform_helper.ts"
    helper.write_text("// wrong business location\nexport function modelForward(value: number): number { return value + 1; }\n", encoding="utf-8")
    transform = project / "nodes/transform.ts"
    transform.write_text('import {modelForward} from "./transform_helper.ts";\nexport function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) {\n  return {output: modelForward(inputs["example.feature"].value)};\n}\n', encoding="utf-8")
    declaration = sdk_resource(project, 'node', 'example.transform')
    descriptor = json.loads(declaration.read_text()); descriptor["base_libs"] = ["example.transform_helper"]
    declaration.write_text(json.dumps(descriptor), encoding="utf-8")
    (sdk_resource(project, "base_lib", "example.transform_helper")).write_text(json.dumps({"kind": "base_lib", "id": "example.transform_helper", "display_name": "Transform helper", "description": "Helper attributed to the transform Node.", "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "nodes/transform_helper.ts"}}]}), encoding="utf-8")
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    finding = next(item for item in error.value.diagnostics if item["rule_id"] == "EXAMPLE.MODEL.LOCATION")
    assert finding["source_location"]["path"] == str(helper)
    assert finding["source_location"]["line"] == 2
    assert finding["details"]["call_paths"] == [["transform"]]
    assert finding["details"]["ownership"]["node_definitions"] == ["example.transform"]


def _wrong_domain_location(project: Path, location: str) -> tuple[Path, int]:
    """Keep native contracts valid while placing a model in a transform's scope."""
    transform = project / "nodes/transform.ts"
    if location == "shared_file":
        source = project / "nodes/model.ts"
        source.write_text(source.read_text() + '\nexport function transformRun(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) { return {output: inputs["example.feature"].value + 1}; }\n')
        declaration = sdk_resource(project, 'node', 'example.transform')
        data = json.loads(declaration.read_text())
        data["implementations"][0]["source"].update({"ref": "nodes/model.ts", "export": "transformRun"})
        declaration.write_text(json.dumps(data))
    elif location == "transform":
        source = transform
        source.write_text('// A model definition directly in an ordinary transform.\nexport function modelForward(value: number): number { return value + 1; }\nexport function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) { return {output: modelForward(inputs["example.feature"].value)}; }\n')
    else:
        assert location == "helper"
        source = project / "nodes/transform_helper.ts"
        source.write_text('// A model definition in a transform helper.\nexport function modelForward(value: number): number { return value + 1; }\n')
        transform.write_text('import {modelForward} from "./transform_helper.js";\nexport function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) { return {output: modelForward(inputs["example.feature"].value)}; }\n')
        declaration = sdk_resource(project, 'node', 'example.transform')
        data = json.loads(declaration.read_text()); data["base_libs"] = ["example.transform_helper"]
        declaration.write_text(json.dumps(data))
        (sdk_resource(project, "base_lib", "example.transform_helper")).write_text(json.dumps({"kind": "base_lib", "id": "example.transform_helper",
            "display_name": "Transform helper", "description": "A helper attributed to the transform.",
            "implementations": [{"language": "typescript", "targets": ["node", "browser"],
                "source": {"kind": "file", "ref": "nodes/transform_helper.ts"}}]}))
    return source, 2


def _domain_commands(project: Path) -> None:
    config = project / "vibeflow_project.jsonc"
    data = json.loads(config.read_text())
    data.update({"architecture": {"documents": [
        {"workflow": "configs/model.jsonc", "document": "Architecture.jsonc"}]}})
    config.write_text(json.dumps(data))


def _domain_cli(workspace: Path, project: Path, command: str, *options: str):
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "vibeflow", command, "--workspace", str(workspace),
        *([] if command == "quality-check" else ["--config", str(project / "configs/model.jsonc")]), *options], cwd=project, env=environment,
        check=False, capture_output=True, text=True, timeout=60)


def _domain_diagnostic(diagnostics, source: Path, line: int, rule="example.model_definition"):
    finding = next(item for item in diagnostics if item.get("code") == "EXAMPLE.MODEL.LOCATION")
    assert finding["definition_id"] == rule
    assert finding["object_id"] == "example.transform"
    assert finding["source_location"] == {"path": str(source), "line": line, "column": 1}
    assert finding["details"]["definition_id"] == "example.transform"
    assert finding["details"]["call_paths"] == [["transform"]]
    assert "example.transform" in finding["details"]["ownership"]["node_definitions"]
    return finding


@pytest.mark.parametrize("location", ["shared_file", "transform", "helper"])
def test_domain_locations_are_rejected_by_formal_commands_without_publishing(domain_project, tmp_path, location) -> None:
    workspace, project = domain_project
    source, line = _wrong_domain_location(project, location)
    _domain_commands(project)
    config = project / "configs/model.jsonc"
    with pytest.raises(ProjectBuildError) as audit_error:
        audit_javascript_project(JavascriptAuditRequest(workspace, config))
    expected = _domain_diagnostic(audit_error.value.diagnostics, source, line, "example.model_files" if location == "shared_file" else "example.model_definition")
    with pytest.raises(ProjectBuildError) as build_error:
        build_project_aot(ProjectBuildRequest(workspace, config, tmp_path / "dist", "node", "single-esm"))
    assert _domain_diagnostic(build_error.value.diagnostics, source, line, "example.model_files" if location == "shared_file" else "example.model_definition") == expected
    assert not (tmp_path / "dist").exists()

    for command in ("validate", "quality-check"):
        result = _domain_cli(workspace, project, command, "--json")
        assert result.returncode == 1, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["status"] in {"ERROR", "FAIL"}
        diagnostics = payload["reports"][0]["diagnostics"] if command == "quality-check" else payload["diagnostics"]
        assert _domain_diagnostic(diagnostics, source, line, "example.model_files" if location == "shared_file" else "example.model_definition") == expected
        result = _domain_cli(workspace, project, command)
        assert result.returncode == 1, result.stderr or result.stdout
        for fragment in ("EXAMPLE.MODEL.LOCATION", "example.model_files" if location == "shared_file" else "example.model_definition", f"{source}:{line}:1", "example.transform"):
            assert fragment in result.stdout

    architecture, output = project / "Architecture.jsonc", tmp_path / "review.svg"
    architecture.write_text("previous Architecture", encoding="utf-8")
    output.write_text("previous SVG", encoding="utf-8")
    reviewed = _domain_cli(workspace, project, "review", "--output", str(output))
    assert reviewed.returncode == 1, reviewed.stderr or reviewed.stdout
    payload = json.loads(reviewed.stdout)
    assert payload["status"] == "FAIL" and payload["failed_stage"] == "preflight" and payload["published"] is False
    assert _domain_diagnostic(payload["diagnostics"], source, line, "example.model_files" if location == "shared_file" else "example.model_definition") == expected
    assert architecture.read_text() == "previous Architecture" and output.read_text() == "previous SVG"
    assert not list(tmp_path.glob("*.tmp.svg"))


def test_allowed_top_level_model_passes_formal_checks_build_and_actual_execution(domain_project, tmp_path) -> None:
    workspace, project = domain_project
    _domain_commands(project)
    # JS Node implementations are exports; this top-level function belongs to the model Node's declared source.
    assert "export function modelForward" in (project / "nodes/model.ts").read_text()
    for command in ("validate", "quality-check"):
        result = _domain_cli(workspace, project, command, "--json")
        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["status"] in {"PASS", "CONCERNS"}
        rule_checks = payload["reports"][0]["rule_checks"] if command == "quality-check" else payload["rule_checks"]
        selected = rule_checks["subjects"]["example.model"]
        assert any(item["plan"]["entrypoint"] == "static" and item["executed"] == ["model_definition"] for item in selected)
    built = build_project_aot(ProjectBuildRequest(workspace, project / "configs/model.jsonc", tmp_path / "dist", "node", "single-esm"))
    result = subprocess.run(["node", "--input-type=module", "--eval", f"import {{pathToFileURL}} from 'node:url'; const workflow=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(workflow.runWorkflow({{value:3}})));"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"result": 7}


def test_run_only_domain_rule_is_explicit_and_does_not_become_a_build_check(domain_project, tmp_path) -> None:
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs

    workspace, project = domain_project
    source, line = _wrong_domain_location(project, "transform")
    rule = sdk_resource(project, 'ruleset', 'example.model_domain')
    data = json.loads(rule.read_text()); data["entrypoints"] = {"import": [], "static": [], "run": ["model_definition"]}
    rule.write_text(json.dumps(data))
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    assert not any(execution.executed for executions in audited.rule_report.results.values() for execution in executions if execution.plan.ruleset_id == "example.model_domain")
    built = build_project_aot(ProjectBuildRequest(workspace, project / "configs/model.jsonc", tmp_path / "dist", "node", "single-esm"))
    result = subprocess.run(["node", "--input-type=module", "--eval", f"import {{pathToFileURL}} from 'node:url'; const workflow=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(workflow.runWorkflow({{value:3}})));"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"result": 7}
    # The public Target checker can explicitly select run; no JS run command or implicit runtime scan is introduced.
    catalogs = prepare_workflow_catalogs(project / "configs/model.jsonc")
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project, allowed_external=set())
    checked = run_javascript_rules(audited.graph, catalogs, project_root=project, package_root=project, target="node", phase="run", import_policy=policy)
    _domain_diagnostic([finding.to_dict() for finding in checked.findings], source, line)
    assert any(execution.plan.entrypoint == "run" and execution.executed == ("model_definition",) for execution in checked.results["example.transform"])


@pytest.mark.parametrize("selection", ["default", "terminal", "empty"])
def test_process_console_policy_is_checked_at_build_and_actual_runtime(domain_project, tmp_path, selection) -> None:
    workspace, project = domain_project
    source = project / "nodes/transform.ts"
    source.write_text(source.read_text().replace('  return {output: inputs["example.feature"].value + 1};',
        '  console.log("domain transform result", inputs["example.feature"].value + 1);\n'
        '  return {output: inputs["example.feature"].value + 1};'))
    manifest = sdk_resource(project, 'node', 'example.transform')
    descriptor = json.loads(manifest.read_text())
    assert descriptor["flow_kind"] == "process"
    if selection == "empty":
        descriptor["rulesets"] = []
        manifest.write_text(json.dumps(descriptor))
    elif selection == "terminal":
        sdk_resource(project, "ruleset", "example.data_terminal").write_text(json.dumps({"kind": "ruleset", "id": "example.data_terminal",
            "calls": [{"id": "native", "ruleset_id": "vibeflow.process"},
                      {"id": "domain", "ruleset_id": "example.model_domain"}],
            "relations": [{"source": "$self", "target": "native/effects", "kind": "overrides",
                "params": {"effect_scope": "terminal"}}],
            "entrypoints": {"import": ["native"], "static": ["native", "domain"], "run": ["native", "domain"]}}))
        descriptor["rulesets"] = ["example.data_terminal"]
        manifest.write_text(json.dumps(descriptor))
    request = ProjectBuildRequest(workspace, project / "configs/model.jsonc", tmp_path / "dist", "node", "single-esm")
    if selection == "default":
        with pytest.raises(ProjectBuildError) as error:
            build_project_aot(request)
        finding = next(item for item in error.value.diagnostics if item.get("definition_id") == "vibeflow.no_side_effects")
        assert finding["code"] == "VF_BASE_LIB_HOST_IO"
        assert finding["source_location"] == {"path": str(source), "line": 3, "column": 3}
        assert finding["details"]["definition_id"] == "example.transform"
        assert finding["details"]["call_paths"] == [["transform"]]
        assert not request.out_dir.exists()
        return
    built = build_project_aot(request)
    report = built.prepared.rule_report
    assert built.prepared.compiled.effect_scopes["transform"] == ("terminal" if selection == "terminal" else "unconstrained")
    if selection == "terminal":
        execution = next(item for item in report.results["example.transform"] if item.plan.entrypoint == "static")
        invocation = next(item for item in execution.plan.invocations if item.id == "native/effects")
        assert invocation.params["effect_scope"] == "terminal"
        assert invocation.parameter_sources["effect_scope"] == "override:$self"
        assert report.policies["example.transform"]["records"][0]["definition_id"] == "vibeflow.no_side_effects"
    else:
        assert report.results["example.transform"] == ()
        assert "example.transform" in report.to_dict()["unconstrained"]
    result = subprocess.run(["node", "--input-type=module", "--eval", f"import {{pathToFileURL}} from 'node:url'; const workflow=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(workflow.runWorkflow({{value:3}})));"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'domain transform result 7\n{"result":7}\n'
    assert json.loads(manifest.read_text())["flow_kind"] == "process"


def test_process_console_name_shadowing_keeps_local_object_pure(domain_project, tmp_path) -> None:
    workspace, project = domain_project
    source = project / "nodes/transform.ts"
    source.write_text('export function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) {\n'
        '  const console = {log: (value: number) => value + 1};\n'
        '  return {output: console.log(inputs["example.feature"].value)};\n}\n')
    built = build_project_aot(ProjectBuildRequest(workspace, project / "configs/model.jsonc", tmp_path / "dist", "node", "single-esm"))
    assert built.prepared.compiled.effect_scopes["transform"] == "none"
    result = subprocess.run(["node", "--input-type=module", "--eval", f"import {{pathToFileURL}} from 'node:url'; const workflow=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(workflow.runWorkflow({{value:3}})));"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == '{"result":7}\n'


def test_explicit_empty_node_rulesets_is_reported_unconstrained(domain_project) -> None:
    workspace, project = domain_project
    manifest = sdk_resource(project, 'node', 'example.model')
    declaration = json.loads(manifest.read_text())
    declaration["rulesets"] = []
    manifest.write_text(json.dumps(declaration), encoding="utf-8")
    # A category's default domain constraint is replaced by the explicit empty selection.
    model = project / "nodes/model.ts"
    model.write_text('export function run(inputs: Readonly<{"example.input": Readonly<{value: number}>}>) { return {feature: inputs["example.input"].value * 2}; }\n', encoding="utf-8")
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    assert audited.rule_report.results["example.model"] == ()
    assert "example.model" in audited.rule_report.to_dict()["unconstrained"]
    assert audited.compiled.effect_scopes["model"] == "unconstrained"


def test_multiple_effect_rules_retain_all_constraints_and_report_mixed(domain_project) -> None:
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.frontend.facts import target_neutral_implementation_facts_from_catalog
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs

    _, project = domain_project
    file = sdk_resource(project, 'node', 'example.model')
    data = json.loads(file.read_text()); data["rulesets"] = ["vibeflow.process", "vibeflow.io"]; file.write_text(json.dumps(data))
    catalogs = prepare_workflow_catalogs(project / "configs/model.jsonc")
    graph = GraphConfig(nodes=(NodeCallSpec("first", "example.model"), NodeCallSpec("second", "example.model")), rulesets=())
    report = run_javascript_rules(graph, catalogs, project_root=project, package_root=project, evaluate_sources=False)
    policy = report.policies["example.model"]
    assert policy["effect_scope"] == "mixed"
    assert {item["value"]["effect_scope"] for item in policy["records"]} == {"none", "terminal"}
    assert {item["rule_call_id"] for item in policy["records"]} == {"effects"}
    assert not any(item.code == "RULE.EFFECT_POLICY.CONFLICT" for item in report.findings)
    assert report.call_effect_scopes == {("example.model", "first"): "mixed", ("example.model", "second"): "mixed"}
    fact = target_neutral_implementation_facts_from_catalog(catalogs.nodes, effect_policies=report.policies).get("example.model")
    assert fact.effect_scope == "mixed"


def test_call_effect_policy_keeps_actual_call_config_and_findings(domain_project) -> None:
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs

    _, project = domain_project
    (project / "plugins/code_plugin/rules/call_policy.ts").write_text('export function check(context) { const io=context.subject.call_spec.params.io; return {records:{policy:{type_id:"vibeflow.effect_policy.v1",value:{effect_scope:io?"terminal":"none",allowed_effects:io?["terminal"]:[]}}},findings:io?[]:[{code:"EXAMPLE.STRICT",severity:"error",message:"Strict constraint stays visible"}]}; }\n')
    (sdk_resource(project, "rule", "test.call_policy")).write_text(json.dumps({"kind": "rule", "id": "test.call_policy", "outputs": {"policy": "vibeflow.effect_policy.v1"}, "implementations": [{"language": "typescript",  "source": {"kind": "file", "ref": "rules/call_policy.ts", "export": "check"}}]}))
    (sdk_resource(project, "ruleset", "test.call_policy")).write_text(json.dumps({"kind": "ruleset", "id": "test.call_policy", "calls": [{"id": "effect", "rule_id": "test.call_policy"}], "entrypoints": {"static": ["effect"]}}))
    file = sdk_resource(project, 'node', 'example.model')
    data = json.loads(file.read_text()); data["rulesets"] = ["test.call_policy"]; file.write_text(json.dumps(data))
    catalogs = prepare_workflow_catalogs(project / "configs/model.jsonc")
    graph = GraphConfig(nodes=(NodeCallSpec("strict", "example.model", params={"io": False}), NodeCallSpec("io", "example.model", params={"io": True})), rulesets=())
    report = run_javascript_rules(graph, catalogs, project_root=project, package_root=project, target="node")
    assert report.policies["example.model"]["effect_scope"] == "mixed"
    assert report.call_effect_scopes == {("example.model", "strict"): "none", ("example.model", "io"): "terminal"}
    assert [item.code for item in report.findings] == ["EXAMPLE.STRICT"]
    records = report.to_dict()["call_effect_policies"]
    assert all(item["definition_id"] == "example.model" for item in records)
    assert all(record["definition_id"] == "test.call_policy" and record["scope"] == "call" for item in records for record in item["records"])
    single = run_javascript_rules(GraphConfig(nodes=(NodeCallSpec("io", "example.model", params={"io": True}),), rulesets=()), catalogs, project_root=project, package_root=project, target="node")
    assert single.policies["example.model"]["effect_scope"] == "mixed"
    assert single.call_effect_scopes == {("example.model", "io"): "terminal"}


def _select_scoped_file_rule(project: Path, scope: str, *, implementation: str = "builtin") -> tuple[Path, Path]:
    helper = project / "nodes/model_helper.ts"
    helper.write_text("export function multiply(value: number): number {\n" + "  value += 0;\n" * 12 + "  return value * 2;\n}\n")
    model = project / "nodes/model.ts"
    model.write_text('import {multiply} from "./model_helper.ts";\n' + model.read_text().replace("return value * 2", "return multiply(value)"))
    # Unused code has neither a descriptor nor a place in this source scope.
    (project / "unused.ts").write_text("function broken( {\n" + "\n" * 1000)
    rule_id = "vibeflow.quality.files"
    if implementation != "builtin":
        rule_id = "test.files"
        declaration = {"kind": "rule", "id": rule_id,
            "params_schema": {"max_file_lines": {"type": "integer"}, "warn_file_lines": {"type": "integer"}},
            "params_defaults": {"max_file_lines": 8, "warn_file_lines": 8}}
        if implementation == "alias":
            declaration["handler"] = "vibeflow.quality.files"
        else:
            (project / "plugins/code_plugin/rules/files.ts").write_text('export function check(context, inputs, params) { return {findings:[...new Set(context.facts.source_files.flatMap(path=>context.sources.reachable(path)))].map(path=>({path,lines:context.sources.text(path).trimEnd().split("\\n").length})).filter(file=>file.lines>params.max_file_lines).map(file=>({code:"TEST.CLOSURE.LINES",severity:"error",message:"Reached helper exceeds the chosen limit",source_location:{path:file.path,line:1},details:{limit:params.max_file_lines}}))}; }\n')
            declaration["implementations"] = [{"language": "typescript", "source": {"kind": "file", "ref": "rules/files.ts", "export": "check"}}]
        sdk_resource(project, "rule", rule_id).write_text(json.dumps(declaration))
    ruleset = {"kind": "ruleset", "id": "test.scope", "calls": [{"id": "files", "rule_id": "vibeflow.quality.files", "params": {"max_file_lines": 8, "warn_file_lines": 8}}],
               "entrypoints": {"static": ["files"], "import": [], "run": []}}
    if implementation == "ordinary":
        ruleset["calls"][0]["rule_id"] = rule_id
    elif implementation != "builtin":
        ruleset["relations"] = [{"source": "$self", "target": "files", "kind": "overrides", "replace_rule": rule_id}]
    resource = sdk_resource(project, "ruleset", "test.scope"); resource.write_text(json.dumps(ruleset))
    for name in ("model", "transform", "boundary"):
        file = sdk_resource(project, "node", "example." + name)
        data = json.loads(file.read_text()); data["rulesets"] = ["test.scope"] if scope == "node" and name == "model" else []; file.write_text(json.dumps(data))
    config = project / "configs/model.jsonc"
    data = json.loads(config.read_text()); data["rulesets"] = ["test.scope"] if scope == "workflow" else []; config.write_text(json.dumps(data))
    return resource, helper


@pytest.mark.parametrize("scope", ["node"])
def test_selected_file_rule_uses_real_closure_and_explicit_overrides(domain_project, tmp_path, capsys, scope) -> None:
    from vibeflow.targets.shared.quality_support import QualityThresholds
    from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy
    from vibeflow.tooling.application.cli import main
    workspace, project = domain_project
    resource, helper = _select_scoped_file_rule(project, scope)
    config = project / "configs/model.jsonc"
    preview = audit_javascript_project(JavascriptAuditRequest(workspace, config, audit_sources=False))
    key = "example.model" if scope == "node" else "workflow:"
    assert preview.rule_report.results[key][-1].status == "ERROR"
    assert not preview.rule_report.findings
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, config, quality_policy=javascript_quality_policy(thresholds=QualityThresholds(max_file_lines=1000))))
    finding = next(item for item in error.value.diagnostics if item["code"] == "QUALITY.FILE.MAX_LINES")
    assert finding["definition_id"] == "vibeflow.quality.files"
    assert finding["source_location"] == {"path": str(helper), "line": 1}
    assert finding["details"]["limit"] == 8
    with pytest.raises(ProjectBuildError):
        build_project_aot(ProjectBuildRequest(workspace, config, tmp_path / "dist", "node", "single-esm"))
    assert main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"]) == 1
    assert "QUALITY.FILE.MAX_LINES" in capsys.readouterr().out
    ruleset = json.loads(resource.read_text())
    ruleset["relations"] = [{"source": "$self", "target": "files", "kind": "overrides", "params": {"max_file_lines": 20, "warn_file_lines": 20}}]
    resource.write_text(json.dumps(ruleset))
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    call = audited.rule_report.results[key][-1].plan.to_dict()["calls"][0]
    assert call["params"]["max_file_lines"] == 20
    assert call["parameter_sources"]["max_file_lines"] == "override:$self"
    assert not any("unused.ts" in str(item.to_dict()) for item in audited.rule_report.findings)
    if scope == "node":
        file = sdk_resource(project, 'node', 'example.model')
    else:
        file = config
    data = json.loads(file.read_text()); data["rulesets"] = []; file.write_text(json.dumps(data))
    unconstrained = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    assert unconstrained.rule_report.results[key] == ()


@pytest.mark.parametrize("implementation", ["alias", "replacement", "ordinary"])
def test_project_topic_alias_and_replacement_receive_the_actual_scope(domain_project, implementation) -> None:
    workspace, project = domain_project
    _, helper = _select_scoped_file_rule(project, "node", implementation=implementation)
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    expected = "QUALITY.FILE.MAX_LINES" if implementation == "alias" else "TEST.CLOSURE.LINES"
    finding = next(item for item in error.value.diagnostics if item["code"] == expected)
    assert finding["definition_id"] == "test.files"
    assert finding["source_location"]["path"] == str(helper)
    assert finding["details"]["limit"] == 8
    assert all("unused.ts" not in str(item) for item in error.value.diagnostics)


def test_native_project_alias_keeps_declared_defaults_and_explicit_overrides(domain_project):
    workspace, project = domain_project
    ruleset, helper = _select_scoped_file_rule(project, "node", implementation="alias")
    data = json.loads(ruleset.read_text())
    data["calls"][0]["params"] = {}
    ruleset.write_text(json.dumps(data))
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    finding = next(item for item in error.value.diagnostics if item["code"] == "QUALITY.FILE.MAX_LINES")
    assert finding["definition_id"] == "test.files"
    assert finding["source_location"]["path"] == str(helper)
    assert finding["details"]["limit"] == 8
    data["relations"].append({"source":"$self", "target":"files", "kind":"overrides",
                              "params":{"max_file_lines":20,"warn_file_lines":20}})
    ruleset.write_text(json.dumps(data))
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    invocation = audited.rule_report.results["example.model"][-1].plan.to_dict()["calls"][0]
    assert invocation["params"] == {"max_file_lines":20, "warn_file_lines":20}
    assert invocation["parameter_sources"]["max_file_lines"] == "override:$self"
    assert not any("unused.ts" in str(item.to_dict()) for item in audited.rule_report.findings)


@pytest.mark.parametrize("state", ["unavailable", "failed"])
@pytest.mark.parametrize("phase", ["import", "static"])
def test_formal_rule_state_failure_is_rejected_before_later_entrances(domain_project, tmp_path, capsys, state, phase) -> None:
    from vibeflow.tooling.application.cli import main

    workspace, project = domain_project
    static_marker = project / "static-rule-ran"
    business_marker = project / "business-node-ran"
    model = project / "nodes/model.ts"
    model.write_text('import {writeFileSync} from "node:fs"; writeFileSync(' + json.dumps(str(business_marker)) + ',"ran");\n' + model.read_text())
    (project / "plugins/code_plugin/rules/status.ts").write_text('import {writeFileSync} from "node:fs"; export function check(context) { if(context.phase===' + json.dumps(phase) + ') return {state:' + json.dumps(state) + ',findings:' + ('[{code:"EXAMPLE.STATUS.WARNING",severity:"warning",message:"Incomplete with warning"}]' if state == "failed" else '[]') + '}; writeFileSync(' + json.dumps(str(static_marker)) + ',"later phase ran"); return {findings:[]}; }\n')
    (sdk_resource(project, "rule", "test.status")).write_text(json.dumps({"kind": "rule", "id": "test.status", "implementations": [{"language": "typescript",  "source": {"kind": "file", "ref": "rules/status.ts", "export": "check"}}]}))
    (sdk_resource(project, "ruleset", "test.status")).write_text(json.dumps({"kind": "ruleset", "id": "test.status", "calls": [{"id": "check", "rule_id": "test.status"}], "entrypoints": {"import": ["check"] if phase == "import" else [], "static": ["check"]}}))
    file = sdk_resource(project, 'node', 'example.model')
    data = json.loads(file.read_text()); data["rulesets"] = ["test.status"]; file.write_text(json.dumps(data))
    config = project / "configs/model.jsonc"
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, config))
    assert any(item["code"] == "RULE.RESULT." + state.upper() and item["definition_id"] == "test.status" for item in error.value.diagnostics)
    with pytest.raises(ProjectBuildError):
        build_project_aot(ProjectBuildRequest(workspace, config, tmp_path / "dist", "node", "single-esm"))
    assert main(["validate", "--workspace", str(workspace), "--config", str(config), "--json"]) == 1
    assert "RULE.RESULT." + state.upper() in capsys.readouterr().out
    assert not business_marker.exists()
    if phase == "import":
        assert not static_marker.exists()
    # Declaration-only previews retain intentionally unavailable source checks.
    preview = audit_javascript_project(JavascriptAuditRequest(workspace, config, audit_sources=False))
    assert any(execution.status == "ERROR" for execution in preview.rule_report.results["example.model"])
    assert not any(item.code.startswith("RULE.RESULT.") for item in preview.rule_report.findings)


def test_rule_abi_arguments_records_ast_and_native_file_io(domain_project) -> None:
    _, project = domain_project
    rule = project / "plugins/code_plugin/rules/wire.ts"
    rule.write_text('import {writeFileSync} from "node:fs"; export function check(context, inputs, params) { writeFileSync(params.file, "rule ran"); const symbols=context.sources.symbols(context.facts.source_files[0]); return {records:{value:{type_id:"example.wire.v1",value:{abi:context.abiVersion, supplied:inputs.prior.value, parameter:params.limit, names:symbols.map(s=>s.name), imports:context.sources.imports(context.facts.source_files[0]).map(s=>s.resolved_path)}}},findings:[]}; }', encoding="utf-8")
    helper = project / "nodes/import_helper.ts"
    helper.write_text("export const value=1;\n")
    source = project / "nodes/model.ts"
    source.write_text('import {value} from "./import_helper.js";\n' + source.read_text())
    output = project / "rule-output.txt"
    with JavascriptPluginSession() as session:
        session.open_rule("rule:wire", rule={"id": "example.wire", "module": str(rule), "export": "check"}, package_root=project)
        returned = session.evaluate_rule("rule:wire", context={"facts": {"source_files": [str(project / "nodes/model.ts")], "sources": [{"path":str(source),"text":source.read_text()},{"path":str(helper),"text":helper.read_text()}]}, "subject": {}, "scope": {}, "phase": "static", "target": "node"}, inputs={"prior": {"type_id": "example.input.v1", "value": 5}}, params={"limit": 9, "file": str(output)})
    value = returned["records"]["value"]["value"]
    assert (value["abi"], value["supplied"], value["parameter"]) == ("vibeflow.rule.v3", 5, 9)
    assert "modelForward" in value["names"]
    assert output.read_text() == "rule ran"
    assert value["imports"] == [str(helper)]


@pytest.mark.parametrize(("scope", "counts"), [("call", [1, 2]), ("source", [1, 1])])
def test_rule_scope_keeps_call_identity_and_caches_source_snapshots(domain_project, scope, counts) -> None:
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
    from vibeflow.tooling.project.resources import prepare_workflow_catalogs

    _, project = domain_project
    rule = project / "plugins/code_plugin/rules/scope.ts"
    rule.write_text('let count=0; export function check(context) { console.log("Rule log"); return {records:{count:{type_id:"example.count.v1",value:{count:++count, call:context.subject.call_spec?.id ?? null, rule:context.subject.rule_call_id ?? null}}},findings:[{code:"EXAMPLE.SCOPE",severity:"warning",message:"Scope proof",source_location:{path:context.facts.source_files[0],line:1}}]}; }\n', encoding="utf-8")
    (sdk_resource(project, "rule", "test.scope")).write_text(json.dumps({"kind": "rule", "id": "test.scope", "scope": scope, "outputs": {"count": "example.count.v1"}, "implementations": [{"language": "typescript",  "source": {"kind": "file", "ref": "rules/scope.ts", "export": "check"}}]}))
    (sdk_resource(project, "ruleset", "test.scope")).write_text(json.dumps({"kind": "ruleset", "id": "test.scope", "calls": [{"id": "check", "rule_id": "test.scope"}], "entrypoints": {"static": ["check"]}}))
    file = sdk_resource(project, 'node', 'example.model')
    data = json.loads(file.read_text()); data["rulesets"] = ["test.scope"]; file.write_text(json.dumps(data))
    catalogs = prepare_workflow_catalogs(project / "configs/model.jsonc")
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project, allowed_external=set(), node_ids=frozenset({"example.model"}))
    graph = GraphConfig(nodes=(NodeCallSpec("first", "example.model"), NodeCallSpec("second", "example.model")), rulesets=())
    report = run_javascript_rules(graph, catalogs, project_root=project, package_root=project, target="node", import_policy=policy)
    results = [execution for execution in report.results["example.model"] if execution.results]
    values = [execution.results["check"].records["count"].value for execution in results]
    assert [value["count"] for value in values] == counts
    assert [value["call"] for value in values] == (["first", "second"] if scope == "call" else [None, None])
    assert all(value["rule"] == ("check" if scope == "call" else None) for value in values)
    assert [execution.executed for execution in results] == [("check",), ("check",) if scope == "call" else ()]
    findings = [finding for finding in report.findings if finding.code == "EXAMPLE.SCOPE"]
    assert all(finding.definition_id == "test.scope" for finding in findings)
    expected_paths = [[["first"]], [["second"]]] if scope == "call" else [[["first"], ["second"]]]
    assert [finding.to_dict()["details"]["call_paths"] for finding in findings] == expected_paths

# Historical mutations are test inputs; publish fixed SDK code explicitly.


def test_call_empty_selection_is_used_by_actual_compiler_and_aot_runtime(domain_project, tmp_path):
    workspace, project = domain_project
    config = project / "configs/model.jsonc"
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][-1]["rulesets"] = []
    config.write_text(json.dumps(data))
    audited = audit_javascript_project(JavascriptAuditRequest(workspace,config))
    assert audited.compiled.effect_scopes["start"] == "terminal"
    assert audited.compiled.effect_scopes["end"] == "unconstrained"
    selected = next(item for item in audited.architecture["rule_selections"] if item["kind"] == "node" and item["call_path"] == ["end"])
    assert selected["selection"]["references"] == [] and selected["selection"]["replaced"] == ["vibeflow.io"]
    built = build_project_aot(ProjectBuildRequest(workspace,config,tmp_path / "dist","node","single-esm"))
    assert built.prepared.compiled.effect_scopes["end"] == "unconstrained"
    result = subprocess.run(["node","--input-type=module","--eval",f"import {{pathToFileURL}} from 'node:url'; const workflow=await import(pathToFileURL({json.dumps(str(built.entry))})); console.log(JSON.stringify(workflow.runWorkflow({{value:3}})));"],capture_output=True,text=True,check=False)
    assert result.returncode == 0 and json.loads(result.stdout) == {"result":7}
