"""Real Python, AOT Node.js and browser sessions over multi-file SDK resources."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

from common import ROOT, normalize, write
from resource_support import project, cli, config, replace, observe


def form(root, target, variant):
    data=config(root)
    if variant in {"serial","unused_file","edit_run"}:return
    if variant=="branch":
        if target=="javascript":
            path=root/"plugin.ts";text=path.read_text()
            source='import {defineNode} from "@vibeflow/plugin";\nexport const choose=defineNode({type_key:"demo.choose",flow_kind:"decision",rulesets:["vibeflow.process"],contract:{provides:[{key:"route.branch",type:"route.branch",display_name:"Branch"}],output_semantics:{"route.branch":["Select a branch"]}},run(){return {"route.branch":"left"};}});\nexport const branchType=defineDataSchema({type_key:"route.branch",schema:{type:"string"}});\n'
            path.write_text(source+text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,choose,branchType]'))
        else:
            path=root/"plugin.py";text=path.read_text()
            source='from vibeflow.targets.python.sdk import node\n@node(type_key="demo.choose",flow_kind="decision",rulesets=["vibeflow.process"],contract={"provides":[{"key":"route.branch","type":"route.branch","display_name":"Branch"}],"output_semantics":{"route.branch":["Select a branch"]}})\nclass Choose:\n    def run_pure(self,inputs,params):\n        return {"route.branch":"left"}\nbranch_type=data_schema(type_key="route.branch",schema={"type":"string"})\n'
            path.write_text(text.replace('plugin = Plugin',source+'\nplugin = Plugin').replace('resources=[Start, Model, increment, number]','resources=[Start, Model, increment, number, Choose, branch_type]'))
        call={"id":"choose","type_used":"demo.choose","display_name":"Choose","description":"Select one native branch"}
        data["pipeline"]["nodes"].insert(1,call)
        data["pipeline"]["edges"]=[{"from":"start","to":"choose"},{"from":"choose","to":"model","when":"route.branch == 'left'"},{"from":"choose","to":"end","when":"route.branch == 'right'"},{"from":"model","to":"end"}]
    else:
        body=deepcopy(data["pipeline"])
        body["outputs"][0]["as"]="result"
        if variant=="loop":
            body["inputs"]=[{"key":"number","type":"number","display_name":"Initial value","required":True}]
            if target=="javascript":
                replace(root,"node.ts",'contract:{provides:','contract:{requires:[{type:"number",cardinality:"exactly_one",display_name:"Input"}],input_semantics:{number:["Incoming value"]},provides:')
                replace(root,"node.ts",'run(){return {result:multiply(library.implementation(2),2)};}','run(inputs){return {result:multiply(library.implementation(inputs.number.value),2)};}')
            else:
                replace(root,"node_resource.py",'contract={"provides":','contract={"requires":[{"type":"number","cardinality":"exactly_one","display_name":"Input"}],"input_semantics":{"number":["Incoming value"]},"provides":')
                replace(root,"node_resource.py",'increment(2)','increment(inputs["number"]["value"])')
        write(root/"body.jsonc",{"type_key":"demo.body","display_name":"Body","description":"A native composition of the multi-file model","rulesets":["vibeflow.workflow"],"requires":[] if variant!="loop" else [{"type":"number","cardinality":"exactly_one","display_name":"Input"}],"provides":[{"key":"result","type":"number","display_name":"Result"}],"pipeline":body})
        data["nodeset_imports"]=[{"path":"body.jsonc"}]
        middle={"id":"stage","type_used":"demo.body","display_name":"Stage","description":"Native Nodeset"}
        if variant=="loop":
            middle.update(type_used="vibeflow.loop.while",requires=[{"type":"number","cardinality":"exactly_one","display_name":"Value"}],provides=[{"key":"result","type":"number","display_name":"Result"}],loop={"body":"demo.body","max_iterations":1,"stop_after":1,"carry":[{"from":"number","as":"number","update":"result"}],"outputs":[{"from":"result","as":"result"}]})
            data["pipeline"]["inputs"]=[{**body["inputs"][0],"key":"value"}]
        data["pipeline"]["nodes"]=[data["pipeline"]["nodes"][0],middle,data["pipeline"]["nodes"][-1]]
        data["pipeline"]["edges"]=[["start","stage"],["stage","end"]]
    write(root/"workflow.jsonc",data)


def execute(root, script, *, browser=False, entry=None, name="session"):
    if browser:
        args=["node",str(ROOT/"tests/fixtures/rule_gaps/resource_runtime_browser.mjs"),os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"],entry,script]
    else:args=["node","--input-type=module","--eval",script]
    result=subprocess.run(args,cwd=root,capture_output=True,text=True,check=False,timeout=120)
    write(root/"evidence"/(name+".json"),{"command":args,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
    return normalize(result)


def runtime(root,target,variant,*,browser=False):
    (root/"evidence").mkdir(exist_ok=True)
    if variant=="unused_file":
        source="node_resource.py" if target=="python" else "node.ts"
        part="node_support.py" if target=="python" else "node_support.ts"
        extra="unreferenced.py" if target=="python" else "unreferenced.ts"
        (root/extra).write_text('UNUSED=9\n' if target=="python" else 'export const unused=9;\n')
        replace(root,source,'"'+part+'"','"'+part+'","'+extra+'"')
    if variant=="edit_run":
        left='left + right' if target=="python" else 'left+right'
        replace(root,"math_support.py" if target=="python" else "math_support.ts",left,left+' + 1')
    form(root,target,variant)
    if target=="python":
        output=root/"evidence"/"values.json"
        script='''import json,sys
from pathlib import Path
from vibeflow.tooling.application.cli import main
import vibeflow.tooling.application.python.workspace_service as service
original=service.run_workspace_checked
def record(*args,**kwargs):
    result=original(*args,**kwargs)
    Path(sys.argv[1]).write_text(json.dumps({"number":result.context.get("number")["value"]}))
    return result
service.run_workspace_checked=record
raise SystemExit(main(sys.argv[2:]))
'''
        write(root/"input.json",{"value":2} if variant=="loop" else {})
        args=[sys.executable,"-c",script,str(output),"run","--workspace",str(root/"vibeflow_config.jsonc"),"--config",str(root/"workflow.jsonc"),"--run-root",str(root/"runs"),"--input",str(root/"input.json"),"--run-id","resources"]
        result=subprocess.run(args,cwd=root,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"},capture_output=True,text=True,check=False,timeout=180)
        (root/"evidence").mkdir(exist_ok=True)
        write(root/"evidence"/"run.json",{"command":args,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
        actual=normalize(result);values=json.loads(output.read_text()) if output.exists() else {}
        actual["metrics"]["numeric_result"]=values.get("number")
        return actual
    built=cli(root,"build",name="build",extra=["--target","browser" if browser else "node","--profile","single-esm","--out-dir",root/"dist"])
    if built["metrics"]["exit_code"]:return built
    entry=built["payload"]["entry"]
    initial=json.dumps({"value":2} if variant=="loop" else {})
    script='const values=await workflow.runWorkflow('+initial+');return values;'
    if browser:executed=execute(root,script,browser=True,entry=entry)
    else:executed=execute(root,'const workflow=await import('+json.dumps(Path(entry).as_uri())+');const values=await workflow.runWorkflow('+initial+');console.log(JSON.stringify(values));')
    built["metrics"].update(runtime_exit_code=executed["metrics"]["exit_code"],numeric_result=executed["payload"].get("number"))
    built["execution"]=executed
    return built


def host_case(root,variant,browser=False):
    replace(root,"node.ts",'run(){return {result:multiply(library.implementation(2),2)};}','run(inputs,params,context){return {result:context.capabilities["demo.session"].next(2)};}')
    replace(root,"node.ts",'base_libs:["demo.math"],','capabilities:[{id:"demo.session",operations:["next"]}],base_libs:["demo.math"],')
    # Diagnostics are external test observations, never shared session state.
    replace(root,"host_support.ts",'let active=false;','globalThis.__events.push("create");let active=false;')
    replace(root,"host_support.ts",'start(){active=true;}', 'start(){globalThis.__events.push("start");active=true;}')
    replace(root,"host_support.ts",'stop(){active=false;}', 'stop(){globalThis.__events.push("stop");active=false;}')
    built=cli(root,"build",name="build",extra=["--target","browser" if browser else "node","--profile","single-esm","--out-dir",root/"dist"])
    if built["metrics"]["exit_code"]:return built,{}
    entry=built["payload"]["entry"]
    body='globalThis.__events=[];const a=workflow.createWorkflowHost();await a.start();'
    expected={"value":4,"events":["create","start","stop"],"stopped":True}
    if variant=="dual":
        body+='const b=workflow.createWorkflowHost();await b.start();const value=a.runWorkflow({}).number;const second=a.runWorkflow({}).number;const independent=b.runWorkflow({}).number;await b.stop();'
        expected.update(second=5,independent=4,events=["create","start","create","start","stop","stop"])
    elif variant=="idempotent":
        body+='await a.start();const value=a.runWorkflow({}).number;await a.stop();await a.stop();'
    elif variant=="cancel":
        body+='const controller=new AbortController();controller.abort("cancelled");let cancelled=false;try{a.runWorkflow({},{signal:controller.signal});}catch(error){cancelled=error.code==="VF_ABORTED";}const value=a.runWorkflow({}).number;'
        expected["cancelled"]=True
    elif variant=="fifo":
        body+='const values=[];for(const value of [2,2,2])values.push(a.runWorkflow({}).number);const value=values[0];'
        expected["fifo"]=[4,5,6]
    elif variant=="timer":
        body+='const value=await new Promise(resolve=>setTimeout(()=>resolve(a.runWorkflow({}).number),5));'
    elif variant=="receipt":
        body+='const receipts=new Map();for(const id of ["first","second"])receipts.set(id,a.runWorkflow({}).number);const value=receipts.get("first");'
        expected["receipts"]=[["first",4],["second",5]]
    else:body+='const value=a.runWorkflow({}).number;'
    body+='await a.stop();return {value,events:globalThis.__events,stopped:!a.started'+(',second,independent' if variant=="dual" else ',cancelled' if variant=="cancel" else ',fifo:values' if variant=="fifo" else ',receipts:[...receipts]' if variant=="receipt" else '')+'};'
    if browser:executed=execute(root,body,browser=True,entry=entry)
    else:executed=execute(root,'const workflow=await import('+json.dumps(Path(entry).as_uri())+');console.log(JSON.stringify(await(async()=>{'+body+'})()));')
    built["metrics"].update(runtime_exit_code=executed["metrics"]["exit_code"],**executed["payload"])
    built["execution"]=executed
    return built,{"runtime_exit_code":0,**expected}


def run_cases(work,toolchain):
    rows=[]
    for target,browser in (("python",False),("javascript",False),("javascript",True)):
        for variant in ("serial","branch","nodeset","loop","unused_file","edit_run"):
            case=f"runtime.{target}.{'browser' if browser else 'native'}.{variant}"
            root=project(work/case,target,toolchain);actual=runtime(root,target,variant,browser=browser)
            metrics={"numeric_result":8 if variant=="edit_run" else 6}
            if target!="python":metrics["runtime_exit_code"]=0
            rows.append(observe(case,"resource-runtime",actual,metrics=metrics))
    for browser in (False,True):
        for variant in ("single","dual","idempotent","cancel","fifo","timer","receipt"):
            case=f"runtime.host.{'browser' if browser else 'node'}.{variant}"
            root=project(work/case,toolchain=toolchain);actual,metrics=host_case(root,variant,browser)
            rows.append(observe(case,"resource-runtime",actual,metrics=metrics))
    from resource_host_runtime import run_cases as host_sessions
    rows.extend(host_sessions(work,toolchain))
    from resource_runtime_extra import run_cases as additional
    rows.extend(additional(work,toolchain))
    return rows
