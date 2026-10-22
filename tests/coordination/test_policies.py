"""Rule grants are call-scoped and baked into AOT independently of appearances."""
import json
import os
from pathlib import Path
import shutil

import pytest

from tests.targets.python.test_code_plugins import project
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle
from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path


SOURCE = '''from vibeflow.targets.python.sdk import Plugin,node,capability,data_schema
@node(node_type='vibeflow.node', id="example.boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(node_type='vibeflow.node', id="example.work",contract={},rulesets=["vibeflow.process"],capabilities=[{"id":"example.external","operations":["read"]}])
class Work:
    def run_pure(self,inputs,params,context):
        context.capabilities["example.external"]["read"]({})
        return {}
interface=capability(id="example.external",targets=["python"],operations={"read":{"input_type":"example.request","output_type":"example.identity"}})
request=data_schema(type_key="example.request",schema={"type":"object"})
identity=data_schema(type_key="example.identity",schema={"type":"object"})
plugin=Plugin(id="example",resources=[interface,request,identity])
'''


def test_repeated_policy_records_merge_intent_without_changing_distinct_actions():
    from vibeflow.core.workflows.policies import fold_policies
    record = {"mode":"allow","call_path":["call"],"capability":"vibeflow.workflow",
        "operations":["call"],"actions":[{"operation":"call","wait":False}]}
    waiting = {**record,"actions":[{"operation":"call","wait":True}]}
    policy = fold_policies([record,record,waiting],[("call",)])[("call",)]
    assert policy["actions"] == [
        {"operation":"call","wait":False,"capability":"vibeflow.workflow"},
        {"operation":"call","wait":True,"capability":"vibeflow.workflow"}]


def test_same_node_type_cannot_borrow_another_calls_grant_and_aot_saves_policy(tmp_path, monkeypatch):
    nodes, resources = SOURCE.split("interface=", 1)
    workspace, config = project(tmp_path, nodes, plugin_source="from vibeflow.targets.python.sdk import Plugin,capability,data_schema\ninterface=" + resources)
    declaration = json.loads(config.read_text())
    grant = {"rule_id": "vibeflow.capability.allow", "params": {
        "capability": "example.external", "operations": ["read"]}}
    nodes = [{"id": name, "definition_id": key, "display_name": name, "description": name}
             for name, key in [("start", "example.boundary"), ("a", "example.work"),
                               ("b", "example.work"), ("end", "example.boundary")]]
    nodes[1]["rulesets"] = ["vibeflow.process", grant]
    nodes[1]["style"] = {"shape": "diamond", "fill": "#F0CC22"}
    declaration.update(rulesets=["vibeflow.workflow", {"rule_id": "vibeflow.capability.restrict", "params":{"capabilities":["example.external"]}}],
        pipeline={"nodes": nodes, "edges": [["start", "a"], ["a", "b"], ["b", "end"]]})
    config.write_text(json.dumps(declaration))
    report = validate_workspace_config_path(config, workspace=workspace)
    denied = [item for item in report.errors if item.rule_id == "GRAPH.CAPABILITY.DENIED"]
    assert len(denied) == 1 and denied[0].details["call_path"] == ["b"], report.to_dict()
    nodes[2]["rulesets"] = ["vibeflow.process", grant]
    config.write_text(json.dumps(declaration))
    result = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "bundle"))
    bundle = load_bundle(result.out_dir)
    from vibeflow.targets.python.quality.workflow import validation

    def forbidden(*args, **kwargs):
        raise AssertionError("AOT executed graph Rules")

    monkeypatch.setattr(validation, "validate_graph_health", forbidden)
    calls = []
    runtime = bundle.create_runtime(capabilities={"example.external": {
        "read": lambda request: calls.append(request) or {"id": "opaque-instance"}}}, run_dir=tmp_path / "run")
    runtime.run({})
    assert len(calls) == 2
    for name in ("a", "b"):
        assert runtime._frames[name].capability_policy["capabilities"]["example.external"] == ["read"]


def test_javascript_rule_adapter_bakes_the_same_call_policy(tmp_path):
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, ProjectBuildError, prepare_project_build, build_project_aot
    from tests.targets.javascript.test_aot_core import _run_esm
    source = Path(__file__).resolve().parents[2] / "sandbox/javascript/integration"
    destination = tmp_path / "integration"
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (destination / "project/node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    config = destination / "project/configs/async_capability.jsonc"
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow", {"rule_id": "vibeflow.capability.restrict",
        "params": {"capabilities": ["sandbox.storage"]}}]
    config.write_text(json.dumps(data))
    request = ProjectBuildRequest(workspace=destination / "vibeflow_config.jsonc", config=config, out_dir=tmp_path / "bundle", target="node", profile="esm-module")
    with pytest.raises(ProjectBuildError, match="no Rule grant"):
        prepare_project_build(request)
    read = next(node for node in data["pipeline"]["nodes"] if node["id"] == "read")
    read["rulesets"] = ["vibeflow.process", {"rule_id": "vibeflow.capability.allow", "params": {
        "capability": "sandbox.storage", "operations": ["read"]}}]
    config.write_text(json.dumps(data))
    built = build_project_aot(request)
    policy = built.prepared.plan.block(built.prepared.plan.entry_block).node("read").capability_policy.to_value()
    assert policy["capabilities"] == {"sandbox.storage": ["read"]}
    shutil.rmtree(destination)
    result = _run_esm(built.build.entry, '''
const result=await workflow.runWorkflowAsync({x:4,key:"answer"},{capabilities:{"sandbox.storage":{read:()=>({value:"stored"})}}});
console.log(JSON.stringify(result));
''')
    assert result == {"doubled": 8, "value": "stored"}
