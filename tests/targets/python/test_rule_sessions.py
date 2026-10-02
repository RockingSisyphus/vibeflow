"""Public source snapshots and actual invocation records stay isolated."""

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fixtures.support.declarations import node_declaration
from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec
from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleCall, RuleContext, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor
from vibeflow.targets.python.project import NodeContract, NodeInfo, NodeRegistry
from vibeflow.targets.python.project.registry import NodeRegistryQueries, NodeRegistryError
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
from vibeflow.targets.python.quality.rules.helpers import source_policy
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def _registry(tmp_path, rules, ruleset):
    path = tmp_path / "nodes.py"
    path.write_text('class Leaf:\n    def run_pure(self, inputs, params):\n        return {}\n')
    descriptor = node_declaration(NodeInfo("test.leaf", "Leaf", "test", "Checks one leaf.", "1", "process"),
        NodeContract(), rulesets=(ruleset.id,))
    registry = NodeRegistry()
    registry.register(descriptor)
    registry.source_locations = {descriptor.type_key:(path,"Leaf","project",tmp_path)}
    registry.source_roots = (tmp_path,)
    registry.source_root_ids = {tmp_path:"project"}
    registry.rule_catalogs = (SimpleNamespace(rules=rules,rulesets=(ruleset,)),)
    return registry


def _repeated_graph():
    inner = GraphConfig(nodes=(NodeSpec("leaf","test.leaf",params={"marker":7}),),rulesets=())
    definition = NodesetSpec(type_key="test.inner",display_name="Inner",description="One leaf.",requires=(),provides=(),graph=inner)
    return GraphConfig(nodes=(NodeSpec("first","test.inner"),NodeSpec("second","test.inner")),
        nodesets={definition.type_key:definition},rulesets=())


def test_source_rule_ast_edits_do_not_change_later_rule_facts(tmp_path):
    writer = RuleDescriptor("test.edit",scope="source")
    reader = RuleDescriptor("test.read",scope="source")
    ruleset = RulesetDescriptor("test.inspect",calls=(RuleCall("edit",rule_id=writer.id),RuleCall("read",rule_id=reader.id)),
        relations=(RuleRelation("read","edit","requires"),))
    registry = _registry(tmp_path,(writer,reader),ruleset)
    sources = collect_workflow_source_context(registry,_repeated_graph())
    observations = []
    def edit(context,inputs,params):
        source = context.require("source_context")
        source.files[0].tree.body.clear()
        source.symbol(source.nodes[0].path,"Leaf").node.body.clear()
        assert "call" not in context.facts and "call_id" not in context.subject
        return RuleResult()
    def read(context,inputs,params):
        source = context.require("source_context")
        observations.append((len(source.files[0].tree.body),len(source.symbol(source.nodes[0].path,"Leaf").node.body)))
        return RuleResult()
    report = execute_python_node_rules(registry,sources,extra_handlers={writer.id:edit,reader.id:read})
    assert report.findings == ()
    assert observations == [(1,1)]
    assert len(report.executions) == 2
    assert report.executions[1].executed == ()
    assert sources.calls[1].call_path == ("first","leaf")
    assert sources.calls[3].call_path == ("second","leaf")


def test_call_rules_receive_each_repeated_nodeset_invocation_and_keep_effect_records(tmp_path):
    rule = RuleDescriptor("test.policy",scope="call",outputs={"policy":EFFECT_POLICY_TYPE})
    ruleset = RulesetDescriptor("test.policy",calls=(RuleCall("policy",rule_id=rule.id),))
    registry = _registry(tmp_path,(rule,),ruleset)
    sources = collect_workflow_source_context(registry,_repeated_graph())
    observed = []
    def policy(context,inputs,params):
        call = context.require("call")
        observed.append((context.subject["call_id"],call.call_path,call.local_id,call.params["marker"]))
        return RuleResult(records={"policy":RuleRecord(EFFECT_POLICY_TYPE,{"effect_scope":"terminal" if call.call_path[0] == "first" else "none"})})
    report = execute_python_node_rules(registry,sources,extra_handlers={rule.id:policy})
    assert observed == [("first/leaf",("first","leaf"),"leaf",7),("second/leaf",("second","leaf"),"leaf",7)]
    assert registry.effect_scope("test.leaf") == "mixed"
    assert report.call_effect_scopes == {("nodeset:test.inner","first/leaf"):"terminal",("nodeset:test.inner","second/leaf"):"none"}
    for key,records in report.call_effect_policies.items():
        assert records[0]["definition_id"] == rule.id
        assert records[0]["rule_call_id"] == "policy"
        assert "/".join(records[0]["call_path"]) == key[1]
    registry.register(replace(registry.descriptor("test.leaf"),rulesets=()),overwrite=True)
    unchecked = execute_python_node_rules(registry,replace(sources,nodes=(replace(sources.nodes[0],descriptor=registry.descriptor("test.leaf")),)))
    assert unchecked.executions == ()
    assert unchecked.effect_scopes["test.leaf"] == "unconstrained"
    assert registry.effect_scope("test.leaf") == "unconstrained"


def test_nested_policy_override_preserves_context_defaults_and_registry_queries_are_readonly(tmp_path):
    base = PurityPolicy(max_source_lines=1234,max_functions=9,allowed_base_lib_modules=("base_lib.custom",))
    changed = source_policy(RuleContext(facts={"purity_policy":base}),{"policy":{"node_source":{"max_lines":20}}})
    assert changed.max_source_lines == 20
    assert changed.max_functions == 9
    assert changed.allowed_base_lib_modules == ("base_lib.custom",)
    registry = _registry(tmp_path,(),RulesetDescriptor("test.empty"))
    descriptor = registry.descriptor("test.leaf")
    registry.register(replace(descriptor,contract=replace(descriptor.contract,
        params_schema={"value":{"type":"number"}},params_defaults={"value":1})),overwrite=True)
    queries = NodeRegistryQueries(registry)
    with pytest.raises(NodeRegistryError):
        queries.merge_config("test.leaf",{"value":"bad"})
    with pytest.raises(TypeError):
        queries.get_config_spec("test.leaf").defaults["value"] = 2
    with pytest.raises(AttributeError):
        queries.source_context_snapshot = None
    assert not hasattr(queries,"register") and not hasattr(queries,"get")


@pytest.mark.parametrize("state",["failed","unavailable"])
def test_incomplete_rule_with_only_warning_is_an_error_in_formal_check(tmp_path,state):
    from vibeflow.core.findings import HealthFinding
    rule = RuleDescriptor("test.incomplete")
    ruleset = RulesetDescriptor("test.incomplete",calls=(RuleCall("check",rule_id=rule.id),),entrypoints={"static":("check",),"import":("check",)})
    registry = _registry(tmp_path,(rule,),ruleset)
    registry.rule_handler_loader = lambda plan: {rule.id:lambda context,inputs,params:RuleResult(state=state,
        findings=(HealthFinding(rule_id="TEST.WARNING",severity="warning",message="Insufficient facts."),))}
    sources = collect_workflow_source_context(registry,GraphConfig(nodes=(NodeSpec("leaf","test.leaf"),),rulesets=()))
    report = execute_python_node_rules(registry,sources,phase="import")
    assert any(item.code == "TEST.WARNING" for item in report.findings)
    error = next(item for item in report.findings if item.code == "RULE.SOURCE.UNAVAILABLE")
    assert error.severity == "error" and error.definition_id == rule.id
    assert error.details["state"] == state
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    workflow = validate_graph_health(GraphConfig(nodes=(),rulesets=(ruleset.id,)),registry=registry)
    assert workflow.status == "FAIL"
    assert any(item.code == "RULE.EXECUTION.UNAVAILABLE" for item in workflow.errors)


def test_public_imports_resolve_alias_relative_and_package_module_without_new_scan(tmp_path,monkeypatch):
    from vibeflow.targets.python.quality import PythonSourceFile,PythonSourceImport
    from vibeflow.targets.python.quality.source_context import PythonSourceNode,build_python_source_context
    node_file = tmp_path / "pkg/node.py"
    helper_file = tmp_path / "pkg/helpers.py"
    text = ('from .helpers import transform as alias\nfrom . import helpers as local\nimport pkg.helpers as direct\n'
        'class Leaf:\n    def run_pure(self, inputs, params):\n        return alias(local.transform(direct.transform(inputs)))\n')
    parses = []
    original = ast.parse
    def parse(*args,**kwargs):
        parses.append(args[0])
        return original(*args,**kwargs)
    monkeypatch.setattr(ast,"parse",parse)
    files = (PythonSourceFile.parse(str(node_file),"pkg.node",text),
        PythonSourceFile.parse(str(helper_file),"pkg.helpers","def transform(value):\n    return value\n"))
    descriptor = node_declaration(NodeInfo("test.leaf","Leaf","test","A source Node.","1","process"),NodeContract())
    context = build_python_source_context((PythonSourceNode(descriptor,str(node_file),"Leaf"),),files)
    assert len(parses) == 2
    assert all(isinstance(item,PythonSourceImport) for item in context.imports)
    assert [(item.specifier,item.module,item.symbol,item.alias) for item in context.imports] == [
        (".helpers","pkg.helpers","transform","alias"),(".","pkg","","local"),("pkg.helpers","pkg.helpers","","direct")]
    assert all(item.resolved_path == str(helper_file) and item.path == str(node_file) for item in context.imports)
    assert [item.line for item in context.imports] == [1,2,3]
    assert all(item.column == 1 for item in context.imports)
    assert len([item for item in context.references if item.target == str(helper_file)+":transform"]) == 3
    assert {item.name for item in context.helpers("test.leaf")} == {"Leaf.run_pure","transform"}
    for file in context.files:
        file.tree.body.clear()
    assert len(parses) == 2 and len(context.files[0].tree.body) == 1


@pytest.mark.parametrize("state",["failed","unavailable"])
def test_import_rule_incomplete_warning_prevents_real_implementation_import(tmp_path,state):
    from vibeflow.core.findings import HealthFinding
    from vibeflow.tooling.application.python.project.declarations import _bind_node,PythonSourceRuleError
    rule = RuleDescriptor("test.before_import")
    selection = RulesetDescriptor("test.before_import",calls=(RuleCall("check",rule_id=rule.id),),entrypoints={"import":("check",)})
    registry = _registry(tmp_path,(rule,),selection)
    marker = tmp_path / "imported.txt"
    source = tmp_path / "nodes.py"
    source.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nclass Leaf:\n    def run_pure(self,inputs,params):\n        return {{}}\n')
    registry.rule_handler_loader = lambda plan: {rule.id:lambda context,inputs,params:RuleResult(state=state,
        findings=(HealthFinding(rule_id="TEST.WARNING",severity="warning",message="Import facts incomplete."),))}
    registry.register(registry.descriptor("test.leaf"),loader=lambda:_bind_node(registry,"test.leaf",(tmp_path,)),overwrite=True)
    with pytest.raises(PythonSourceRuleError) as error:
        registry.get("test.leaf")
    assert error.value.findings[0].code == "RULE.SOURCE.UNAVAILABLE"
    assert not marker.exists()


def test_explicit_nodeset_topic_inherits_project_defaults_and_call_override_wins(tmp_path):
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    rule_id = "vibeflow.graph.nodesets"
    selection = RulesetDescriptor("test.depth",calls=(RuleCall("depth",rule_id=rule_id),))
    registry = _registry(tmp_path,(),selection)
    graph = GraphConfig(nodes=(),rulesets=(selection.id,))
    report = validate_graph_health(graph,registry=registry,nodeset_max_depth=7)
    plan = report.info["rule_executions"][0]["plan"]
    assert plan["calls"][0]["params"]["nodeset_max_depth"] == 7
    override = replace(selection,calls=(RuleCall("depth",rule_id=rule_id,params={"nodeset_max_depth":2}),))
    registry.rule_catalogs = (SimpleNamespace(rules=(),rulesets=(override,)),)
    report = validate_graph_health(graph,registry=registry,nodeset_max_depth=7)
    assert report.info["rule_executions"][0]["plan"]["calls"][0]["params"]["nodeset_max_depth"] == 2


def test_source_project_quality_facts_reuse_ast_and_resolved_import_scope(tmp_path,monkeypatch):
    from vibeflow.targets.python.quality import PythonSourceFile,source_context_quality_facts
    from vibeflow.targets.python.quality.source_context import build_python_source_context
    files = (
        PythonSourceFile.parse(str(tmp_path / "pkg/node.py"),"pkg.node",
            "from .helpers import transform as alias\nclass Leaf:\n    def run_pure(self,inputs,params):\n        return alias(inputs)\n"),
        PythonSourceFile.parse(str(tmp_path / "pkg/helpers.py"),"pkg.helpers","def transform(value):\n    return value\n"),
    )
    snapshot = build_python_source_context((),files)
    (tmp_path / "orphan.py").write_text("\n"*1000)
    monkeypatch.setattr(ast,"parse",lambda *args,**kwargs:pytest.fail("SourceContext facts must reuse its parsed AST"))
    facts = source_context_quality_facts(snapshot)
    assert [item.path for item in facts.files] == ["helpers.py","node.py"]
    node = next(item for item in facts.files if item.module == "pkg.node")
    assert node.function_count == 1 and node.class_count == 1
    assert node.imports == ("pkg.helpers",)
    assert node.import_sites[0].line == 1 and node.import_sites[0].imported == "pkg.helpers"
    assert all("orphan" not in item.path for item in facts.files)


@pytest.mark.parametrize("selection_owner",["node","workflow"])
def test_selected_project_file_rule_has_real_cli_params_and_current_source_scope(tmp_path,capsys,selection_owner):
    import json
    from tests.fixtures.support.strict_support import cli_main
    from tests.fixtures.support.rule_inspection import node_document
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.core import build_workspace_node_registry
    from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context
    from vibeflow.tooling.project.graph_config import parse_graph_config
    declarations = tmp_path / "manifests/nodes"
    rulesets = tmp_path / "manifests/rulesets"
    declarations.mkdir(parents=True)
    rulesets.mkdir()
    (tmp_path / "leaf.py").write_text("class Leaf:\n    def run_pure(self, inputs, params):\n        return {}\n")
    (tmp_path / "orphan.py").write_text("\n"*1000)
    node = node_document(type_key="test.leaf",class_name="Leaf",contract={},rulesets=["test.files"] if selection_owner == "node" else [])
    node["implementations"][0]["source"]["ref"] = "leaf.py"
    (declarations / "leaf.jsonc").write_text(json.dumps(node))
    selection = {"kind":"ruleset","id":"test.files","calls":[
        {"id":"files","rule_id":"vibeflow.quality.files","params":{"max_file_lines":2,"warn_file_lines":1000}}]}
    manifest = rulesets / "files.jsonc"
    manifest.write_text(json.dumps(selection))
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python","quality_enabled":False,
        "descriptors":{"nodes":["manifests/nodes"],"rulesets":["manifests/rulesets"]}}))
    workflow = tmp_path / "main.jsonc"
    workflow.write_text(json.dumps({"rulesets":["test.files"] if selection_owner == "workflow" else [],"pipeline":{"nodes":[
        {"id":"leaf","type_used":"test.leaf","display_name":"Leaf","description":"A scoped file check."}]}}))
    code = cli_main(["validate","--config",str(workflow),"--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 1
    errors = [item for item in report["errors"] if item["code"] == "QUALITY.FILE.MAX_LINES"]
    assert len(errors) == 1 and errors[0]["definition_id"] == "vibeflow.quality.files"
    assert errors[0]["details"]["limit"] == 2
    assert errors[0]["source_location"]["path"] == str(tmp_path / "leaf.py")
    assert not any("orphan.py" in str(item) for item in report["errors"])
    selection["calls"][0]["params"]["max_file_lines"] = 5
    manifest.write_text(json.dumps(selection))
    code = cli_main(["validate","--config",str(workflow),"--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["errors"] == []
    workspace = load_project_workspace(workflow)
    registry = build_workspace_node_registry(workspace)
    graph = parse_graph_config(json.loads(workflow.read_text()))
    snapshot = collect_workflow_source_context(registry,graph)
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    health = validate_graph_health(graph,registry=registry,source_context=snapshot,purity_policy=PurityPolicy(max_source_lines=1))
    # Explicit manifest RuleCall parameters win over the project's numeric defaults.
    assert health.errors == ()
    executions = health.info["rule_executions"]
    selected = next(item for item in executions if item["plan"]["ruleset_id"] == "test.files")
    assert selected["plan"]["calls"][0]["params"]["max_file_lines"] == 5


def test_project_handler_alias_receives_current_source_facts(tmp_path):
    from vibeflow.core.rules.builtin import builtin_rule_resources
    builtin = next(item for item in builtin_rule_resources()[0] if item.id == "vibeflow.quality.files")
    alias = replace(builtin,id="test.files.alias",handler=builtin.id)
    selection = RulesetDescriptor("test.files.alias",calls=(RuleCall("files",rule_id=alias.id,params={"max_file_lines":2}),))
    registry = _registry(tmp_path,(alias,),selection)
    graph = GraphConfig(nodes=(NodeSpec("leaf","test.leaf"),),rulesets=())
    source = collect_workflow_source_context(registry,graph)
    report = execute_python_node_rules(registry,source)
    finding = next(item for item in report.findings if item.code == "QUALITY.FILE.MAX_LINES")
    assert finding.definition_id == alias.id
    assert finding.source_location["path"] == str(tmp_path / "nodes.py")
    assert finding.details["limit"] == 2


def test_selected_project_theme_reports_original_parse_location_without_reparse(tmp_path,monkeypatch):
    selection = RulesetDescriptor("test.files",calls=(RuleCall("files",rule_id="vibeflow.quality.files"),))
    registry = _registry(tmp_path,(),selection)
    source_path = tmp_path / "nodes.py"
    broken = "class Leaf:\n    def run_pure(self, inputs, params):\n        return (\n"
    source_path.write_text(broken)
    snapshot = collect_workflow_source_context(registry,GraphConfig(nodes=(NodeSpec("leaf","test.leaf"),),rulesets=()))
    monkeypatch.setattr(ast,"parse",lambda *args,**kwargs:pytest.fail("A missing AST must remain unavailable, without reparse"))
    report = execute_python_node_rules(registry,snapshot)
    error = next(item for item in report.findings if item.code == "QUALITY.SYNTAX.PYTHON")
    assert error.source_location["path"] == str(source_path)
    assert error.source_location["line"] == 3
    assert error.definition_id == "vibeflow.quality.files"
    assert report.executions[0].results["files"].state == "unavailable"


@pytest.mark.parametrize("max_lines",[2,1000])
def test_checked_run_import_file_rule_uses_current_command_numeric_defaults_before_marker(tmp_path,max_lines):
    import json
    from vibeflow.tooling.application.python.project.declarations import _bind_node
    from vibeflow.tooling.application.python.runner import CheckedRunError,run_checked
    selection = RulesetDescriptor("test.import.files",calls=(RuleCall("files",rule_id="vibeflow.quality.files"),),
        entrypoints={"static":(),"run":(),"import":("files",)})
    registry = _registry(tmp_path,(),selection)
    marker = tmp_path / "imported.txt"
    path = tmp_path / "nodes.py"
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("imported")\nclass Leaf:\n    def run_pure(self,inputs,params):\n        return {{}}\n')
    registry.register(registry.descriptor("test.leaf"),loader=lambda:_bind_node(registry,"test.leaf",(tmp_path,)),overwrite=True)
    workflow = tmp_path / "main.jsonc"
    workflow.write_text(json.dumps({"policy":{"node_source":{"max_lines":max_lines}},"rulesets":[],"pipeline":{"nodes":[
        {"id":"leaf","type_used":"test.leaf","display_name":"Leaf","description":"One delayed import."}]}}))
    if max_lines == 2:
        with pytest.raises(CheckedRunError) as failure:
            run_checked(workflow,registry=registry,run_root=tmp_path / "runs",run_id="strict-import")
        finding = next(item for item in failure.value.result.health.errors if item.code == "QUALITY.FILE.MAX_LINES")
        assert finding.details["limit"] == 2
        assert finding.definition_id == "vibeflow.quality.files"
        assert failure.value.result.health.info["rule_phase"] == "import"
        assert not marker.exists()
    else:
        result = run_checked(workflow,registry=registry,run_root=tmp_path / "runs",run_id="allowed-import")
        assert result.health.status == "PASS"
        assert marker.read_text() == "imported"
    assert registry.rule_defaults()["purity_policy"].max_source_lines == max_lines
