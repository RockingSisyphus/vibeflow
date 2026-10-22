"""Run real SDK workflows through the explicit Python and Node host adapters."""
import json
import os
from pathlib import Path
import sys
from time import sleep

import pytest

from tests.targets.python.test_code_plugins import project
from tests.targets.javascript.aot_fixtures import plan_fixture
from vibeflow.core.workflows.interfaces import WORKFLOW_SCHEMA_TYPES, workflow_capability_descriptor
from vibeflow.coordination import WorkflowClient, WorkflowServer
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module


def python_project(root):
    descriptor = workflow_capability_descriptor().to_dict()
    descriptor.pop("kind")
    schemas = "\n".join(f's{i}=data_schema(type_key={key!r},schema={value!r})'
        for i, (key, value) in enumerate(WORKFLOW_SCHEMA_TYPES.items()))
    source = '''from vibeflow.targets.python.sdk import Plugin,node,capability,data_schema
@node(node_type='vibeflow.node', id="peer.boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(node_type='vibeflow.node', id="peer.work",rulesets=["vibeflow.process"],
      capabilities=[{"id":"vibeflow.workflow","operations":["send","receive"]}],
      contract={"params_schema":{"workflow":{"type":"object"},"launch":{"type":"object"}},"params_defaults":{"workflow":{},"launch":{}},"provides":[{"key":"out","type":"number","display_name":"Result"}],"output_semantics":{"out":["Tripled message"]}})
class Work:
    def run_pure(self,inputs,params,context):
        api=context.capabilities["vibeflow.workflow"]
        message=api["receive"]({"port":"request"})
        value=message["payload"]["value"]*3
        api["send"]({"id":message["sender"],"port":"reply","payload":{"value":value,"self":context.workflow.self()["id"]}})
        return {"out":value}
'''
    plugin_source = "from vibeflow.targets.python.sdk import Plugin,capability,data_schema\n"
    plugin_source += f"interface=capability(**{descriptor!r})\n" + schemas
    plugin_source += "\nplugin=Plugin(id='peer',resources=[interface," + ",".join(f"s{i}" for i in range(len(WORKFLOW_SCHEMA_TYPES))) + "])\n"
    workspace, config = project(root, source, plugin_source=plugin_source)
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow", {"rule_id": "vibeflow.capability.restrict"}]
    data["pipeline"] = {"nodes": [{"id": key, "definition_id": node, "display_name": key, "description": key}
        for key, node in [("start", "peer.boundary"), ("work", "peer.work"), ("end", "peer.boundary")]],
        "edges": [["start", "work"], ["work", "end"]],
        "outputs": [{"type": "number", "as": "result", "cardinality": "exactly_one", "display_name": "Result"}]}
    data["pipeline"]["nodes"][1]["rulesets"] = ["vibeflow.process", {"rule_id": "vibeflow.capability.allow",
        "params": {"capability": "vibeflow.workflow", "operations": [ "send", "receive"]}}]
    config.write_text(json.dumps(data))
    return workspace, config


def node_module(root, *, caller=False, peer=None):
    implementation = '''
export function boundary(){return {};}
export async function work(inputs,params,context){
  const api=context.capabilities["vibeflow.workflow"];
  const message=await api.receive({port:"request"});
  const value=message.payload.value*3;
  api.send({id:message.sender,port:"reply",payload:{value,self:context.workflow.self().id}});
  return {out:value};
}
'''
    operations = [ "send", "receive"]
    if caller:
        operations += ["call", "wait"]
        implementation = implementation.replace('const message=await api.receive({port:"request"});', '''
  const peer=await api.call({workflow:params.workflow,launch:params.launch});
  api.send({id:peer.id,port:"request",payload:{value:7}});
  const message=await api.receive({port:"reply"});
  const ended=await api.wait({id:peer.id});
  if(ended.state!=="succeeded")throw new Error(JSON.stringify(ended));''')
        implementation = implementation.replace('  api.send({id:message.sender,port:"reply",payload:{value,self:context.workflow.self().id}});', '')
    (root / "nodes.mjs").write_text(implementation)
    cap = workflow_capability_descriptor().to_dict()
    plan, bindings = plan_fixture({"entry_mode": "async", "schemas": {**WORKFLOW_SCHEMA_TYPES, "number": {"type": "number"}},
        "capabilities": [cap], "nodes": [
            {"id": key, "definition_id": key, "is_terminal": key != "work", "flow_kind": "process" if key == "work" else "terminal",
             "implementation": {"kind": "file", "ref": "./nodes.mjs", "export": "work" if key == "work" else "boundary"},
             **({"completion": "suspend", "provides": [{"key": "out", "type": "number"}],
                 "capabilities": [{"id": "vibeflow.workflow", "operations": operations}], "params":peer or {}} if key == "work" else {})}
            for key in ("start", "work", "end")],
        "routes": [{"source": "start", "target": "work"}, {"source": "work", "target": "end"}],
        "outputs": [{"type": "number", "as": "result", "cardinality": "exactly_one"}]})
    path = root / "workflow.mjs"
    path.write_text(emit_workflow_module(plan, javascript_bindings=bindings).source)
    return path


@pytest.mark.parametrize("target", ["python-source", "python-aot", "node"])
def test_instances_exchange_messages_and_kill_confirms_actual_workflow_end(tmp_path, target):
    resources = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources"
    if target.startswith("python"):
        workspace, config = python_project(tmp_path)
        command = [sys.executable, "-B", "-m", "vibeflow.coordination", "run-python",
            "--run-root", str(tmp_path / "runs"), "--preview-root", str(tmp_path / "preview")]
        if target == "python-aot":
            from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
            built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "bundle"))
            command += ["--bundle", str(built.out_dir)]
        else:
            command += ["--config", str(config), "--workspace", str(workspace.path)]
    else:
        command = ["node", str(resources / "coordination" / "workflow_node.mjs"), str(node_module(tmp_path))]
    reference={"root":workspace.root_for_path(config).id if target.startswith("python") else "peer","path":"workflow.jsonc"}
    launch={"command":command,"cwd":str(tmp_path)}
    with WorkflowServer(launches=[{"workflow":reference,"launch":launch}]) as server:
        caller = WorkflowClient(server.url)
        instances = []
        try:
            for value in (7, 11):
                identity = caller.call(reference, launch=launch, timeout=15)["id"]
                instances.append(identity)
                caller.send(identity, "request", {"value": value})
            caller.flush()
            replies = [caller.receive("reply", timeout=15) for _ in instances]
            assert {reply["payload"]["self"] for reply in replies} == set(instances)
            assert sorted(reply["payload"]["value"] for reply in replies) == [21, 33]
            for identity in instances:
                result = caller.wait(identity, timeout=15)
                assert result["state"] == "succeeded", result
                assert result["outputs"]["result"] in (21, 33)
            waiting = caller.call(reference, launch=launch, timeout=15)["id"]
            instances.append(waiting)
            stopped = caller.kill(waiting,workflow=reference, timeout=15)
            assert stopped["state"] == "cancelled", stopped
        finally:
            for identity in instances:
                if caller.request("status", {"id": identity})["state"] not in {"succeeded", "failed", "cancelled"}:
                    caller.kill(identity, timeout=15)
            caller.finish()


@pytest.mark.parametrize("caller_target", ["python-source", "python-aot", "node"])
def test_ordinary_workflow_node_calls_other_target_sends_receives_and_waits(tmp_path, caller_target):
    """The caller is a real Node implementation, rather than a raw test client."""
    resources = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources"
    caller_root, peer_root = tmp_path / "caller", tmp_path / "peer"
    caller_root.mkdir()
    peer_root.mkdir()
    def python_command(root, *, caller=False, aot=False, peer=None):
        workspace, config = python_project(root)
        if caller:
            plugin = root / "nodes/steps.py"
            source = plugin.read_text().replace('["send","receive"]', '["send","receive","call","wait"]')
            source = source.replace('        message=api["receive"]({"port":"request"})',
                '        peer=api["call"]({"workflow":params["workflow"],"launch":params["launch"]})\n        api["send"]({"id":peer["id"],"port":"request","payload":{"value":7}})\n        message=api["receive"]({"port":"reply"})\n        api["wait"]({"id":peer["id"]})')
            source = source.replace('        api["send"]({"id":message["sender"],"port":"reply","payload":{"value":value,"self":context.workflow.self()["id"]}})\n', '')
            plugin.write_text(source)
            declaration = json.loads(config.read_text())
            declaration["pipeline"]["nodes"][1]["rulesets"][1]["params"]["operations"] += ["call", "wait"]
            declaration["pipeline"]["nodes"][1]["config"] = peer
            config.write_text(json.dumps(declaration))
        command = [sys.executable, "-B", "-m", "vibeflow.coordination", "run-python",
            "--run-root", str(root / "runs"), "--preview-root", str(root / "preview")]
        if aot:
            from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
            built = build_python_aot(PythonBuildRequest(workspace, config, root / "bundle"))
            return command + ["--bundle", str(built.out_dir)]
        return command + ["--workspace", str(workspace.path), "--config", str(config)]
    if caller_target == "node":
        peer_command=python_command(peer_root,aot=True)
    else:
        peer_command=["node",str(resources/"coordination/workflow_node.mjs"),str(node_module(peer_root))]
    peer={"workflow":{"root":"peer","path":"workflow.jsonc"},"launch":{"command":peer_command,"cwd":str(tmp_path)}}
    caller_command=(["node",str(resources/"coordination/workflow_node.mjs"),str(node_module(caller_root,caller=True,peer=peer))]
        if caller_target=="node" else python_command(caller_root,caller=True,aot=caller_target.endswith("aot"),peer=peer))
    reference={"root":"caller","path":"workflow.jsonc"}
    launch={"command":caller_command,"cwd":str(tmp_path)}
    with WorkflowServer(launches=[peer,{"workflow":reference,"launch":launch}]) as server:
        client = WorkflowClient(server.url)
        try:
            identity = client.call(reference,launch=launch,timeout=20)["id"]
            result = client.wait(identity, timeout=30)
            assert result["state"] == "succeeded", result
            assert result["outputs"] == {"result": 63}
        finally:
            # This is author/test cleanup, not server-owned child cleanup.
            for instance in client.request("instances", {}):
                if instance["id"] != client.id and instance["state"] not in {"succeeded", "failed", "cancelled"}:
                    client.kill(instance["id"], timeout=15)
            client.finish()


def test_launcher_and_caller_exit_do_not_end_the_registered_workflow(tmp_path):
    resources = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources"
    command = ["node", str(resources / "coordination" / "workflow_node.mjs"), str(node_module(tmp_path))]
    wrapper = tmp_path / "launch.py"
    wrapper.write_text("import subprocess\nsubprocess.Popen(" + repr(command) + ")\n")
    reference={"root":"peer","path":"workflow.jsonc"}
    launch={"command":[sys.executable,str(wrapper)],"cwd":str(tmp_path)}
    with WorkflowServer(launches=[{"workflow":reference,"launch":launch}]) as server:
        caller = WorkflowClient(server.url)
        observer = WorkflowClient(server.url)
        identity = None
        try:
            identity = caller.call(reference, launch=launch, timeout=15)["id"]
            caller.finish()
            sleep(.1)
            assert observer.request("status", {"id": identity})["state"] == "running"
            observer.send(identity, "request", {"value": 9})
            assert observer.receive("reply", timeout=10)["payload"]["value"] == 27
            assert observer.wait(identity, timeout=10)["state"] == "succeeded"
        finally:
            if identity and observer.request("status", {"id": identity})["state"] not in {"succeeded", "failed", "cancelled"}:
                observer.kill(identity,workflow=reference, timeout=10)
            observer.finish()
            caller.finish()
