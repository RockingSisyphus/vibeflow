"""Real JavaScript workflow lifecycle through ordinary Nodes and API injection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot

ROOT=Path(__file__).resolve().parents[2]


def example(tmp_path):
    source=tmp_path/"integration"
    shutil.copytree(ROOT/"sandbox/javascript/integration",source,
        ignore=shutil.ignore_patterns("node_modules","__pycache__","reports","*.pyc"))
    toolchain=Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (source/"project/node_modules").symlink_to(toolchain/"node_modules",target_is_directory=True)
    return source


def test_graph_opens_and_closes_an_application_api_without_a_host_factory(tmp_path):
    source=example(tmp_path)
    result=build_project_aot(ProjectBuildRequest(source/"vibeflow_config.jsonc",
        source/"project/configs/explicit_lifecycle.jsonc",tmp_path/"bundle",target="node",profile="single-esm",
        preview_root=tmp_path/"preview"))
    script='''const workflow=await import(process.argv[1]);
if("createWorkflowHost" in workflow)throw Error("retired export");
const calls=[];let active=false;
const api={open(){active=true;calls.push("open");return null;},double(x){if(!active)throw Error("not open");return 2*x;},close(){active=false;calls.push("close");return null;}};
const result=workflow.runWorkflow({x:8},{capabilities:{"sandbox.math_session":api}});
if(result.result!==16||active||JSON.stringify(calls)!=='["open","close"]')throw Error(JSON.stringify({result,calls,active}));'''
    executed=subprocess.run(["node","--input-type=module","-e",script,result.entry.as_uri()],capture_output=True,text=True)
    assert executed.returncode==0,executed.stderr
    assert "host_extensions" not in json.loads(result.manifest.read_text())["target_metadata"]


@pytest.mark.parametrize("profile",["web-app","esm-module"])
def test_browser_message_listener_is_explicit_isolated_and_cancelled(tmp_path, profile):
    renderer=os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT")
    if not renderer:
        pytest.skip("full browser gate supplies the locked Puppeteer runtime")
    source=example(tmp_path)
    script='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from lifecycle_cases import browser_message_loop_case
from sandbox_support import BuildCache
result=browser_message_loop_case(BuildCache(Path(sys.argv[2])),puppeteer_root=Path(sys.argv[3]),profile=sys.argv[4])
assert result["firstOutputs"]==[14,23]
assert result["secondOutputs"]==[32]
assert result["unhandledRejections"]==[]
assert result["errorCode"]=="VF_OUTPUT_SCHEMA"
'''
    env={**os.environ,"VIBEFLOW_SANDBOX_RUNTIME_ROOT":str(source)}
    result=subprocess.run([sys.executable,"-B","-c",script,str(ROOT/"sandbox/javascript/integration"),str(tmp_path/"builds"),renderer,profile],
        env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
