"""Independent business Nodes use types and rules from atomic Plugin packages."""
import json
from pathlib import Path
import pytest

from tests.fixtures.support.projects import register_root
from vibeflow.tooling.project.resources import prepare_workflow_resources, ResourcePreparationError
from vibeflow.tooling.project.workspace_loader import load_project_workspace
from vibeflow.tooling.application.python.project.declarations import declared_python_registry
from vibeflow.tooling.application.rule_review import effective_rule_plans


SOURCE = '''from vibeflow.targets.python.sdk import node
@node(node_type="demo.shell", id="demo",contract={},rulesets=["demo.rules"])
class Demo:
    def run_pure(self,inputs,params):
        raise RuntimeError("business was invoked")
'''
PLUGIN_SOURCE = '''from vibeflow.targets.python.sdk import Plugin,node_type,rule,ruleset,RuleCall
from vibeflow.core.rules import RuleResult
shell=node_type(id="demo.shell",presentation={"shape":"rect","fill":"#f2e6c5"})
@rule(id="demo.check")
def check(context,inputs,params):
    assert context.subject["descriptor"].id == "demo"
    return RuleResult()
rules=ruleset(id="demo.rules",calls=[RuleCall(id="check",rule_id="demo.check")])
plugin=Plugin(id="demo",resources=[shell,check,rules],config_schema={"type":"object","properties":{"value":{"type":"integer"}},"additionalProperties":False},config_defaults={"value":1})
'''
EXECUTABLE = '''from vibeflow.targets.python.sdk import node
from vibeflow.core.rules import RuleResult
@node(node_type="demo.shell", id="demo.start",flow_kind="terminal",contract={},rulesets=[])
class Start:
    def run_pure(self,inputs,params):
        return {}
@node(node_type="demo.shell", id="demo",contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Computed value"]}},rulesets=["vibeflow.process","demo.rules"])
class Demo:
    def run_pure(self,inputs,params):
        return {"result": 7}
'''


def project(root, source=SOURCE, selections=None, *, plugin_source=PLUGIN_SOURCE):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    register_root(root)
    (root / "nodes").mkdir(exist_ok=True)
    (root / "nodes/steps.py").write_text(source, encoding="utf-8")
    package = root / "plugins/demo"
    package.mkdir(parents=True, exist_ok=True)
    (package / "plugin.py").write_text(plugin_source, encoding="utf-8")
    config = root / "workflow.jsonc"
    config.write_text(json.dumps({"plugins": selections if selections is not None else [
        {"source":{"kind":"file","ref":"plugins/demo/plugin.py"}}],
        "pipeline":{"nodes":[{"id":"demo","definition_id":"demo","display_name":"Demo","description":"Fixture business operation"}],"edges":[]}}), encoding="utf-8")
    return load_project_workspace(root), config


def executable_project(root, source=EXECUTABLE, *, plugin_source=PLUGIN_SOURCE):
    workspace, config = project(root, source, plugin_source=plugin_source)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["rulesets"] = []
    data["pipeline"]["nodes"].insert(0,{"id":"start","definition_id":"demo.start","display_name":"Start","description":"Start"})
    data["pipeline"]["edges"] = [["start","demo"]]
    data["pipeline"]["outputs"] = [{"type":"number","as":"result","display_name":"Result","cardinality":"exactly_one"}]
    config.write_text(json.dumps(data), encoding="utf-8")
    return workspace, config


def test_declarations_do_not_invoke_business_rule_or_runtime(tmp_path):
    source = PLUGIN_SOURCE.replace('return RuleResult()', 'raise RuntimeError("check invoked")').replace('plugin=Plugin(', 'plugin=Plugin(runtime=lambda context: (_ for _ in ()).throw(RuntimeError("factory invoked")),')
    workspace, config = project(tmp_path, plugin_source=source)
    assert effective_rule_plans(config, workspace=workspace)["nodes"][0]["rulesets"] == ["demo.rules"]
    prepared = prepare_workflow_resources(workspace, config)
    assert prepared.catalogs.origins[("nodes","demo")].owner.kind == "root"
    assert {kind for _,kind,_ in prepared.bindings} == {"rule","plugin"}


def test_removing_plugin_preserves_business_file_and_reports_missing_type(tmp_path):
    workspace, config = project(tmp_path, selections=[])
    with pytest.raises(ValueError,match="missing NodeType"):
        prepare_workflow_resources(workspace, config)
    assert (tmp_path / "nodes/steps.py").is_file()


def test_workflow_parameters_do_not_change_fixed_resources(tmp_path):
    workspace, config = project(tmp_path)
    first = prepare_workflow_resources(workspace, config)
    data=json.loads(config.read_text());data["plugins"][0]["config"]={"value":9};config.write_text(json.dumps(data))
    second = prepare_workflow_resources(workspace, config)
    assert first.catalogs.nodes.to_dict() == second.catalogs.nodes.to_dict()
    assert first.catalogs.plugin_settings["demo"]["value"] == 1
    assert second.catalogs.plugin_settings["demo"]["value"] == 9


@pytest.mark.parametrize("selection,code", [
    ({"status":{}},"CONFIG.SCHEMA.RESOURCE_STATUS"),
    ({"source":{"kind":[],"ref":"plugins/demo/plugin.py"}},"PLUGIN.SELECTION.SOURCE"),
    ({"id":"demo","status":"planned","type":{}},"CONFIG.SCHEMA.PLUGIN_TYPE"),
])
def test_invalid_selection_precedes_loading(tmp_path,selection,code):
    marker=tmp_path/"loaded"
    workspace,config=project(tmp_path,selections=[selection],plugin_source=f"open({str(marker)!r},'w').write('loaded')")
    with pytest.raises((ResourcePreparationError,ValueError)) as error:
        prepare_workflow_resources(workspace,config)
    diagnostics=getattr(error.value,"findings",())
    assert getattr(error.value,"code",None)==code or any(item.rule_id==code for item in diagnostics)
    assert not marker.exists()


def test_separate_rule_and_node_use_native_execution(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    workspace,config=executable_project(tmp_path)
    result=run_workspace_checked(config,workspace=workspace,run_root=tmp_path/"runs")
    assert result.context.get("result")["value"]==7
    assert not result.health.errors


@pytest.mark.parametrize("execution",["plan","compiled","block"])
@pytest.mark.parametrize("defaults,overrides",[({"labels":{"phase":"prepare"}},{}),({"labels":{}},{}),({"phases":[{"name":"prepare"}]},{}),({"phases":["prepare"]},{}),({},{"labels":{"phase":"prepare"}})])
def test_nested_plugin_config_is_readonly_and_runtime_is_per_run(tmp_path,execution,defaults,overrides):
    from vibeflow.targets.python.runtime import RuntimeOptions
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    expected={**defaults,**overrides}
    runtime=f'''
from vibeflow.core.descriptors.json_values import thaw_json
class Runtime:
    def __init__(self): self.calls=0
    def before_run(self,payload): self.calls+=1
    def after_run(self,payload,trace): assert self.calls==1
    def dispose(self): assert self.calls==1
def create(context):
    assert thaw_json(context["config"])=={expected!r}
    try: context["config"]["extra"]=True
    except TypeError: pass
    else: raise AssertionError("mutable config")
    return Runtime()
'''
    plugin=PLUGIN_SOURCE.replace('plugin=Plugin(',runtime+'\nplugin=Plugin(runtime=create,').replace('config_defaults={"value":1}',f'config_defaults={defaults!r}').replace('config_schema={"type":"object","properties":{"value":{"type":"integer"}},"additionalProperties":False}','config_schema={"type":"object"}')
    workspace,config=executable_project(tmp_path,plugin_source=plugin)
    data=json.loads(config.read_text());data["plugins"][0]["config"]=overrides;config.write_text(json.dumps(data))
    for name in ("first","second"):
        result=run_workspace_checked(config,workspace=workspace,run_root=tmp_path/"runs",run_id=name,runtime_options=RuntimeOptions(execution=execution,trace="off"))
        assert result.context.get("result")["value"]==7


def test_business_nodes_in_plugin_are_rejected(tmp_path):
    workspace,config=project(tmp_path, source="", plugin_source=SOURCE+'\n'+PLUGIN_SOURCE.replace('resources=[shell,check,rules]', 'resources=[shell,check,rules,Demo]'))
    from vibeflow.tooling.project.preparation import ProjectPreparation
    prepare_workflow_resources(workspace,config)
    (tmp_path / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.packages"}]}')
    assert any(item.rule_id == "PLUGIN.PACKAGE.BUSINESS_NODE" for item in ProjectPreparation(workspace).review().findings)


def test_private_support_cannot_be_imported_outside_plugin_package(tmp_path):
    (tmp_path/"borrowed.py").write_text('VALUE=1\n')
    workspace,config=project(tmp_path,plugin_source='import borrowed\n'+PLUGIN_SOURCE)
    from vibeflow.tooling.project.preparation import ProjectPreparation
    prepare_workflow_resources(workspace,config)
    (tmp_path / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.plugin_ownership"}]}')
    assert any(item.rule_id == "PLUGIN.PACKAGE.IMPORT" for item in ProjectPreparation(workspace).review().findings)
