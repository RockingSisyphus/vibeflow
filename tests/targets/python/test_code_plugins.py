"""Fixed SDK declarations selected independently by actual workflows."""

import json
from pathlib import Path

import pytest

from vibeflow.tooling.project.descriptor_loader import load_workflow_plugins, DescriptorLoadError
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.application.python.project.declarations import declared_python_registry
from vibeflow.tooling.application.rule_review import effective_rule_plans


def project(tmp_path, source, selections=None):
    (tmp_path / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "p", "path": "."}]}))
    (tmp_path / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (tmp_path / "plugin.py").write_text(source)
    config = tmp_path / "workflow.jsonc"
    config.write_text(json.dumps({"plugins": selections if selections is not None else [{"source": {"kind": "file", "ref": "plugin.py"}}],
        "pipeline": {"nodes": [{"id": "demo", "type_used": "demo", "display_name": "demo", "description": "demo"}], "edges": []}}))
    return load_workspace_config(tmp_path / "vibeflow_config.jsonc"), config


SOURCE = '''from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,RuleCall
@node(type_key="demo",contract={},rulesets=["demo.rules"])
class Demo:
    def run_pure(self,inputs,params):
        raise RuntimeError("business was invoked")
@rule(id="demo.check")
def check(context,inputs,params):
    raise RuntimeError("check was invoked")
rules = ruleset(id="demo.rules",calls=[RuleCall(id="check",rule_id="demo.check")],entrypoints={"static":["check"]})
plugin=Plugin(id="demo",resources=[Demo,check,rules],config_schema={"type":"object","properties":{"value":{"type":"integer"}},"additionalProperties":False},config_defaults={"value":1})
'''


def test_preview_loads_declarations_without_invoking_rule_or_node(tmp_path):
    workspace, config = project(tmp_path, SOURCE)
    payload = effective_rule_plans(config, workspace=workspace)
    assert payload["nodes"][0]["rulesets"] == ["demo.rules"]
    loaded = load_workflow_plugins(workspace, config)
    assert loaded.catalogs.origins[("nodes", "demo")].line == 2
    assert set(kind for _, kind, _ in loaded.bindings) == {"node", "rule"}


@pytest.mark.parametrize("selection", [[], [{"enabled": False, "source": {"kind":"file","ref":"plugin.py"}}],
    [{"status":"planned", "id":"demo", "source":{"kind":"file","ref":"plugin.py"}}]])
def test_unselected_plugin_is_never_loaded(tmp_path, selection):
    workspace, config = project(tmp_path, 'raise RuntimeError("unselected")', selection)
    assert not load_workflow_plugins(workspace, config).catalogs.nodes.available()


@pytest.mark.parametrize("selection,code", [
    ({"status":{}}, "CONFIG.SCHEMA.RESOURCE_STATUS"),
    ({"source":{"kind":[],"ref":"plugin.py"}}, "PLUGIN.SELECTION.SOURCE"),
    ({"id":"demo","status":"planned","type":{}}, "CONFIG.SCHEMA.PLUGIN_TYPE"),
    ({"id":"demo","status":"planned","targets":"python"}, "CONFIG.SCHEMA.PLUGIN_TARGETS"),
])
def test_invalid_selection_reports_its_field_before_trusted_loading(tmp_path, selection, code):
    marker = tmp_path / "loaded"
    workspace, config = project(tmp_path, f"open({str(marker)!r}, 'w').write('loaded')", [selection])
    with pytest.raises(DescriptorLoadError) as captured:
        load_workflow_plugins(workspace, config)
    assert captured.value.code == code
    assert captured.value.field.startswith("plugins[0]")
    assert captured.value.path == str(config)
    assert not marker.exists()


def test_workflow_parameters_do_not_change_fixed_resources(tmp_path):
    workspace, config = project(tmp_path, SOURCE)
    first = load_workflow_plugins(workspace, config)
    data = json.loads(config.read_text())
    data["plugins"][0]["config"] = {"value": 9}
    config.write_text(json.dumps(data))
    second = load_workflow_plugins(workspace, config)
    assert first.catalogs.nodes.to_dict() == second.catalogs.nodes.to_dict()
    assert first.catalogs.plugin_settings["demo"]["value"] == 1
    assert second.catalogs.plugin_settings["demo"]["value"] == 9


def test_importing_a_definition_does_not_contribute_it(tmp_path):
    workspace, config = project(tmp_path, SOURCE.replace("resources=[Demo,check,rules]", "resources=[check,rules]"))
    registry = declared_python_registry(workspace, config)
    assert registry.available() == []


def test_declaration_factory_is_rejected(tmp_path):
    workspace, config = project(tmp_path, 'def plugin(config):\n    raise RuntimeError("factory called")\n')
    with pytest.raises(DescriptorLoadError, match="fixed SDK"):
        load_workflow_plugins(workspace, config)


EXECUTABLE = '''from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,base_lib
from vibeflow.core.rules import RuleResult
@node(type_key="demo.start",flow_kind="terminal",contract={},rulesets=[])
class Start:
    def run_pure(self,inputs,params):
        return {}
@node(type_key="demo",contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Computed value"]}},rulesets=["vibeflow.process","demo.rules"])
class Demo:
    def run_pure(self,inputs,params):
        return {"result": 7}
@rule(id="demo.check")
def check(context,inputs,params):
    print("rule execution")
    assert context.facts["plugins"]["demo"]["value"] == 1
    return RuleResult()
rules=ruleset(id="demo.rules",calls=[{"id":"check","rule_id":"demo.check"}])
plugin=Plugin(id="demo",resources=[Start,Demo,check,rules],config_defaults={"value":1})
'''


def executable_project(tmp_path, source=EXECUTABLE):
    workspace, config = project(tmp_path, source)
    data = json.loads(config.read_text())
    data["rulesets"] = []
    data["pipeline"]["nodes"].insert(0,{"id":"start","type_used":"demo.start","display_name":"Start","description":"Start"})
    data["pipeline"]["edges"] = [["start","demo"]]
    data["pipeline"]["outputs"] = [{"type":"number","as":"result","display_name":"Result","cardinality":"exactly_one"}]
    config.write_text(json.dumps(data))
    return workspace, config


def test_colocated_rule_and_node_use_native_execution(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    workspace, config = executable_project(tmp_path)
    result = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs")
    assert result.context.get("result")["value"] == 7
    assert result.health.status == "PASS"


def test_resource_query_does_not_call_business_checks_or_factories(tmp_path, capsys):
    from vibeflow.tooling.application.cli import main
    workspace, config = project(tmp_path,SOURCE.replace('resources=[Demo,check,rules]', 'resources=[Demo,check,rules],runtime=lambda context: (_ for _ in ()).throw(RuntimeError("factory invoked"))'))
    assert main(["inspect-resources","--config",str(config),"--workspace",str(workspace.path),"--kind","node","--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["descriptor"]["type_key"] for item in payload["resources"]] == ["demo"]
    assert payload["resources"][0]["origin"]["line"] == 2


def test_loaded_bootstrap_is_diagnosed(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    marker = tmp_path / "events.txt"
    source = EXECUTABLE.replace('from vibeflow.core.rules import RuleResult',
        'from vibeflow.core.rules import RuleResult\nfrom pathlib import Path\nPath('+repr(str(marker))+').write_text("loaded")')
    workspace, config = executable_project(tmp_path,source)
    report = validate_workspace_config_path(config,workspace=workspace)
    assert marker.read_text() == "loaded"
    assert report.status == "FAIL"
    assert any(item.rule_id == "NODE.IMPORT.SIDE_EFFECT" for item in report.errors)


def test_late_module_is_not_imported_after_failed_import_rule(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    marker = tmp_path / "late.txt"
    (tmp_path / "late.py").write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("imported")\nclass Demo:\n    def run_pure(self,inputs,params):\n        return {}\n')
    source = 'from vibeflow.targets.python.sdk import Plugin,node,SourceLocator\nlate=node(type_key="demo",contract={},rulesets=["vibeflow.process"],source=SourceLocator("file","late.py","Demo"))\nplugin=Plugin(id="demo",resources=[late])\n'
    workspace, config = project(tmp_path,source)
    report = validate_workspace_config_path(config,workspace=workspace)
    assert report.status == "FAIL"
    assert not marker.exists()
    assert any(item.rule_id == "NODE.IMPORT.SIDE_EFFECT" for item in report.errors)


def test_runtime_instances_and_readonly_parameters_are_per_run(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    marker = tmp_path / "runtime.txt"
    lifecycle = '''class Runtime:
    def before_run(self,payload):
        self.calls += 1
    def after_run(self,payload,trace):
        assert self.calls == 1
    def dispose(self):
        with open(MARKER,"a") as stream:
            stream.write("disposed\\n")
def create(context):
    try:
        context["config"]["value"]=99
        raise AssertionError("mutable config")
    except TypeError:
        pass
    instance=Runtime()
    instance.calls=0
    return instance
plugin=Plugin(runtime=create,'''
    source = EXECUTABLE.replace('plugin=Plugin(', lifecycle.replace('MARKER',repr(str(marker))))
    workspace, config = executable_project(tmp_path,source)
    for name in ("first","second"):
        result = run_workspace_checked(config,workspace=workspace,run_root=tmp_path/"runs",run_id=name)
        assert result.context.get("result")["value"] == 7
    assert marker.read_text().splitlines() == ["disposed","disposed"]


def test_colocated_library_reviews_its_function_and_reachable_helpers(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    source = EXECUTABLE.replace('@node(type_key="demo",', '@node(type_key="demo",base_libs=["demo.math"],')
    source = source.replace('return {"result": 7}', 'return {"result": calculate()}')
    source = source.replace('@rule(id=', '''@base_lib(id="demo.math",rulesets=["vibeflow.base_lib"])
def calculate():
    return offset(6)
def offset(value):
    return value+1
@rule(id=''')
    source = source.replace('resources=[Start,Demo,check,rules]', 'resources=[Start,Demo,calculate,check,rules]')
    workspace, config = executable_project(tmp_path,source)
    report = validate_workspace_config_path(config,workspace=workspace)
    assert not report.errors, [item.to_dict() for item in report.errors]
    (tmp_path/"plugin.py").write_text(source.replace('return value+1','print("helper effect")\n    return value+1'))
    report = validate_workspace_config_path(config,workspace=workspace)
    assert any(item.code == "BASE_LIB.SIDE_EFFECT_CALL" for item in report.errors)


def test_compiler_instances_are_released_and_partial_failure_releases_runtime(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    from vibeflow.tooling.application.python.runner import CheckedRunError
    marker = tmp_path/"dispose.txt"
    callbacks = '''class Compiler:
    def dispose(self):
        with open(MARKER,"a") as stream:
            stream.write("compiler\\n")
class Runtime:
    def dispose(self):
        with open(MARKER,"a") as stream:
            stream.write("runtime\\n")
def compiler(context): return Compiler()
def runtime(context): return Runtime()
def broken(context): raise RuntimeError("factory root cause")
plugin=Plugin(compiler=compiler,runtime=runtime,'''
    source = EXECUTABLE.replace('plugin=Plugin(',callbacks.replace('MARKER',repr(str(marker))))
    source += '\nsecond=Plugin(id="broken",runtime=broken)\n'
    workspace,config = executable_project(tmp_path,source)
    data=json.loads(config.read_text())
    data["plugins"].append({"source":{"kind":"file","ref":"plugin.py","export":"second"}})
    config.write_text(json.dumps(data))
    with pytest.raises(CheckedRunError) as error:
        run_workspace_checked(config,workspace=workspace,run_root=tmp_path/"runs")
    assert error.value.result.health.errors[0].code == "PLUGIN.FACTORY.LOAD"
    assert "factory root cause" in error.value.result.health.errors[0].message
    assert marker.read_text().splitlines() == ["compiler","runtime"]


def test_colocated_plugin_default_rules_review_its_factory_and_methods(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    source=EXECUTABLE.replace('plugin=Plugin(','''class Runtime:
    def before_run(self,payload):
        return None
def create(context):
    return Runtime()
plugin=Plugin(runtime=create,rulesets=["vibeflow.plugin"],''')
    workspace,config=executable_project(tmp_path,source)
    report=validate_workspace_config_path(config,workspace=workspace)
    assert not report.errors,[item.to_dict() for item in report.errors]
    (tmp_path/"plugin.py").write_text(source.replace('return None','print("plugin effect")\n        return None'))
    report=validate_workspace_config_path(config,workspace=workspace)
    assert any(item.code=="NODE.EFFECT.CALL_FORBIDDEN" for item in report.errors), [item.to_dict() for item in report.errors]


def test_refused_nodeset_preserves_health_before_rendering(tmp_path):
    import shutil
    from vibeflow.tooling.application.python.runner import CheckedRunError, run_checked
    from vibeflow.tooling.application.python.project.core import build_workspace_environment

    fixture = Path(__file__).resolve().parents[3] / "sandbox/python/integration"
    shutil.copytree(fixture / "project", tmp_path / "project")
    shutil.copy2(fixture / "vibeflow_config.jsonc", tmp_path / "vibeflow_config.jsonc")
    workspace = load_workspace_config(tmp_path / "vibeflow_config.jsonc")
    config = tmp_path / "project/configs/fail_nodeset_key_leak.jsonc"
    environment = build_workspace_environment(workspace, config)
    with pytest.raises(CheckedRunError) as captured:
        run_checked(config, registry=environment.registry,
                    policy_path=tmp_path / "project/kernel_policy.jsonc", run_root=tmp_path / "runs")
    result = captured.value.result
    assert any(item.code == "NODESET.PROVIDES.UNKNOWN_KEY" for item in result.health.errors)
    saved = json.loads((result.run_dir / "health_report.json").read_text())
    assert any(item["code"] == "NODESET.PROVIDES.UNKNOWN_KEY" for item in saved["errors"])
    assert not (result.run_dir / "architecture.jsonc").exists()
    assert not (result.run_dir / "graph.svg").exists()
    assert (result.run_dir / "runtime_trace.jsonl").read_text() == ""


@pytest.mark.parametrize("kind",["module","package"])
def test_explicit_python_package_source_uses_fixed_definition(tmp_path,kind):
    workspace,config=project(tmp_path,SOURCE,selections=[{"source":{"kind":kind,"ref":"selected_package"}}])
    package=tmp_path/"selected_package";package.mkdir()
    (package/"__init__.py").write_text(SOURCE)
    loaded=load_workflow_plugins(workspace,config)
    assert loaded.catalogs.nodes.available()==("demo",)
    assert loaded.catalogs.origins[("nodes","demo")].path==str(package/"__init__.py")
