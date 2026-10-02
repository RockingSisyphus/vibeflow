"""Public Rule source services exercised by real TypeScript implementations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.core.flow import GraphConfig, NodeSpec
from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
from vibeflow.targets.javascript.quality.rules import run_javascript_rules
from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs

ROOT = Path(__file__).resolve().parents[3]
MODEL = ('import {multiply} from "./model_helper.js";\n'
         'type Envelope = Readonly<{value: number}>;\n'
         'export function modelForward(value: number): number { return multiply(value); }\n'
         'export function run(inputs: Readonly<{"example.input": Envelope}>) {\n'
         '  return {feature: modelForward(inputs["example.input"].value)};\n'
         '}\n'
         'export class DomainTools { forward(value: number) { return multiply(value); } }\n')
HELPER = '// Declared helper belonging to the model implementation.\nexport function multiply(value: number): number { return value * 2; }\n'


@pytest.fixture
def source_project(tmp_path: Path) -> Path:
    toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("requires the pinned TypeScript/esbuild toolchain")
    project = tmp_path / "project"
    shutil.copytree(ROOT / "sandbox/javascript/domain_rules/project", project)
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (project / "nodes/model.ts").write_text(MODEL, encoding="utf-8")
    (project / "nodes/model_helper.ts").write_text(HELPER, encoding="utf-8")
    directory = project / "manifests/base_lib"
    directory.mkdir()
    (directory / "helper.jsonc").write_text(json.dumps({
        "kind": "base_lib", "id": "example.model_helper", "display_name": "Model helper",
        "description": "Owned implementation helper.", "implementations": [{
            "language": "typescript", "targets": ["node"],
            "source": {"kind": "file", "ref": "nodes/model_helper.ts"}}]}), encoding="utf-8")
    config = project / "vibeflow_project.jsonc"
    data = json.loads(config.read_text())
    data["descriptors"].update({"base_lib": ["manifests/base_lib"], "rules": ["manifests/rules"], "rulesets": ["manifests/rulesets"]})
    config.write_text(json.dumps(data), encoding="utf-8")
    for directory in ("rules", "rulesets"):
        (project / "manifests" / directory).mkdir()
    descriptor = project / "bundle/nodes/model.jsonc"
    data = json.loads(descriptor.read_text())
    data.update({"base_libs": ["example.model_helper"], "rulesets": ["test.source"], "metadata": {"nested": {"count": 7}}})
    descriptor.write_text(json.dumps(data), encoding="utf-8")
    return project


def _rule(project: Path, name: str, source: str, *, inputs=None, outputs=None) -> None:
    (project / "rules" / (name + ".ts")).write_text(source, encoding="utf-8")
    (project / "manifests/rules" / (name + ".jsonc")).write_text(json.dumps({
        "kind": "rule", "id": "test." + name, "inputs": inputs or {}, "outputs": outputs or {},
        "implementations": [{"language": "typescript", "targets": ["node"],
            "source": {"kind": "file", "ref": "rules/" + name + ".ts", "export": "check"}}]}), encoding="utf-8")


def _execute(project: Path, calls, relations=(), *, completed: bool = True):
    (project / "manifests/rulesets/source.jsonc").write_text(json.dumps({
        "kind": "ruleset", "id": "test.source", "calls": calls, "relations": relations,
        "entrypoints": {"static": [calls[-1]["id"]], "import": [], "run": []}}), encoding="utf-8")
    catalogs = load_project_descriptor_catalogs(project, project_config=project / "vibeflow_project.jsonc")
    import_policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=project, allowed_external=set(), node_ids=frozenset({"example.model"}))
    report = run_javascript_rules(GraphConfig(nodes=(NodeSpec("model", "example.model"),), rulesets=()),
                                  catalogs, project_root=project, package_root=project, target="node", import_policy=import_policy)
    if completed:
        assert not report.findings, [finding.to_dict() for finding in report.findings]
    execution = next(result for result in report.results["example.model"] if result.plan.entrypoint == "static")
    assert execution.status == ("PASS" if completed else "ERROR")
    return execution


def test_real_rule_reads_all_public_source_services_and_exact_locations(source_project: Path) -> None:
    _rule(source_project, "api", '''export function check(context) {
      const file=context.facts.source_files[0];
      return {records:{api:{type_id:"test.source_api.v1",value:{
        text:context.sources.text(file), ast:context.sources.ast(file), symbols:context.sources.symbols(file),
        imports:context.sources.imports(file), reachable:context.sources.reachable(file),
        ownership:context.sources.ownership(file), helper:context.sources.ownership(context.sources.imports(file)[0].resolved_path),
        functions:context.sources.nodes(file,"FunctionDeclaration"), absent:context.sources.nodes(file,"InterfaceDeclaration")
      }}}};
    }''', outputs={"api": "test.source_api.v1"})
    execution = _execute(source_project, [{"id": "api", "rule_id": "test.api"}])
    value = execution.to_dict()["results"]["api"]["records"]["api"]["value"]
    model, helper = str(source_project / "nodes/model.ts"), str(source_project / "nodes/model_helper.ts")
    assert value["text"] == MODEL
    ast = value["ast"]
    assert (ast["kind"], ast["path"], ast["line"], ast["column"], ast["end_line"], ast["end_column"]) == ("SourceFile", model, 1, 1, 8, 1)
    assert ast["text"] == MODEL.rstrip("\n") + "\n"
    assert [(node["kind"], node["name"]) for node in ast["children"][:4]] == [
        ("ImportDeclaration", ""), ("TypeAliasDeclaration", "Envelope"), ("FunctionDeclaration", "modelForward"), ("FunctionDeclaration", "run")]
    forward = next(symbol for symbol in value["symbols"] if symbol["qualname"] == "modelForward")
    assert (forward["kind"], forward["path"], forward["line"], forward["column"]) == ("FunctionDeclaration", model, 3, 1)
    assert forward["text"] == MODEL.splitlines()[2]
    assert any(symbol["qualname"] == "DomainTools.forward" and symbol["kind"] == "MethodDeclaration" for symbol in value["symbols"])
    assert value["imports"] == [{"specifier": "./model_helper.js", "resolved_path": helper, "path": model,
                                  "line": 1, "column": 1, "end_line": 1, "end_column": 44}]
    assert value["reachable"] == [model, helper]
    assert value["functions"] == [{key: item for key, item in symbol.items() if key != "qualname"}
                                  for symbol in value["symbols"] if symbol["kind"] == "FunctionDeclaration"]
    assert value["absent"] == []
    assert value["ownership"]["node_types"] == ["example.model"]
    assert [(owner["kind"], owner["id"], owner["path"]) for owner in value["ownership"]["declared"]] == [("node", "example.model", model)]
    assert value["helper"]["node_types"] == ["example.model"]
    assert [(owner["kind"], owner["id"], owner["path"]) for owner in value["helper"]["declared"]] == [("base_lib", "example.model_helper", helper)]


MUTATIONS = '''
  const file=context.facts.source_files[0], blocked=[];
  function attempt(action) { try { action(); blocked.push(false); } catch(error) { blocked.push(error instanceof TypeError); } }
  const ast=context.sources.ast(file), symbols=context.sources.symbols(file), functions=context.sources.nodes(file,"FunctionDeclaration");
  const imports=context.sources.imports(file), reachable=context.sources.reachable(file), ownership=context.sources.ownership(file);
  attempt(()=>context.facts.node_types["example.model"].metadata.nested.count=99);
  attempt(()=>context.facts.sources[0].text="corrupt snapshot");
  attempt(()=>ast.children[0].text="corrupt AST"); attempt(()=>ast.children.push({}));
  attempt(()=>symbols[0].name="corrupt symbol"); attempt(()=>functions[0].name="corrupt function");
  attempt(()=>imports[0].resolved_path="corrupt import"); attempt(()=>reachable.push("corrupt path"));
  attempt(()=>ownership.declared[0].id="corrupt owner"); attempt(()=>ownership.node_types.push("corrupt type"));
  attempt(()=>context.sources.text=()=>"corrupt service");
'''


def test_two_real_rules_cannot_mutate_shared_facts_records_or_source_results(source_project: Path) -> None:
    _rule(source_project, "mutator", 'export function check(context) {\n' + MUTATIONS + '''
      return {records:{seed:{type_id:"test.seed.v1",value:{nested:{count:7,values:[1,2]},blocked}}}};
    }''', outputs={"seed": "test.seed.v1"})
    _rule(source_project, "observer", 'export function check(context,inputs) {\n' + MUTATIONS + '''
      attempt(()=>inputs.seed.value.nested.count=99); attempt(()=>inputs.seed.value.nested.values.push(3));
      return {records:{evidence:{type_id:"test.observed.v1",value:{blocked,prior:inputs.seed.value,
        count:context.facts.node_types["example.model"].metadata.nested.count,text:context.sources.text(file),
        ast:context.sources.ast(file),names:context.sources.symbols(file).map(symbol=>symbol.qualname),
        functions:context.sources.nodes(file,"FunctionDeclaration").map(node=>node.name),
        imports:context.sources.imports(file),reachable:context.sources.reachable(file),ownership:context.sources.ownership(file)}}}};
    }''', inputs={"seed": "test.seed.v1"}, outputs={"evidence": "test.observed.v1"})
    execution = _execute(source_project, [{"id": "mutator", "rule_id": "test.mutator"}, {"id": "observer", "rule_id": "test.observer"}],
                         [{"source": "observer", "target": "mutator", "kind": "requires", "bindings": {"seed": "seed"}}])
    assert execution.executed == ("mutator", "observer")
    records = execution.to_dict()["results"]
    prior = records["mutator"]["records"]["seed"]["value"]
    observed = records["observer"]["records"]["evidence"]["value"]
    assert prior["nested"] == {"count": 7, "values": [1, 2]}
    assert prior["blocked"] == [True] * 11
    assert observed["blocked"] == [True] * 13
    assert observed["prior"] == prior
    assert observed["count"] == 7 and observed["text"] == MODEL
    assert observed["ast"]["children"][0]["text"] == MODEL.splitlines()[0]
    assert observed["functions"] == ["modelForward", "run"]
    assert "DomainTools.forward" in observed["names"]
    assert observed["imports"][0]["resolved_path"] == str(source_project / "nodes/model_helper.ts")
    assert observed["reachable"] == [str(source_project / "nodes/model.ts"), str(source_project / "nodes/model_helper.ts")]
    assert observed["ownership"]["declared"][0]["id"] == "example.model"
    assert observed["ownership"]["node_types"] == ["example.model"]


@pytest.mark.parametrize("failure", ["source", "export"])
def test_real_rule_binding_errors_keep_declaration_implementation_and_owner(source_project: Path, failure: str) -> None:
    _rule(source_project, "missing", 'export function check() { return {findings:[]}; }\n')
    module = source_project / "rules/missing.ts"
    manifest = source_project / "manifests/rules/missing.jsonc"
    if failure == "source":
        module.unlink()
    else:
        data = json.loads(manifest.read_text())
        data["implementations"][0]["source"]["export"] = "missing_check"
        manifest.write_text(json.dumps(data))
    execution = _execute(source_project, [{"id": "check", "rule_id": "test.missing"}], completed=False)
    assert execution.executed == ("check",)
    assert execution.results["check"].state == "failed"
    finding = execution.findings[0].to_dict()
    assert finding["code"] == "RULE.EXECUTION" and finding["definition_id"] == "test.missing"
    assert finding["source_location"] == {"path": str(manifest), "line": 1, "column": 1}
    assert finding["object_id"] == "example.model"
    assert finding["details"]["call_paths"] == [["model"]]
    assert finding["details"]["implementation"] == {"path": str(module), "export": "check" if failure == "source" else "missing_check"}
    assert finding["details"]["cause_code"] == "RULE.IMPLEMENTATION"
