"""Normal browser host application over the real HTTP/CORS transport."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
from time import monotonic

from vibeflow.coordination import WorkflowClient, WorkflowServer

from .async_cases import async_case
from .host_projects import node_module
from .support import ROOT, serve, write


@async_case
async def test_browser_host_messages_completion_and_cooperative_stop(tmp_path,toolchain,browser_runtime):
    resources=ROOT / "src/vibeflow/targets/javascript/resources/coordination"
    for name in ("workflow_client.mjs","workflow_host.mjs"):
        shutil.copy2(resources / name,tmp_path / name)
    node_module(tmp_path)
    with serve(tmp_path) as base, WorkflowServer() as server:
        write(tmp_path / "index.html",'''<!doctype html><meta charset="utf-8"><title>Workflow host</title>
<button id="run">开始消息工作流</button><pre id="result"></pre>
<script type="module">
import {runWorkflowAsync} from './workflow.mjs';
import {runConnected} from './workflow_host.mjs';
document.querySelector('#run').addEventListener('click',async()=>{
 const url='''+json.dumps(server.url)+''';
 try {
  const first=await runConnected(runWorkflowAsync,{url,workflow:'browser-0'});
  let cancelled=false;
  try{await runConnected(runWorkflowAsync,{url,workflow:'browser-1'});}
  catch(error){cancelled=error.code==='VF_ABORTED'||error.name==='AbortError';}
  document.querySelector('#result').textContent=JSON.stringify({first,cancelled});
 }catch(error){document.querySelector('#result').textContent=JSON.stringify({error:error.message});}
});
</script>''')
        client=await WorkflowClient.open(server.url)
        process=subprocess.Popen(["node",str(ROOT / "tests/e2e/browser/application.cjs"),str(browser_runtime / "package.json"),base+"/index.html"],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8")
        try:
            for index in range(2):
                deadline=monotonic()+30
                while True:
                    instances=[item for item in await client.request("instances",{}) if item["workflow"]==f"browser-{index}"]
                    if instances:break
                    assert monotonic()<deadline and process.poll() is None,"browser did not register workflow"
                    await asyncio.sleep(.02)
                identity=instances[0]["id"]
                if index==0:
                    client.send(identity,"request",{"value":14})
                    reply=await client.receive("reply",timeout=10)
                    assert reply["payload"]=={"value":42,"self":identity}
                    assert (await client.wait(identity,timeout=10))["outputs"]=={"result":42}
                else:
                    assert (await client.kill(identity,timeout=10))["state"]=="cancelled"
            stdout,stderr=await asyncio.to_thread(process.communicate,timeout=20)
            assert process.returncode==0,stdout+stderr
            assert json.loads(stdout)=={"first":{"result":42},"cancelled":True}
        finally:
            if process.poll() is None:
                process.terminate();await asyncio.to_thread(process.wait,timeout=10)
            await client.finish()
