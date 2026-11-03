"""User-facing session behavior through real AOT workflows and HTTP clients."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.e2e.async_cases import async_case
from vibeflow.coordination import Coordinator, CoordinationError, WorkflowClient, WorkflowServer
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.targets.python.sdk import CancellationSignal
from vibeflow.tooling.application.python.bundle import load_bundle


NODE_SOURCE = '''import asyncio
from vibeflow.targets.python.sdk import node

@node(id="session.boundary", node_type="vibeflow.node", flow_kind="terminal", rulesets=[], contract={})
class Boundary:
    def run_pure(self, inputs, params):
        return {}

@node(id="session.worker", node_type="vibeflow.node", rulesets=[], contract={
    "provides":[{"key":"result","type":"session.result","display_name":"Result"}],
    "output_semantics":{"result":["Worker result"]}})
class Worker:
    def run_pure(self, inputs, params):
        print("worker executed", flush=True)
        return {"result":"finished"}

@node(id="session.caller", node_type="vibeflow.node", flow_kind="workflow-io", rulesets=[],
    workflow_operations=[{"operation":"call"},{"operation":"kill"}], contract={
    "provides":[{"key":"result","type":"session.result","display_name":"Result"}],
    "output_semantics":{"result":["Worker terminal state"]},
    "params_schema":{"workflow":{"type":"object","required":True},"launch":{"type":"object","required":True}}})
class Caller:
    async def run_pure(self, inputs, params, context):
        child = await context.workflow.call({"workflow":params["workflow"],"launch":params["launch"]})
        stopped = await context.workflow.kill({"id":child["id"],"workflow":params["workflow"]})
        return {"result":stopped["state"]}

@node(id="session.cancelled_caller", node_type="vibeflow.node", flow_kind="workflow-io", rulesets=[],
    workflow_operations=[{"operation":"call"},{"operation":"receive"}], contract={
    "provides":[{"key":"result","type":"session.result","display_name":"Result"}],
    "output_semantics":{"result":["Parent result"]},
    "params_schema":{"workflow":{"type":"object","required":True},"launch":{"type":"object","required":True}}})
class CancelledCaller:
    async def run_pure(self, inputs, params, context):
        try:
            print("parent waiting", flush=True)
            await context.workflow.receive()
        finally:
            await context.workflow.call({"workflow":params["workflow"],"launch":params["launch"]})
        return {"result":"finished"}
'''


@pytest.fixture(scope="module")
def session_bundles(tmp_path_factory):
    root = tmp_path_factory.mktemp("session-workflows")
    source, app = root / "source", root / "source/app"
    for directory in (app / "nodes", app / "configs", app / "plugins/protocol"):
        directory.mkdir(parents=True)

    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    write(source / "vibeflow_config.jsonc", {"roots":[{"id":"session","path":"app"}]})
    write(source / "project_rules.jsonc", {"rulesets":[]})
    write(app / "root_rules.jsonc", {"rulesets":[]})
    write(app / "vibeflow_project.jsonc", {"project_target":"python"})
    (app / "nodes/operations.py").write_text(NODE_SOURCE, encoding="utf-8")
    (app / "plugins/protocol/plugin.py").write_text(
        '''from vibeflow.targets.python.sdk import Plugin, data_schema, lifecycle
class Session:
    def before_run(self, inputs):
        print("session opened", flush=True)
    def dispose(self):
        print("session closed", flush=True)
@lifecycle(id="session.lifecycle", type="runtime", rulesets=[])
def runtime(context):
    return Session()
plugin=Plugin(id="session.protocol",resources=[data_schema(type_key="session.result",schema={"type":"string"}),runtime])
''',
        encoding="utf-8")
    bundles = {}
    for name in ("worker", "full", "relative", "cancelled"):
        definition = "session.worker" if name == "worker" else "session.cancelled_caller" if name == "cancelled" else "session.caller"
        operation = {"id":"operate", "definition_id":definition}
        if name != "worker":
            operation["config"] = {"workflow":{"path":"configs/worker.jsonc",
                **({"root":"session"} if name != "relative" else {})}, "launch":{"kind":"in_process"}}
        nodes = [{"id":"start","definition_id":"session.boundary"}, operation,
                 {"id":"end","definition_id":"session.boundary"}]
        for item in nodes:
            item.update(display_name=item["id"], description="Execute " + item["id"] + " in " + name)
        config = app / f"configs/{name}.jsonc"
        write(config, {"rulesets":[], "plugins":[{"source":{"kind":"file","ref":"plugins/protocol/plugin.py"}}],
            "pipeline":{"entry_mode":"sync" if name == "worker" else "async", "nodes":nodes,
                "edges":[["start","operate"],["operate","end"]],
                "outputs":[{"type":"session.result","as":"result","cardinality":"exactly_one","display_name":"Result"}]}})
        destination = root / name
        built = subprocess.run([sys.executable, "-B", "-m", "vibeflow", "build",
            "--workspace", str(source / "vibeflow_config.jsonc"), "--config", str(config),
            "--out-dir", str(destination)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert built.returncode == 0, built.stdout + built.stderr
        bundles[name] = load_bundle(destination)
    shutil.rmtree(source)
    return bundles


def bind_application(scope, bundles, directory, execution):
    controls = {}
    for bundle in bundles.values():
        def factory(bundle=bundle, **options):
            runtime = bundle.create_runtime(run_dir=directory / options["workflow_instance_id"],
                runtime_options={"execution":execution, "trace":"off"}, **options)
            controls[bundle.workflow_descriptor["workflow"]["path"]] = runtime
            return runtime
        bind_workflow(scope, bundle.workflow_descriptor, factory)
    return controls


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_reused_aot_runtime_creates_and_disposes_each_session(session_bundles, tmp_path, execution, capsys):
    runtime = session_bundles["worker"].create_runtime(run_dir=tmp_path,
        runtime_options={"execution":execution, "trace":"off"})
    capsys.readouterr()
    for _ in range(2):
        assert runtime.run().get("result")["value"] == "finished"
    messages = {"session opened", "worker executed", "session closed"}
    output = [line for line in capsys.readouterr().out.splitlines() if line in messages]
    assert output == ["session opened", "worker executed", "session closed"] * 2


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
@async_case
async def test_relative_kill_matches_explicit_root(session_bundles, tmp_path, execution):
    scope = Coordinator()
    bind_application(scope, session_bundles, tmp_path, execution)
    try:
        for name in ("full", "relative"):
            ended = await asyncio.wait_for(scope.run(session_bundles[name].workflow_descriptor["workflow"]), 10)
            assert ended["state"] == "succeeded", ended
            assert ended["outputs"] == {"result":"cancelled"}, ended
    finally:
        await scope.aclose()


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
@async_case
async def test_stopped_parent_does_not_launch_work_from_cleanup(session_bundles, tmp_path, execution, capsys):
    scope = Coordinator()
    controls = bind_application(scope, session_bundles, tmp_path, execution)
    parent = asyncio.create_task(scope.run(session_bundles["cancelled"].workflow_descriptor["workflow"]))
    output = ""
    try:
        async with asyncio.timeout(10):
            while "parent waiting" not in output:
                output += capsys.readouterr().out
                await asyncio.sleep(.01)
        controls["configs/cancelled.jsonc"].request_stop("application stop button")
        ended = await asyncio.wait_for(parent, 10)
        await asyncio.sleep(0)
        output += capsys.readouterr().out
        assert ended["state"] == "cancelled", ended
        assert "worker executed" not in output, output
    finally:
        await scope.aclose()
        await parent


@pytest.mark.parametrize("client", ["python", "javascript"])
@async_case
async def test_http_zero_timeout_reads_available_messages_and_terminal_results(client):
    with WorkflowServer() as server:
        if client == "javascript":
            module = Path(__file__).resolve().parents[2] / "src/vibeflow/targets/javascript/resources/coordination/workflow_client.mjs"
            script = '''import {WorkflowClient} from MODULE;
const a=await WorkflowClient.open(URL), b=await WorkflowClient.open(URL);
try {
  a.send(b.id,"requests",{answer:42}); await a.flush();
  const message=await b.receive("requests",{timeout:0});
  let empty;
  try {await b.receive("requests",{timeout:0});} catch(error) {empty=error.code;}
  await b.finish({outputs:message.payload});
  const ended=await a.wait(b.id,{timeout:0});
  console.log(JSON.stringify({payload:message.payload,empty,state:ended.state,outputs:ended.outputs}));
} finally {await a.finish(); await b.finish();}
'''.replace("MODULE", json.dumps(module.as_uri())).replace("URL", json.dumps(server.url))
            result = await asyncio.to_thread(subprocess.run, ["node", "--input-type=module", "-e", script],
                capture_output=True, text=True, encoding="utf-8", timeout=10)
            assert result.returncode == 0, result.stdout + result.stderr
            assert json.loads(result.stdout) == {"payload":{"answer":42}, "empty":"VF_WAIT_TIMEOUT",
                "state":"succeeded", "outputs":{"answer":42}}
            return
        a, b = await WorkflowClient.open(server.url), await WorkflowClient.open(server.url)
        try:
            a.send(b.id, "requests", {"answer":42})
            await a.flush()
            assert (await b.receive("requests", timeout=0))["payload"] == {"answer":42}
            with pytest.raises(CoordinationError) as empty:
                await b.receive("requests", timeout=0)
            assert empty.value.code == "VF_WAIT_TIMEOUT"
            await b.finish(outputs={"answer":42})
            ended = await a.wait(b.id, timeout=0)
            assert ended["state"] == "succeeded" and ended["outputs"] == {"answer":42}
        finally:
            await a.finish()
            await b.finish()


@async_case
async def test_cancelled_http_call_does_not_create_an_instance(session_bundles, tmp_path):
    worker = session_bundles["worker"]
    reference, launch = worker.workflow_descriptor["workflow"], {"kind":"in_process"}
    server = WorkflowServer(launches=[{"workflow":reference, "launch":launch}])
    bind_application(server.coordinator, {"worker":worker}, tmp_path, "plan")
    with server:
        client = await WorkflowClient.open(server.url)
        try:
            signal = CancellationSignal()
            signal.request_stop("application stopped before Call")
            with pytest.raises(Exception) as stopped:
                await client.call(reference, launch=launch, signal=signal)
            assert stopped.value.code == "VF_ABORTED"
            instances = await client.request("instances", {})
            assert all(item["workflow"] != reference for item in instances), instances
        finally:
            await client.finish()
