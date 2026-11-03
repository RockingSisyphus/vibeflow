"""Primary business failures and lifecycle cleanup through deployed hosts."""
import asyncio
import shutil

import pytest

from vibeflow.coordination import Coordinator
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.tooling.application.python import load_bundle

from .async_cases import async_case
from .support import cli, workspace, write


@pytest.fixture(scope="module")
def failure_bundle(tmp_path_factory):
    root=tmp_path_factory.mktemp("failure-application")
    app=workspace(root / "source",'''from vibeflow.targets.python.sdk import node
@node(id="failure.boundary",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={})
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(id="failure.work",node_type="vibeflow.node",rulesets=[],contract={
 "params_schema":{"fail":{"type":"boolean"}},"params_defaults":{"fail":False},
 "provides":[{"key":"answer","type":"answer","display_name":"Answer"}],"output_semantics":{"answer":["Computed value"]}})
class Work:
    def run_pure(self,inputs,params):
        if params["fail"]:
            raise ValueError("business input is invalid")
        return {"answer":7}
''',plugin='''from vibeflow.targets.python.sdk import Plugin,lifecycle,data_schema
class Audit:
    def node_failed(self,*args):
        print("failure observer executed",flush=True)
        raise RuntimeError("failure observer could not write")
    def dispose(self):
        print("application cleanup finished",flush=True)
@lifecycle(id="failure.audit",type="runtime",rulesets=[])
def create(context):return Audit()
plugin=Plugin(id="failure",resources=[create,data_schema(type_key="answer",schema={"type":"number"})])
''')
    config=write(app / "configs/main.jsonc",{"rulesets":[],"plugins":[{"source":{"kind":"file","ref":"plugins/example/plugin.py"}}],
        "pipeline":{"nodes":[{"id":name,"definition_id":"failure.work" if name=="work" else "failure.boundary",
            "display_name":name,"description":"Failure application "+name} for name in ("start","work","end")],
            "edges":[["start","work"],["work","end"]],"outputs":[{"type":"answer","as":"result","cardinality":"exactly_one","display_name":"Result"}]}})
    cli(app.parent,"build","--workspace",app.parent / "vibeflow_config.jsonc","--config",config,"--out-dir",root / "bundle")
    shutil.rmtree(app.parent)
    return load_bundle(root / "bundle")


@pytest.mark.parametrize("execution",["plan","block","compiled"])
@pytest.mark.parametrize("fails",[False,True])
@async_case
async def test_host_preserves_business_error_and_actual_cleanup(failure_bundle,tmp_path,execution,fails,capsys):
    bundle=failure_bundle
    scope=Coordinator()
    def create(**options):
        return bundle.create_runtime(run_dir=tmp_path / options["workflow_instance_id"],node_config_overrides={"work":{"fail":fails}},
            runtime_options={"execution":execution},**options)
    bind_workflow(scope,bundle.workflow_descriptor,create)
    capsys.readouterr()
    try:
        ended=await asyncio.wait_for(scope.run(bundle.workflow_descriptor["workflow"]),15)
        output=capsys.readouterr().out
        assert "application cleanup finished" in output
        if fails:
            assert ended["state"]=="failed" and ended["error"]["code"]=="ValueError",ended
            assert ended["error"]["message"]=="business input is invalid",ended
            assert "failure observer executed" in output
            assert any("failure observer could not write" in item["message"] for item in ended["error"]["cleanup_errors"]),ended
        else:assert ended["state"]=="succeeded" and ended["outputs"]=={"result":7},ended
    finally:await scope.aclose()
