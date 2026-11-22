"""Real worker receipts, declared capacity, incremental refill and all-join cleanup."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from .graph_cases import SUCCESS_CASES, TOPOLOGY_CASES, assert_worker_trace, write_cases
from .support import ROOT, cli, command, example, findings, serve, write


def build_cases(root,language,toolchain=None):
    source=example(root / "source",language+"/graph_concurrency",toolchain)
    write_cases(source)
    entries={}
    for name,scenario,capacity in SUCCESS_CASES:
        target=root / name
        args=["build","--workspace",source / "vibeflow_config.jsonc","--config",source / f"project/configs/{name}.jsonc","--out-dir",target]
        if language=="javascript":args += ["--target","browser","--profile","single-esm"]
        result=cli(source,*args)
        entries[name]=target if language=="python" else Path(json.loads(result.stdout)["entry"])
    shutil.rmtree(source)
    return root,entries


@pytest.fixture(scope="module")
def python_concurrent(tmp_path_factory):
    return build_cases(tmp_path_factory.mktemp("concurrent-python"),"python")


@pytest.fixture(scope="module")
def javascript_concurrent(tmp_path_factory,toolchain):
    return build_cases(tmp_path_factory.mktemp("concurrent-javascript"),"javascript",toolchain)


@pytest.mark.parametrize("case",SUCCESS_CASES,ids=lambda case:str(case))
@pytest.mark.parametrize("execution",["plan","block","compiled"])
def test_python_concurrent_receipts_and_business_log(python_concurrent,tmp_path,case,execution):
    name,scenario,capacity=case
    root,entries=python_concurrent
    request=write(tmp_path / "request.json",{"initial":{"scenario":scenario},"mode":"async", "runtime_options":{"execution":execution,"trace":"full"}})
    for round in range(2):
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",entries[name],request,
            tmp_path / f"runs-{round}",cwd=tmp_path,env={"PYTHONPATH":None})
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
        assert payload["outputs"]=={"report":list(range(12))}
        events=[json.loads(line) for line in (Path(payload["run_dir"]) / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
        assert_worker_trace(events,capacity)


@pytest.mark.parametrize("case",SUCCESS_CASES,ids=lambda case:str(case))
@pytest.mark.parametrize("environment",["node","browser"])
def test_javascript_concurrent_receipts_and_business_log(javascript_concurrent,tmp_path,case,environment,browser_runtime):
    name,scenario,capacity=case
    root,entries=javascript_concurrent
    if environment=="node":
        request=write(tmp_path / "request.json",{"initial":{"scenario":scenario},"mode":"async","observe_business":True,"options":{"trace":"full"}})
        result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",entries[name],request,cwd=tmp_path)
        payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    else:
        html=write(root / (name+".html"),'''<meta charset="utf-8"><button id="run">收集并发任务结果</button><pre id="result"></pre>
<script type="module">
import {runWorkflowAsync} from "./'''+entries[name].relative_to(root).as_posix()+'''";
document.querySelector('#run').addEventListener('click',async()=>{
 try{
  const events=[];const output=await runWorkflowAsync({scenario:'''+json.dumps(scenario)+'''},{trace:'full',onTrace:event=>events.push(event)});
  document.querySelector('#result').textContent=JSON.stringify({output,events});
 }catch(error){document.querySelector('#result').textContent=JSON.stringify({error:error.message});}
});
</script>''')
        with serve(root) as url:
            result=command("node",ROOT / "tests/e2e/browser/application.cjs",browser_runtime / "package.json",url+"/"+html.name,cwd=tmp_path)
        payload=json.loads(result.stdout)
    assert payload["output"]=={"report":list(range(12))},payload
    assert_worker_trace(payload["events"],capacity)


@pytest.mark.parametrize("language",["python","javascript"])
def test_invalid_collector_and_disconnected_worker_are_rejected_before_build(tmp_path,language,toolchain):
    work=example(tmp_path / "source",language+"/graph_concurrency",toolchain if language=="javascript" else None)
    write_cases(work)
    for name,(code,severity) in TOPOLOGY_CASES.items():
        common=["--workspace",work / "vibeflow_config.jsonc","--config",work / f"project/configs/{name}.jsonc"]
        result=cli(work,"validate",*common,"--json",success=False)
        assert result.returncode==1 and any(item["code"]==code and item["severity"]==severity for item in findings(result)),result.stdout
        target=tmp_path / name
        args=["build",*common,"--out-dir",target]
        if language=="javascript":args += ["--target","node","--profile","single-esm"]
        rejected=cli(work,*args,success=False)
        assert rejected.returncode==1 and code in rejected.stdout and not target.exists(),rejected.stdout
