"""Public Rule source services exercised by real TypeScript implementations."""
from __future__ import annotations

from tests.fixtures.support.plugins import resource as sdk_resource

import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.core.flow import GraphConfig, NodeSpec
from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
from vibeflow.targets.javascript.quality.rules import run_javascript_rules
from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs

ROOT = Path(__file__).resolve().parents[3]
MODEL = ('import {multiply} from "./model_helper.js";\n'
         'type Envelope = Readonly<{value: number}>;\n'
         'export function modelForward(value: number): number { return multiply(value); }\n'
         'export function run(inputs: Readonly<{"example.input": Envelope}>) {\n'
         '  return {feature: modelForward(inputs["example.input"].value)};\n'
         '}\n'
         'export class DomainTools { forward(value: number) { return multiply(value); } }\n')
LOCAL_MODEL = "\n".join(MODEL.splitlines()[:6]) + "\n"
HELPER = '// Declared helper belonging to the model implementation.\nexport function multiply(value: number): number { return value * 2; }\n'


@pytest.fixture
def source_project(tmp_path: Path) -> Path:
    toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("requires the pinned TypeScript/esbuild toolchain")
    project = tmp_path / "project"
    shutil.copytree(ROOT / "sandbox/javascript/domain_rules/project", project)
    from tests.fixtures.support.plugins import copy_sdk_inputs
    copy_sdk_inputs(ROOT / "sandbox/javascript/domain_rules/project", project)
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (project / "nodes/model.ts").write_text(MODEL, encoding="utf-8")
    (project / "nodes/model_helper.ts").write_text(HELPER, encoding="utf-8")
    (sdk_resource(project, "base_lib", "example.model_helper")).write_text(json.dumps({
        "kind": "base_lib", "id": "example.model_helper", "display_name": "Model helper",
        "description": "Owned implementation helper.", "implementations": [{
            "language": "typescript", "targets": ["node"],
            "source": {"kind": "file", "ref": "nodes/model_helper.ts"}}]}), encoding="utf-8")
    config = project / "vibeflow_project.jsonc"
    descriptor = sdk_resource(project, 'node', 'example.model')
    data = json.loads(descriptor.read_text())
    data.update({"base_libs": ["example.model_helper"], "rulesets": ["test.source"], "metadata": {"nested": {"count": 7}}})
    descriptor.write_text(json.dumps(data), encoding="utf-8")
    return project


def _rule(project: Path, name: str, source: str, *, inputs=None, outputs=None) -> None:
    (project / "rules" / (name + ".ts")).write_text(source, encoding="utf-8")
    (sdk_resource(project, "rule", "test." + name)).write_text(json.dumps({
        "kind": "rule", "id": "test." + name, "inputs": inputs or {}, "outputs": outputs or {},
        "implementations": [{"language": "typescript",
            "source": {"kind": "file", "ref": "rules/" + name + ".ts", "export": "check"}}]}), encoding="utf-8")


def _execute(project: Path, calls, relations=(), *, completed: bool = True):
    (sdk_resource(project, "ruleset", "test.source")).write_text(json.dumps({
        "kind": "ruleset", "id": "test.source", "calls": calls, "relations": relations,
        "entrypoints": {"static": [calls[-1]["id"]], "import": [], "run": []}}), encoding="utf-8")
    catalogs = load_workflow_catalogs(project, project_config=project / "vibeflow_project.jsonc", workflow_config=project / "configs/model.jsonc")
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
    assert value["text"] == LOCAL_MODEL
    ast = value["ast"]
    assert (ast["kind"], ast["path"], ast["line"], ast["column"], ast["end_line"], ast["end_column"]) == ("SourceFile", model, 1, 1, 7, 1)
    assert ast["text"] == LOCAL_MODEL
    assert [(node["kind"], node["name"]) for node in ast["children"][:4]] == [
        ("ImportDeclaration", ""), ("TypeAliasDeclaration", "Envelope"), ("FunctionDeclaration", "modelForward"), ("FunctionDeclaration", "run")]
    forward = next(symbol for symbol in value["symbols"] if symbol["qualname"] == "modelForward")
    assert (forward["kind"], forward["path"], forward["line"], forward["column"]) == ("FunctionDeclaration", model, 3, 1)
    assert forward["text"] == MODEL.splitlines()[2]
    assert not any(symbol["qualname"].startswith("DomainTools") for symbol in value["symbols"])
    assert value["imports"] == [{"specifier": "./model_helper.js", "resolved_path": helper, "path": model,
                                  "line": 1, "column": 1, "end_line": 1, "end_column": 44, "type_only": False}]
    assert value["reachable"] == [model, helper]
    assert value["functions"] == [{key: item for key, item in symbol.items() if key != "qualname"}
                                  for symbol in value["symbols"] if symbol["kind"] == "FunctionDeclaration"]
    assert value["absent"] == []
    assert value["ownership"]["node_types"] == ["example.model"]
    assert [(owner["kind"], owner["id"], owner["path"]) for owner in value["ownership"]["declared"]] == [("node", "example.model", model)]
    assert value["helper"]["node_types"] == ["example.model"]
    assert [(owner["kind"], owner["id"], owner["path"]) for owner in value["helper"]["declared"]] == [("base_lib", "example.model_helper", helper)]


def test_inherited_sdk_implementation_excludes_parent_node_declaration(source_project):
    path = source_project / "nodes/model.ts"
    path.write_text('import {defineNode} from "@vibeflow/plugin";\n'
        'function helper(value:number) {return value * 2;}\n'
        'export const parent = defineNode({type_key:"PRIVATE_PARENT_DECLARATION", contract:{},\n'
        '  run(inputs:any) {return {feature:helper(inputs["example.input"].value)};}\n'
        '});\nexport const child = defineNode({...parent, type_key:"example.model"});\n')
    node = json.loads(sdk_resource(source_project, "node", "example.model").read_text())
    node["implementations"][0]["source"]["export"] = "child.run"
    sdk_resource(source_project, "node", "example.model").write_text(json.dumps(node))
    parent = {**node, "type_key":"test.parent", "rulesets":[]}
    parent["implementations"] = [{**node["implementations"][0], "source":{"kind":"file", "ref":"nodes/model.ts", "export":"parent.run"}}]
    sdk_resource(source_project, "node", "test.parent").write_text(json.dumps(parent))
    _rule(source_project, "inheritance", '''export function check(context) {
      const file=context.facts.source_files[0], text=context.sources.text(file);
      if(text.includes("PRIVATE_PARENT_DECLARATION") || !text.includes("feature:helper")) throw Error("wrong inherited boundary");
      if(!context.sources.symbols(file).some(symbol=>symbol.name === "helper")) throw Error("helper absent");
      if(JSON.stringify(context.sources.ast(file)).includes("PRIVATE_PARENT_DECLARATION")) throw Error("parent AST exposed");
      return {findings:[]};
    }''')
    _execute(source_project,[{"id":"inheritance", "rule_id":"test.inheritance"}])


def test_explicit_empty_selections_preserve_native_syntax_errors(source_project):
    (source_project / "nodes/model.ts").write_text('export function run( {\n')
    catalogs = load_workflow_catalogs(source_project, project_config=source_project / "vibeflow_project.jsonc",
        workflow_config=source_project / "configs/model.jsonc")
    report = run_javascript_rules(GraphConfig((NodeSpec("model", "example.model", rulesets=()),), rulesets=()),
        catalogs, project_root=source_project, package_root=source_project, target="node")
    errors = [finding for finding in report.findings if finding.code == "QUALITY.SYNTAX.JAVASCRIPT"]
    assert errors and errors[0].source_location["path"] == str(source_project / "nodes/model.ts")
    assert not errors[0].definition_id


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
    assert observed["count"] == 7 and observed["text"] == LOCAL_MODEL
    assert observed["ast"]["children"][0]["text"] == MODEL.splitlines()[0]
    assert observed["functions"] == ["modelForward", "run"]
    assert "DomainTools.forward" not in observed["names"]
    assert observed["imports"][0]["resolved_path"] == str(source_project / "nodes/model_helper.ts")
    assert observed["reachable"] == [str(source_project / "nodes/model.ts"), str(source_project / "nodes/model_helper.ts")]
    assert observed["ownership"]["declared"][0]["id"] == "example.model"
    assert observed["ownership"]["node_types"] == ["example.model"]


@pytest.mark.parametrize("failure", ["source", "export"])
def test_real_rule_binding_errors_keep_declaration_implementation_and_owner(source_project: Path, failure: str) -> None:
    _rule(source_project, "missing", 'export function check() { return {findings:[]}; }\n')
    module = source_project / "rules/missing.ts"
    manifest = sdk_resource(source_project, "rule", "test.missing")
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
    assert finding["source_location"]["path"] == str(source_project / "code_plugin.ts")
    declaration_line = next(index for index, text in enumerate((source_project / "code_plugin.ts").read_text().splitlines(), 1) if '"id": "test.missing"' in text)
    assert finding["source_location"]["line"] == declaration_line
    assert finding["source_location"]["column"] == 14
    assert finding["object_id"] == "example.model"
    assert finding["details"]["call_paths"] == [["model"]]
    assert finding["details"]["implementation"] == {"path": str(module), "export": "check" if failure == "source" else "missing_check"}
    assert finding["details"]["cause_code"] == "RULE.IMPLEMENTATION"


def test_unknown_source_paths_have_no_filesystem_fallback(source_project):
    _rule(source_project, "closed", """export function check(context) {
      const denied=[];
      for (const action of [()=>context.sources.text("package.json"), ()=>context.sources.ast("package.json"),
        ()=>context.sources.symbols("package.json"), ()=>context.sources.imports("package.json"),
        ()=>context.sources.ownership("package.json"), ()=>context.sources.reachable("package.json")]) {
        try { action(); denied.push(false); } catch { denied.push(true); }
      }
      return {records:{closed:{type_id:"test.closed",value:denied}}};
    }""", outputs={"closed": "test.closed"})
    execution = _execute(source_project, [{"id":"closed", "rule_id":"test.closed"}])
    assert execution.results["closed"].records["closed"].value == (True,) * 6


def test_real_rule_dynamic_replacement_and_empty_are_independent_calls(source_project):
    _rule(source_project, "default", '''export function check(context) {
      return {records:{value:{type_id:"test.selected",value:{choice:"default",call:context.subject.call_spec.id}}}};
    }''', outputs={"value":"test.selected"})
    _rule(source_project, "dynamic", '''export function check(context) {
      const forbidden=["graph","global_graph","node_catalog","catalogs"].filter(key=>key in context.facts);
      return {records:{value:{type_id:"test.selected",value:{choice:"dynamic",call:context.subject.call_spec.id,forbidden,
        visible:Object.keys(context.facts.node_types),text:context.sources.text(context.facts.source_files[0])}}}};
    }''', outputs={"value":"test.selected"})
    sdk_resource(source_project,"ruleset","test.source").write_text(json.dumps({"kind":"ruleset","id":"test.source",
        "calls":[{"id":"check","rule_id":"test.default"}],"entrypoints":{"static":["check"],"import":[],"run":[]}}))
    catalogs = load_workflow_catalogs(source_project, project_config=source_project / "vibeflow_project.jsonc", workflow_config=source_project / "configs/model.jsonc")
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=source_project, allowed_external=set(), node_ids=frozenset({"example.model"}))
    graph = GraphConfig((NodeSpec("default", "example.model"),
        NodeSpec("dynamic", "example.model", rulesets=({"rule_id":"test.dynamic"},)),
        NodeSpec("disabled", "example.model", rulesets=())), rulesets=())
    report = run_javascript_rules(graph, catalogs, project_root=source_project, package_root=source_project, target="node", import_policy=policy)
    assert not report.findings
    values = [record.value for result in report.results["example.model"] for returned in result.results.values()
        for record in returned.records.values() if record.type_id == "test.selected"]
    assert [(value["choice"], value["call"]) for value in values] == [("default","default"), ("dynamic","dynamic"), ("dynamic","dynamic")]
    assert all(not value["forbidden"] and value["visible"] == ("example.model",) and "DomainTools" not in value["text"]
        for value in values if value["choice"] == "dynamic")


def test_variable_declarations_on_the_same_line_are_sliced_by_symbol(source_project):
    (source_project / "nodes/model.ts").write_text('export const run = () => ({feature: 1}), otherRun = () => "OTHER_NODE_SECRET";\n')
    other = json.loads(sdk_resource(source_project, "node", "example.transform").read_text())
    other["implementations"][0]["source"].update(ref="nodes/model.ts",export="otherRun")
    sdk_resource(source_project,"node","example.transform").write_text(json.dumps(other))
    _rule(source_project, "sliced", 'export function check(context) {const file=context.facts.source_files[0];return {records:{view:{type_id:"test.view",value:{text:context.sources.text(file),ast:context.sources.ast(file),symbols:context.sources.symbols(file)}}}};}', outputs={"view":"test.view"})
    execution = _execute(source_project,[{"id":"view","rule_id":"test.sliced"}])
    view = execution.to_dict()["results"]["view"]["records"]["view"]["value"]
    assert "OTHER_NODE_SECRET" not in json.dumps(view)
    assert "run" in [symbol["name"] for symbol in view["symbols"]]
    assert "otherRun" not in [symbol["name"] for symbol in view["symbols"]]


@pytest.mark.parametrize("scope", ["current_graph", "effective_subtree"])
def test_real_typescript_rule_gets_disjoint_responsibility_and_global_background(source_project, scope):
    from vibeflow.core.flow import NodesetSpec
    from vibeflow.targets.javascript.quality.rules import run_javascript_workflow_rules
    _rule(source_project,"range",'''export function check(context) {
      if (context.facts.graph.nodesets.child?.graph.nodes.length) throw new Error("Default traversal crossed the boundary");
      if (context.facts.global_graph.nodesets.child.graph.nodes.length !== 1) throw new Error("Global background is absent");
      return {records:{range:{type_id:"test.range",value:{paths:context.scope.graph_paths,boundaries:context.scope.boundaries}}}};
    }''',outputs={"range":"test.range"})
    sdk_resource(source_project,"ruleset","test.range").write_text(json.dumps({"kind":"ruleset","id":"test.range","graph_scope":scope,
        "calls":[{"id":"range","rule_id":"test.range"}],"entrypoints":{"import":["range"]}}))
    def definition(key, graph):
        return NodesetSpec(key,key,key,(),(),graph)
    child = definition("child",GraphConfig((NodeSpec("leaf","example.model",rulesets=()),)))
    middle = definition("middle",GraphConfig((NodeSpec("inner","child"),),nodesets={"child":child}))
    boundary = definition("boundary",GraphConfig((NodeSpec("inner","child"),),nodesets={"child":child},rulesets=()))
    graph = GraphConfig((NodeSpec("first","middle"),NodeSpec("second","middle"),NodeSpec("boundary","boundary")),
        nodesets={"child":child,"middle":middle,"boundary":boundary},rulesets=("test.range",))
    catalogs = load_workflow_catalogs(source_project,project_config=source_project / "vibeflow_project.jsonc",workflow_config=source_project / "configs/model.jsonc")
    nodes = run_javascript_rules(graph,catalogs,project_root=source_project,package_root=source_project,phase="import",target="node")
    report = run_javascript_workflow_rules(graph,catalogs,compiled_by_path={},node_report=nodes,project_root=source_project,package_root=source_project,phase="import",target="node")
    assert not report.findings
    executed = [result for key,values in report.results.items() if key.startswith("workflow:") for result in values]
    observed = [tuple(path) for result in executed for path in result.results["range"].records["range"].value["paths"]]
    assert observed == [(),("first",),("first","inner"),("second",),("second","inner")]
    assert len(executed) == (5 if scope == "current_graph" else 1)
    assert executed[0].scope["boundaries"] == (("boundary",),)


def test_inherited_graph_definition_preserves_leaf_call_override(source_project):
    from vibeflow.core.flow import NodesetSpec
    inner = NodesetSpec("inner","Inner","Nested",(),(),GraphConfig((NodeSpec("leaf","example.model",rulesets=()),)))
    outer = NodesetSpec("outer","Outer","Nested",(),(),GraphConfig((NodeSpec("middle","inner"),)))
    graph = GraphConfig((NodeSpec("outer","outer"),),nodesets={"inner":inner,"outer":outer},rulesets=())
    catalogs = load_workflow_catalogs(source_project,project_config=source_project / "vibeflow_project.jsonc",workflow_config=source_project / "configs/model.jsonc")
    report = run_javascript_rules(graph,catalogs,project_root=source_project,package_root=source_project,target="node")
    assert not report.findings
    assert report.results["example.model"] == ()
    assert next(item for item in report.selections if item["type_key"] == "example.model")["call_path"] == ("outer","middle","leaf")
