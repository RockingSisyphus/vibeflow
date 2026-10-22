"""Node-owned launches survive deployment and retain instance-level stopping."""
import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.coordination.test_hosts import python_project, node_module
from vibeflow.coordination import WorkflowClient, WorkflowServer, CoordinationError
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle
from vibeflow.tooling.project.workflow_launches import source_launches, bundle_launches


@pytest.mark.parametrize("deployment", ["source", "aot"])
def test_call_selects_named_entry_in_source_and_deployment(tmp_path, deployment):
    workspace, config = python_project(tmp_path)
    steps = tmp_path/"nodes/steps.py"
    source = steps.read_text().replace('"params_schema":{', '"params_schema":{"factor":{"type":"number"},', 1)
    source = source.replace('"params_defaults":{', '"params_defaults":{"factor":3,', 1)
    steps.write_text(source.replace('message["payload"]["value"]*3', 'message["payload"]["value"]*params["factor"]'))
    value = json.loads(config.read_text())
    second = json.loads(json.dumps(value["pipeline"]["nodes"]))
    for node in second:
        node["id"] = "other_"+node["id"]
    second[1]["config"] = {"factor":10}
    value["pipeline"]["nodes"].extend(second)
    value["pipeline"]["edges"].extend([["other_start","other_work"],["other_work","other_end"]])
    value["pipeline"]["entries"] = {"triple":{"start":"start"},"ten":{"start":"other_start"}}
    config.write_text(json.dumps(value))
    command = [sys.executable,"-B","-m","vibeflow.coordination","run-python",
        "--run-root",str(tmp_path/"runs"),"--preview-root",str(tmp_path/"preview")]
    if deployment == "aot":
        built = build_python_aot(PythonBuildRequest(workspace,config,tmp_path/"bundle"))
        command += ["--bundle",str(built.out_dir)]
    else:
        command += ["--config",str(config),"--workspace",str(workspace.path)]
    launch = {"command":command,"cwd":str(tmp_path)}
    references = [{"root":workspace.root_for_path(config).id,"path":"workflow.jsonc","entry":entry} for entry in ("triple","ten")]
    with WorkflowServer(launches=[{"workflow":reference,"launch":launch} for reference in references]) as server:
        client = WorkflowClient(server.url)
        try:
            for reference, expected in zip(references, (6,20)):
                instance = client.call(reference,launch=launch,timeout=10)
                assert client.request("status",{"id":instance["id"]})["workflow"]["entry"] == reference["entry"]
                client.send(instance["id"],"request",{"value":2})
                assert client.receive("reply",timeout=10)["payload"]["value"] == expected
                assert client.wait(instance["id"],timeout=10)["state"] == "succeeded"
        finally:
            client.finish()


@pytest.mark.parametrize("nested", [False,True])
def test_node_launch_configuration_runs_after_source_project_is_removed(tmp_path, monkeypatch, nested):
    source=tmp_path/"source";source.mkdir()
    deployment=tmp_path/"peer";deployment.mkdir()
    peer=node_module(deployment)
    implementation=deployment/"nodes.mjs"
    implementation.write_text(implementation.read_text().replace('const api=context.capabilities',
        'if(process.env.NODE_LAUNCH_CASE!=="bundle")throw new Error("launch environment missing");\n  const api=context.capabilities'))
    host=Path(__file__).resolve().parents[2]/"src/vibeflow/targets/javascript/resources/coordination/workflow_node.mjs"
    reference={"root":"peer","path":"worker.jsonc"}
    launch={"command":["node",str(host),str(peer)],"cwd":".","env":{"NODE_LAUNCH_CASE":"bundle"}}
    workspace,config=python_project(source)
    steps=source/"nodes/steps.py"
    text=steps.read_text().replace('["send","receive"]','["send","receive","call","wait"]')
    text=text.replace('        message=api["receive"]({"port":"request"})',
        '        peer=api["call"]({"workflow":params["workflow"],"launch":params["launch"]})\n'
        '        api["send"]({"id":peer["id"],"port":"request","payload":{"value":7}})\n'
        '        message=api["receive"]({"port":"reply"})\n'
        '        api["wait"]({"id":peer["id"]})')
    text=text.replace('        api["send"]({"id":message["sender"],"port":"reply","payload":{"value":value,"self":context.workflow.self()["id"]}})\n','')
    steps.write_text(text)
    data=json.loads(config.read_text());call=data["pipeline"]["nodes"][1]
    call["config"]={"workflow":reference,"launch":launch}
    call["rulesets"][1]["params"]["operations"] += ["call","wait"]
    if nested:
        call["config"] = {"workflow":{"root":"unused","path":"unused.jsonc"},"launch":{"command":["unused"]}}
        value_output = {"type":"number","as":"out","display_name":"Result","cardinality":"exactly_one"}
        definition = {"type_key":"launch.block","display_name":"Launch block","description":"Reusable call block",
            "requires":[],"provides":[{"key":"out","type":"number","display_name":"Result"}],"rulesets":[],
            "pipeline":{"nodes":[data["pipeline"]["nodes"][0],call,data["pipeline"]["nodes"][2]],
                "edges":[["start","work"],["work","end"]],"outputs":[value_output]}}
        (source/"launch.jsonc").write_text(json.dumps(definition))
        data["nodeset_imports"] = ["launch.jsonc"]
        data["pipeline"]["nodes"][1] = {"id":"block","definition_id":"launch.block","display_name":"Call block","description":"Override the reusable launch",
            "node_configs":{"work":{"workflow":reference,"launch":launch}}}
        data["pipeline"]["edges"] = [["start","block"],["block","end"]]
    config.write_text(json.dumps(data))
    declared=source_launches(workspace)
    assert len(declared)==1 and declared[0]["workflow"]==reference
    built=build_python_aot(PythonBuildRequest(workspace,config,tmp_path/"bundle"))
    bundle=load_bundle(built.out_dir)
    shutil.rmtree(source)
    from vibeflow.tooling.project.preparation import ProjectPreparation
    monkeypatch.setattr(ProjectPreparation,"__init__",lambda *_a,**_k:pytest.fail("deployment prepared the source project"))
    with WorkflowServer(launches=bundle_launches(built.out_dir)) as server:
        client=WorkflowClient(server.url,workflow=declared[0]["caller"])
        try:
            result=bundle.run(capabilities={"vibeflow.workflow":client.operations()},run_root=tmp_path/"runs")
            assert result.public_outputs=={"result":63}
        finally:
            client.finish()


def test_identical_launch_commands_resolve_against_each_calling_root(tmp_path):
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    roots=[]
    reference={"root":"peer","path":"worker.jsonc"}
    launch={"command":[sys.executable,"-B","worker.py"],"cwd":".","env":{}}
    for name in ("left","right"):
        location=tmp_path/name;location.mkdir()
        _,config=python_project(location)
        steps=location/"nodes/steps.py"
        steps.write_text(steps.read_text().replace('["send","receive"]','["send","receive","call"]'))
        data=json.loads(config.read_text());data["pipeline"]["nodes"][1]["config"]={"workflow":reference,"launch":launch}
        config.write_text(json.dumps(data))
        (location/"worker.py").write_text('from vibeflow.coordination import WorkflowClient\nc=WorkflowClient.from_environment()\n'
            f'c.finish(outputs={{"root":{name!r}}})\n')
        roots.append({"id":name,"path":name})
    workspace_path=tmp_path/"vibeflow_config.jsonc";workspace_path.write_text(json.dumps({"roots":roots}))
    declarations=source_launches(load_workspace_config(workspace_path))
    assert len(declarations)==2
    with WorkflowServer(launches=declarations) as server:
        for name in ("left","right"):
            client=WorkflowClient(server.url,workflow={"root":name,"path":"workflow.jsonc"})
            try:
                instance=client.call(reference,launch=launch,timeout=10)
                assert client.wait(instance["id"],timeout=10)["outputs"]=={"root":name}
            finally:
                client.finish()


def test_kill_checks_workflow_and_only_stops_selected_instance(tmp_path):
    module=node_module(tmp_path)
    host=Path(__file__).resolve().parents[2]/"src/vibeflow/targets/javascript/resources/coordination/workflow_node.mjs"
    reference={"root":"peer","path":"worker.jsonc"}
    launch={"command":["node",str(host),str(module)]}
    with WorkflowServer(launches=[{"workflow":reference,"launch":launch}]) as server:
        client=WorkflowClient(server.url);ids=[]
        try:
            for _ in range(2):ids.append(client.call(reference,launch=launch,timeout=10)["id"])
            with pytest.raises(CoordinationError) as failure:
                client.kill(ids[0],workflow={"root":"other","path":"worker.jsonc"},timeout=2)
            assert failure.value.code=="VF_WORKFLOW_MISMATCH"
            assert client.kill(ids[0],workflow=reference,timeout=10)["state"]=="cancelled"
            assert client.request("status",{"id":ids[1]})["state"]=="running"
            client.send(ids[1],"request",{"value":3})
            assert client.receive("reply",timeout=10)["payload"]["value"]==9
            assert client.wait(ids[1],timeout=10)["state"]=="succeeded"
            with pytest.raises(CoordinationError) as failure:
                client.call(reference,launch={"command":["unconfigured-command"]},timeout=2)
            assert failure.value.code=="VF_LAUNCH_UNDECLARED"
        finally:
            for identifier in ids:
                if client.request("status",{"id":identifier})["state"] not in {"succeeded","failed","cancelled"}:
                    client.kill(identifier,timeout=10)
            client.finish()


def test_call_rejects_a_host_registering_a_different_workflow():
    expected={"root":"peer","path":"expected.jsonc"}
    child="from vibeflow.coordination import WorkflowClient\nc=WorkflowClient.from_environment(workflow={'root':'peer','path':'actual.jsonc'})\nc.finish()\n"
    launch={"command":[sys.executable,"-B","-c",child]}
    with WorkflowServer(launches=[{"workflow":expected,"launch":launch}]) as server:
        client=WorkflowClient(server.url)
        try:
            with pytest.raises(CoordinationError,match="actual.jsonc"):
                client.call(expected,launch=launch,timeout=10)
            child=next(item for item in client.request("instances",{}) if item["id"]!=client.id)
            assert child["state"]=="failed" and "expected.jsonc" in child["error"]
        finally:
            client.finish()


@pytest.mark.parametrize("configured", [False, True])
def test_source_service_never_launches_planned_calls(tmp_path, configured):
    workspace, config = python_project(tmp_path / "source")
    steps = tmp_path / "source/nodes/steps.py"
    steps.write_text(steps.read_text().replace(
        '["send","receive"]', '["send","receive","call"]'))
    command = [sys.executable, "-B", "-c",
        'from vibeflow.coordination import WorkflowClient; '
        'c=WorkflowClient.from_environment(); c.finish(outputs={"launched":True})']
    launch = {"command": command}
    live = {"root": "peer", "path": "live.jsonc"}
    future = {"root": "peer", "path": "future.jsonc"}
    data = json.loads(config.read_text())
    work = data["pipeline"]["nodes"][1]
    work["config"] = {"workflow": live, "launch": launch}
    work["rulesets"][1]["params"]["operations"].append("call")
    data["pipeline"]["nodes"].extend([
        {**data["pipeline"]["nodes"][0], "id": "future_start"},
        {**work, "id": "future", "status": "planned", "flow_kind": "process",
            "requires": [], "provides": [{"key": "out", "type": "number", "display_name": "Future result"}],
            "config": {"workflow": future, "launch": launch} if configured else {}},
        {**data["pipeline"]["nodes"][2], "id": "future_end"},
    ])
    data["pipeline"]["edges"].extend([["future_start", "future"], ["future", "future_end"]])
    data["pipeline"]["entries"] = {"live": {"start": "start"}, "future": {"start": "future_start"}}
    data["pipeline"]["default_entry"] = "live"
    config.write_text(json.dumps(data))
    caller = {"root": workspace.root_for_path(config).id, "path": "workflow.jsonc"}
    with WorkflowServer(launches=source_launches(workspace)) as server:
        client = WorkflowClient(server.url, workflow=caller)
        try:
            instance = client.call(live, launch=launch, timeout=10)
            assert client.wait(instance["id"], timeout=10)["outputs"] == {"launched": True}
            with pytest.raises(CoordinationError) as failure:
                client.call(future, launch=launch, timeout=10)
            assert failure.value.code == "VF_LAUNCH_UNDECLARED"
        finally:
            client.finish()
