"""Executable domain bundle: class styling, ownership, Rule diagnostics and runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
from vibeflow.tooling.application.javascript.review import render_mermaid
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


def test_domain_bundle_category_defaults_and_actual_numerical_execution(domain_project, tmp_path: Path) -> None:
    workspace, project = domain_project
    config = project / "configs/model.jsonc"
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    node = next(item for item in audited.architecture["workflow"]["nodes"] if item["id"] == "model")
    assert node["presentation"]["values"]["fill"] == "#cceeff"
    assert node["presentation"]["sources"]["fill"] == "category"
    assert node["category"] == "model_block"
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
    declaration = project / "bundle/nodes/transform.jsonc"
    descriptor = json.loads(declaration.read_text()); descriptor["base_libs"] = ["example.transform_helper"]
    declaration.write_text(json.dumps(descriptor), encoding="utf-8")
    config = project / "vibeflow_project.jsonc"
    data = json.loads(config.read_text()); data["descriptors"]["base_lib"] = ["manifests/base_lib"]
    config.write_text(json.dumps(data), encoding="utf-8")
    manifests = project / "manifests/base_lib"; manifests.mkdir()
    (manifests / "helper.jsonc").write_text(json.dumps({"kind": "base_lib", "id": "example.transform_helper", "display_name": "Transform helper", "description": "Helper attributed to the transform Node.", "implementations": [{"language": "typescript", "targets": ["browser", "node"], "source": {"kind": "file", "ref": "nodes/transform_helper.ts"}}]}), encoding="utf-8")
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/model.jsonc"))
    finding = next(item for item in error.value.diagnostics if item["rule_id"] == "EXAMPLE.MODEL.LOCATION")
    assert finding["source_location"]["path"] == str(helper)
    assert finding["source_location"]["line"] == 2
    assert finding["details"]["call_paths"] == [["transform"]]
    assert finding["details"]["ownership"]["node_types"] == ["example.transform"]


def test_explicit_empty_node_rulesets_is_reported_unconstrained(domain_project) -> None:
    workspace, project = domain_project
    manifest = project / "bundle/nodes/model.jsonc"
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
    from vibeflow.core.flow import GraphConfig, NodeSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.frontend.facts import target_neutral_implementation_facts_from_catalog
    from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs

    _, project = domain_project
    file = project / "bundle/nodes/model.jsonc"
    data = json.loads(file.read_text()); data["rulesets"] = ["vibeflow.process", "vibeflow.io"]; file.write_text(json.dumps(data))
    catalogs = load_project_descriptor_catalogs(project, project_config=project / "vibeflow_project.jsonc")
    graph = GraphConfig(nodes=(NodeSpec("first", "example.model"), NodeSpec("second", "example.model")), rulesets=())
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
    from vibeflow.core.flow import GraphConfig, NodeSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs

    _, project = domain_project
    (project / "rules/call_policy.ts").write_text('export function check(context) { const io=context.subject.call_spec.params.io; return {records:{policy:{type_id:"vibeflow.effect_policy.v1",value:{effect_scope:io?"terminal":"none",allowed_effects:io?["terminal"]:[]}}},findings:io?[]:[{code:"EXAMPLE.STRICT",severity:"error",message:"Strict constraint stays visible"}]}; }\n')
    directory = project / "manifests/rules"; directory.mkdir()
    (directory / "call.jsonc").write_text(json.dumps({"kind": "rule", "id": "test.call_policy", "outputs": {"policy": "vibeflow.effect_policy.v1"}, "implementations": [{"language": "typescript", "targets": ["node"], "source": {"kind": "file", "ref": "rules/call_policy.ts", "export": "check"}}]}))
    directory = project / "manifests/rulesets"; directory.mkdir()
    (directory / "call.jsonc").write_text(json.dumps({"kind": "ruleset", "id": "test.call_policy", "calls": [{"id": "effect", "rule_id": "test.call_policy"}], "entrypoints": {"static": ["effect"]}}))
    file = project / "vibeflow_project.jsonc"
    data = json.loads(file.read_text()); data["descriptors"].update({"rules": ["manifests/rules"], "rulesets": ["manifests/rulesets"]}); file.write_text(json.dumps(data))
    file = project / "bundle/nodes/model.jsonc"
    data = json.loads(file.read_text()); data["rulesets"] = ["test.call_policy"]; file.write_text(json.dumps(data))
    catalogs = load_project_descriptor_catalogs(project, project_config=project / "vibeflow_project.jsonc")
    graph = GraphConfig(nodes=(NodeSpec("strict", "example.model", params={"io": False}), NodeSpec("io", "example.model", params={"io": True})), rulesets=())
    report = run_javascript_rules(graph, catalogs, project_root=project, package_root=project, target="node")
    assert report.policies["example.model"]["effect_scope"] == "mixed"
    assert report.call_effect_scopes == {("example.model", "strict"): "none", ("example.model", "io"): "terminal"}
    assert [item.code for item in report.findings] == ["EXAMPLE.STRICT"]
    records = report.to_dict()["call_effect_policies"]
    assert all(item["node_type"] == "example.model" for item in records)
    assert all(record["definition_id"] == "test.call_policy" and record["scope"] == "call" for item in records for record in item["records"])
    single = run_javascript_rules(GraphConfig(nodes=(NodeSpec("io", "example.model", params={"io": True}),), rulesets=()), catalogs, project_root=project, package_root=project, target="node")
    assert single.policies["example.model"]["effect_scope"] == "mixed"
    assert single.call_effect_scopes == {("example.model", "io"): "terminal"}


def _select_scoped_file_rule(project: Path, scope: str, *, implementation: str = "builtin") -> tuple[Path, Path]:
    helper = project / "nodes/model_helper.ts"
    helper.write_text("export function multiply(value: number): number { return value * 2; }\n" + "\n" * 12)
    model = project / "nodes/model.ts"
    model.write_text('import {multiply} from "./model_helper.ts";\n' + model.read_text().replace("return value * 2", "return multiply(value)"))
    # Unused code has neither a descriptor nor a place in this source scope.
    (project / "unused.ts").write_text("function broken( {\n" + "\n" * 1000)
    rule_id = "vibeflow.quality.files"
    if implementation != "builtin":
        rule_id = "test.files"
        directory = project / "manifests/rules"; directory.mkdir()
        declaration = {"kind": "rule", "id": rule_id,
            "params_schema": {"max_file_lines": {"type": "integer"}, "warn_file_lines": {"type": "integer"}},
            "params_defaults": {"max_file_lines": 8, "warn_file_lines": 8}}
        if implementation == "alias":
            declaration["handler"] = "vibeflow.quality.files"
        else:
            (project / "rules/files.ts").write_text('export function check(context, inputs, params) { return {findings:context.facts.project_facts.files.filter(file=>file.lines>params.max_file_lines).map(file=>({code:"TEST.CLOSURE.LINES",severity:"error",message:"Reached helper exceeds the chosen limit",source_location:{path:context.facts.project_facts.root+"/"+file.path,line:1},details:{limit:params.max_file_lines}}))}; }\n')
            declaration["implementations"] = [{"language": "typescript", "targets": ["node"], "source": {"kind": "file", "ref": "rules/files.ts", "export": "check"}}]
        (directory / "files.jsonc").write_text(json.dumps(declaration))
    ruleset = {"kind": "ruleset", "id": "test.scope", "calls": [{"id": "files", "rule_id": "vibeflow.quality.files", "params": {"max_file_lines": 8, "warn_file_lines": 8}}],
               "entrypoints": {"static": ["files"], "import": [], "run": []}}
    if implementation != "builtin":
        ruleset["relations"] = [{"source": "$self", "target": "files", "kind": "overrides", "replace_rule": rule_id}]
    directory = project / "manifests/rulesets"; directory.mkdir()
    resource = directory / "scope.jsonc"; resource.write_text(json.dumps(ruleset))
    file = project / "vibeflow_project.jsonc"
    data = json.loads(file.read_text()); data["descriptors"]["rulesets"] = ["manifests/rulesets"]
    if implementation != "builtin":
        data["descriptors"]["rules"] = ["manifests/rules"]
    file.write_text(json.dumps(data))
    for name in ("model", "transform", "boundary"):
        file = project / "bundle/nodes" / (name + ".jsonc")
        data = json.loads(file.read_text()); data["rulesets"] = ["test.scope"] if scope == "node" and name == "model" else []; file.write_text(json.dumps(data))
    config = project / "configs/model.jsonc"
    data = json.loads(config.read_text()); data["rulesets"] = ["test.scope"] if scope == "workflow" else []; config.write_text(json.dumps(data))
    return resource, helper


@pytest.mark.parametrize("scope", ["node", "workflow"])
def test_selected_file_rule_uses_real_closure_and_explicit_overrides(domain_project, tmp_path, capsys, scope) -> None:
    from vibeflow.core.quality import QualityThresholds
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
        file = project / "bundle/nodes/model.jsonc"
    else:
        file = config
    data = json.loads(file.read_text()); data["rulesets"] = []; file.write_text(json.dumps(data))
    unconstrained = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    assert unconstrained.rule_report.results[key] == ()


@pytest.mark.parametrize("implementation", ["alias", "replacement"])
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


@pytest.mark.parametrize("state", ["unavailable", "failed"])
@pytest.mark.parametrize("phase", ["import", "static"])
def test_formal_rule_state_failure_is_rejected_before_later_entrances(domain_project, tmp_path, capsys, state, phase) -> None:
    from vibeflow.tooling.application.cli import main

    workspace, project = domain_project
    static_marker = project / "static-rule-ran"
    business_marker = project / "business-node-ran"
    model = project / "nodes/model.ts"
    model.write_text('import {writeFileSync} from "node:fs"; writeFileSync(' + json.dumps(str(business_marker)) + ',"ran");\n' + model.read_text())
    (project / "rules/status.ts").write_text('import {writeFileSync} from "node:fs"; export function check(context) { if(context.phase===' + json.dumps(phase) + ') return {state:' + json.dumps(state) + ',findings:' + ('[{code:"EXAMPLE.STATUS.WARNING",severity:"warning",message:"Incomplete with warning"}]' if state == "failed" else '[]') + '}; writeFileSync(' + json.dumps(str(static_marker)) + ',"later phase ran"); return {findings:[]}; }\n')
    directory = project / "manifests/rules"; directory.mkdir()
    (directory / "status.jsonc").write_text(json.dumps({"kind": "rule", "id": "test.status", "implementations": [{"language": "typescript", "targets": ["node"], "source": {"kind": "file", "ref": "rules/status.ts", "export": "check"}}]}))
    directory = project / "manifests/rulesets"; directory.mkdir()
    (directory / "status.jsonc").write_text(json.dumps({"kind": "ruleset", "id": "test.status", "calls": [{"id": "check", "rule_id": "test.status"}], "entrypoints": {"import": ["check"] if phase == "import" else [], "static": ["check"]}}))
    file = project / "vibeflow_project.jsonc"
    data = json.loads(file.read_text()); data["descriptors"].update({"rules": ["manifests/rules"], "rulesets": ["manifests/rulesets"]}); file.write_text(json.dumps(data))
    file = project / "bundle/nodes/model.jsonc"
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
    rule = project / "rules/wire.ts"
    rule.write_text('import {writeFileSync} from "node:fs"; export function check(context, inputs, params) { writeFileSync(params.file, "rule ran"); const symbols=context.sources.symbols(context.facts.source_files[0]); return {records:{value:{type_id:"example.wire.v1",value:{abi:context.abiVersion, supplied:inputs.prior.value, parameter:params.limit, names:symbols.map(s=>s.name), imports:context.sources.imports(context.facts.source_files[0]).map(s=>s.resolved_path)}}},findings:[]}; }', encoding="utf-8")
    helper = project / "nodes/import_helper.ts"
    helper.write_text("export const value=1;\n")
    source = project / "nodes/model.ts"
    source.write_text('import {value} from "./import_helper.js";\n' + source.read_text())
    output = project / "rule-output.txt"
    with JavascriptPluginSession() as session:
        session.open_rule("rule:wire", rule={"id": "example.wire", "module": str(rule), "export": "check"}, package_root=project)
        returned = session.evaluate_rule("rule:wire", context={"facts": {"source_files": [str(project / "nodes/model.ts")]}, "subject": {}, "scope": {}, "phase": "static", "target": "node"}, inputs={"prior": {"type_id": "example.input.v1", "value": 5}}, params={"limit": 9, "file": str(output)})
    value = returned["records"]["value"]["value"]
    assert (value["abi"], value["supplied"], value["parameter"]) == ("vibeflow.rule.v1", 5, 9)
    assert "modelForward" in value["names"]
    assert output.read_text() == "rule ran"
    assert value["imports"] == [str(helper)]


@pytest.mark.parametrize(("scope", "counts"), [("call", [1, 2]), ("source", [1, 1])])
def test_rule_scope_keeps_call_identity_and_caches_source_snapshots(domain_project, scope, counts) -> None:
    from vibeflow.core.flow import GraphConfig, NodeSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_rules
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
    from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs

    _, project = domain_project
    rule = project / "rules/scope.ts"
    rule.write_text('let count=0; export function check(context) { console.log("Rule log"); return {records:{count:{type_id:"example.count.v1",value:{count:++count, call:context.subject.call_spec?.id ?? null, rule:context.subject.rule_call_id}}},findings:[{code:"EXAMPLE.SCOPE",severity:"warning",message:"Scope proof",source_location:{path:context.facts.source_files[0],line:1}}]}; }\n', encoding="utf-8")
    directory = project / "manifests/rules"; directory.mkdir()
    (directory / "scope.jsonc").write_text(json.dumps({"kind": "rule", "id": "test.scope", "scope": scope, "outputs": {"count": "example.count.v1"}, "implementations": [{"language": "typescript", "targets": ["node"], "source": {"kind": "file", "ref": "rules/scope.ts", "export": "check"}}]}))
    directory = project / "manifests/rulesets"; directory.mkdir()
    (directory / "scope.jsonc").write_text(json.dumps({"kind": "ruleset", "id": "test.scope", "calls": [{"id": "check", "rule_id": "test.scope"}], "entrypoints": {"static": ["check"]}}))
    file = project / "vibeflow_project.jsonc"
    data = json.loads(file.read_text()); data["descriptors"].update({"rules": ["manifests/rules"], "rulesets": ["manifests/rulesets"]}); file.write_text(json.dumps(data))
    file = project / "bundle/nodes/model.jsonc"
    data = json.loads(file.read_text()); data["rulesets"] = ["test.scope"]; file.write_text(json.dumps(data))
    catalogs = load_project_descriptor_catalogs(project, project_config=project / "vibeflow_project.jsonc")
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project, allowed_external=set(), node_ids=frozenset({"example.model"}))
    graph = GraphConfig(nodes=(NodeSpec("first", "example.model"), NodeSpec("second", "example.model")), rulesets=())
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
