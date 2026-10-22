"""Copyable declarations exercise the ordinary SDK on both Targets."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
import shutil
import pytest

from vibeflow.targets.python.sdk.resources import definition


def test_shipped_templates_and_contract_resources_use_normal_sdk(tmp_path, monkeypatch):
    from distribution.build import _copy_coordination_templates
    _copy_coordination_templates(tmp_path)
    root = tmp_path / "kernel/templates/workflow_nodes"
    spec = importlib.util.spec_from_file_location("copied_nodes", root / "nodes.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    names=("Call","CallAndWait","Wait","Send","Receive","Kill","PortReceive","PortSend")
    nodes = [definition(getattr(module,name)).descriptor for name in names]
    assert len(nodes) == 8
    workflow_nodes=[item for item in nodes if item.flow_kind=="workflow-io"]
    assert len(workflow_nodes)==6
    from vibeflow.tooling.presentation.node_presentation import resolve_presentation
    styles={item.id:resolve_presentation(item).to_dict() for item in workflow_nodes}
    assert styles["example.call"]["values"]["fill"]=="#fef3c7"
    assert styles["example.receive"]["values"]["fill"]=="#1e3a8a"
    sdk = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources/sdk.mjs"
    javascript = (root / "nodes.mjs").read_text().replace('"@vibeflow/plugin"', json.dumps(sdk.as_uri()))
    (root / "nodes.mjs").write_text(javascript)
    result = subprocess.run(["node", "--input-type=module", "-e", f'''
import {{CallAndWaitRun,ReceiveRun,SendRun}} from {json.dumps((root / "nodes.mjs").as_uri())};
const calls=[];
const context={{capabilities:{{"vibeflow.workflow":{{call:async()=>({{id:"worker-id"}}),wait:async r=>({{state:"succeeded",outputs:{{answer:42}}}}),receive:async()=>({{payload:7}}),send:r=>calls.push(r)}}}}}};
const result=await CallAndWaitRun({{}},{{workflow:{{root:"peer",path:"main.jsonc"}},launch:{{command:["worker"]}}}},context);
const message=await ReceiveRun({{}},{{}},context);
SendRun({{"example.instance":{{value:"worker-id"}},"example.payload":{{value:7}}}},{{}},context);
console.log(JSON.stringify({{result,message,calls}}));
'''], text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == {"instance": "worker-id", "result": {"state": "succeeded", "outputs": {"answer": 42}}}
    assert payload["message"] == {"message": {"payload": 7}}
    assert payload["calls"] == [{"id": "worker-id", "payload": 7}]


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_copied_templates_build_and_call_through_real_host(tmp_path, target, capsys):
    from distribution.build import _copy_coordination_templates
    from vibeflow.coordination import WorkflowClient, WorkflowServer
    from vibeflow.tooling.project.workflow_launches import source_launches, bundle_launches
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.bundle import load_bundle
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
    _copy_coordination_templates(tmp_path/"templates")
    templates = tmp_path/"templates/kernel/templates/workflow_nodes"
    location = tmp_path/"project"
    if target == "python":
        from tests.targets.python.test_code_plugins import project
        source=(templates/"nodes.py").read_text()+'\n@node(id="fixture.boundary",node_type="vibeflow.node",flow_kind="terminal",contract={},rulesets=[])\nclass Boundary:\n    def run_pure(self,inputs,params):return {}\n'
        workspace, config = project(location, source, plugin_source=(templates/"protocol.py").read_text())
    else:
        from tests.targets.javascript.test_code_plugins import project
        workspace, config = project(location, "", plugin_source="")
        (location/"nodes/steps.ts").unlink()
        shutil.copy2(templates/"nodes.mjs", location/"nodes/nodes.mjs")
        with (location/"nodes/nodes.mjs").open("a") as stream:
            stream.write('\nexport const boundary=defineNode({id:"fixture.boundary",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[],run(){return {};}});\n')
        for name in ("protocol.mjs","interfaces.mjs"):
            shutil.copy2(templates/name, location/"plugins/demo"/name)
    child = "from vibeflow.coordination import WorkflowClient\nc=WorkflowClient.from_environment()\nc.finish(outputs={'answer':42})\n"
    launch = {"command":[sys.executable,"-B","-c",child],"cwd":".","env":{}}
    value = json.loads(config.read_text())
    if target == "javascript":
        value["plugins"] = [{"source":{"kind":"file","ref":"plugins/demo/protocol.mjs"}}]
    value["rulesets"] = []
    value["pipeline"] = {"entry_mode":"async" if target=="javascript" else "sync",
        "nodes":[{"id":"start","definition_id":"fixture.boundary","display_name":"Start","description":"Begin invocation"},
            {"id":"call","definition_id":"example.callandwait","display_name":"Call and wait","description":"Launch a real peer",
            "config":{"workflow":{"root":"peer","path":"worker.jsonc"},"launch":launch}},
            {"id":"end","definition_id":"fixture.boundary","display_name":"End","description":"Finish invocation"}],
        "edges":[["start","call"],["call","end"]],
        "outputs":[{"type":"example.result","as":"result","display_name":"Result","cardinality":"exactly_one"}]}
    config.write_text(json.dumps(value))
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    workspace_path=tmp_path/"vibeflow_config.jsonc"
    workspace_path.write_text(json.dumps({"roots":[{"id":"project","path":"project"}]}))
    workspace=load_workspace_config(workspace_path)
    declared = source_launches(workspace)
    if target == "python":
        built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path/"bundle"))
    else:
        built = build_project_aot(ProjectBuildRequest(workspace.path, config, tmp_path/"bundle", "node", "esm-module"))
    with WorkflowServer(launches=bundle_launches(built.out_dir)) as server:
        if target == "python":
            client = WorkflowClient(server.url, workflow=declared[0]["caller"])
            try:
                output = load_bundle(built.out_dir).run(capabilities={"vibeflow.workflow":client.operations()}, run_root=tmp_path/"runs").public_outputs
            finally:
                client.finish()
        else:
            host = Path(__file__).resolve().parents[2]/"src/vibeflow/targets/javascript/resources/coordination/workflow_node.mjs"
            completed = subprocess.run(["node",str(host),str(built.entry)], env={**os.environ,"VIBEFLOW_COORDINATION_URL":server.url},
                capture_output=True,text=True,timeout=30)
            assert completed.returncode == 0, completed.stdout+completed.stderr
            observer = WorkflowClient(server.url)
            try:
                instances = observer.request("instances",{})
                output = next(item["outputs"] for item in instances if item["workflow"] == declared[0]["caller"])
            finally:
                observer.finish()
        assert output["result"]["state"] == "succeeded"
        assert output["result"]["outputs"] == {"answer":42}
    # A known planned Call retains its configured target without executing Rules.
    value["pipeline"]["nodes"][1].update(status="planned",flow_kind="workflow-io",requires=[],provides=[
        {"key":"instance","type":"example.instance","display_name":"Instance"},
        {"key":"result","type":"example.result","display_name":"Result"}])
    config.write_text(json.dumps(value))
    from vibeflow.tooling.application.cli import main
    from vibeflow.tooling.project.config_loader import strip_jsonc_comments
    capsys.readouterr()
    assert main(["export-architecture","--workspace",str(workspace.path),"--config",str(config)])==0
    architecture=json.loads(strip_jsonc_comments(capsys.readouterr().out))
    node=next(item for item in architecture["workflow"]["nodes"] if item["id"]=="call")
    assert node["presentation"]["modifiers"]["planned"] is True
    assert node["presentation"]["values"]["fill"]=="#fef3c7"
    assert node["presentation"]["values"]["shape"]=="notch-rect"
    action=node["operations"][0]
    assert action["planned"] is True and action["workflow"]=={"root":"peer","path":"worker.jsonc"}
