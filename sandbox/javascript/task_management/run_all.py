"""Formal Node and Chromium AOT acceptance using the public SDK and CLI."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from tests.fixtures.support.addition_sandboxes import cli, workspace


SCENARIOS = ("failure", "unexpected_failure", "success", "stop_return", "stop_wait", "uncooperative",
             "selective", "invalid_refs", "cleanup_failure", "concurrent_failure", "root_failure", "unobserved_failure", "external_cancel")

CONSUMER = r'''
async function probe(workflow) {
 const timers=new Set(),listeners=new Set(),bindings=new WeakMap();
 const timeout=globalThis.setTimeout,clearTimeout=globalThis.clearTimeout;
 const interval=globalThis.setInterval,clearInterval=globalThis.clearInterval;
 const add=EventTarget.prototype.addEventListener,remove=EventTarget.prototype.removeEventListener;
 globalThis.setTimeout=(callback,delay,...args)=>{let handle=timeout(()=>{timers.delete(handle);callback(...args);},delay);timers.add(handle);return handle;};
 globalThis.clearTimeout=handle=>{timers.delete(handle);return clearTimeout(handle);};
 globalThis.setInterval=(callback,delay,...args)=>{const handle=interval(callback,delay,...args);timers.add(handle);return handle;};
 globalThis.clearInterval=handle=>{timers.delete(handle);return clearInterval(handle);};
 EventTarget.prototype.addEventListener=function(type,callback,options){
  if(type!=='abort' || !(this instanceof AbortSignal) || !callback)return add.call(this,type,callback,options);
  let entries=bindings.get(this);if(!entries)bindings.set(this,entries=new Map());
  const existing=entries.get(callback);if(existing)return add.call(this,type,existing.wrapped,options);
  const record={target:this,callback,wrapped:null};
  record.wrapped=event=>{if(options?.once){listeners.delete(record);entries.delete(callback);}return typeof callback==='function'?callback.call(this,event):callback.handleEvent(event);};
  entries.set(callback,record);listeners.add(record);return add.call(this,type,record.wrapped,options);
 };
 EventTarget.prototype.removeEventListener=function(type,callback,options){
  const entries=bindings.get(this),record=type==='abort' && entries?.get(callback);
  if(record){entries.delete(callback);listeners.delete(record);return remove.call(this,type,record.wrapped,options);}
  return remove.call(this,type,callback,options);
 };
 const resourceCheck=()=>{if(timers.size || listeners.size)throw new Error('workflow resources retained: '+JSON.stringify({timers:timers.size,listeners:listeners.size}));return {timers:timers.size,listeners:listeners.size};};
 try {
 const rows=[];
 for(const scenario of SCENARIOS) {
  const trace=[];const controller=new AbortController();let started=0;
  let result,error;
  try {result=await (scenario==='unobserved_failure' ? solo : workflow).runWorkflowAsync({scenario},{signal:controller.signal,trace:'full',onTrace:event=>{
   trace.push(event);
   if(scenario==='external_cancel' && event.kind==='node_trace' && event.event==='worker_started' && ++started===3)controller.abort('external stop');
  }});}catch(cause){error={code:cause.code,message:cause.message,taskErrors:cause.taskErrors,cause:String(cause.cause)};}
  rows.push({scenario,result,error,trace,resources:resourceCheck()});
 }
 const trace=[];const result=await solo.runWorkflowAsync({scenario:'stop_return'},{trace:'full',onTrace:event=>trace.push(event)});
 rows.push({scenario:'workflow_join',result,trace,resources:resourceCheck()});
 for(const [config,workflow] of [['nested',nested],['nested_manager',nestedManager]]) {
  for(const scenario of ['success','stop_wait']){
   const trace=[];const result=await workflow.runWorkflowAsync({scenario},{trace:'full',onTrace:event=>trace.push(event)});
   rows.push({scenario,config,result,trace,resources:resourceCheck()});
  }
 }
 return rows;
 } finally {
  globalThis.setTimeout=timeout;globalThis.clearTimeout=clearTimeout;
  globalThis.setInterval=interval;globalThis.clearInterval=clearInterval;
  EventTarget.prototype.addEventListener=add;EventTarget.prototype.removeEventListener=remove;
 }
}
'''.replace('SCENARIOS',json.dumps(SCENARIOS))


def check(row):
    scenario, result, trace = row["scenario"], row.get("result"), row["trace"]
    if row.get("config"):
        assert [item["status"] for item in result["report"]]==(["succeeded"]*3 if scenario=="success" else ["cancelled"]*3),row
        expected=4 if row["config"]=="nested_manager" else 3
        assert sum(event["kind"]=="task_exited" for event in trace)==expected,row
        assert sum(event.get("event")=="cleanup_finished" for event in trace)==3,row
        if row["config"]=="nested_manager":assert any(event.get("event")=="nested_joined" for event in trace),row
        return
    if scenario in ("root_failure", "unobserved_failure", "external_cancel"):
        assert row["error"]["code"] == {"root_failure":"VF_NODE_FAILED", "unobserved_failure":"VF_TASK_UNOBSERVED", "external_cancel":"VF_ABORTED"}[scenario],row
    elif scenario != "workflow_join":
        statuses = [item["status"] for item in result["report"]]
        expected = ["cancelled", "failed", "cancelled"] if scenario in ("failure", "unexpected_failure", "cleanup_failure") else ["succeeded"] * 3 if scenario == "success" else ["failed"] * 3 if scenario=="concurrent_failure" else ["cancelled"] * 3
        assert statuses == expected, row
    events = [event for event in trace if event["kind"] == "node_trace"]
    index = lambda kind, label=None: next(i for i,event in enumerate(events) if event["event"]==kind and (label is None or event["details"].get("label")==label))
    for label in ("A", "B", "C"):
        assert index("cleanup_started",label)<index("cleanup_finished",label),row
        if result and scenario!="workflow_join":assert index("cleanup_finished", label) < index("control_joined"), row
    if scenario in ("failure", "unexpected_failure", "cleanup_failure"):
        first = events[index("first_outcome")]["details"]["outcome"]
        assert first["task"]["task_id"] == "2" and first["status"] == "failed", row
        assert index("cleanup_finished", "B") < index("first_outcome"), row
    if scenario in ("stop_return", "workflow_join"):
        assert index("manager_return") < index("cleanup_finished", "A"), row
    if scenario == "uncooperative":
        for label in ("A", "B", "C"):
            assert index("manager_return") < index("underlying_finished", label) < index("cleanup_finished",label), row
    if scenario == "stop_wait":
        assert index("cleanup_finished", "A") < index("manager_return"), row
    expected_count=4 if scenario=="selective" else 3
    assert sum(event["kind"] == "task_started" for event in trace) == expected_count
    assert sum(event["kind"] == "task_exited" for event in trace) == expected_count
    if scenario=="invalid_refs":assert sum(event.get("event")=="expected_contract_error" for event in trace)==3,row
    if scenario=="cleanup_failure":assert "cleanup failed" in json.dumps(result) and "failed deliberately" in json.dumps(result),row


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def browser(work, puppeteer_root):
    server = ThreadingHTTPServer(("127.0.0.1",0),partial(QuietHandler,directory=str(work)))
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    script = r'''
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(DRIVER);
const {default:puppeteer}=await import(pathToFileURL(require.resolve('puppeteer')).href);
const browser=await puppeteer.launch({headless:true,args:['--no-sandbox','--disable-setuid-sandbox']});
try {
 const page=await browser.newPage();const errors=[];
 page.on('pageerror',error=>errors.push(String(error)));
 await page.goto(PROBE_BASE);
 const rows=await page.evaluate(async ()=>{
  const workflow=await import('/build-browser/workflow.js');const solo=await import('/build-browser-solo/workflow.js');
  const nested=await import('/build-browser-nested/workflow.js');const nestedManager=await import('/build-browser-nested_manager/workflow.js');
  CONSUMER
  return await probe(workflow);
 });
 await page.goto(PROBE_BASE+'build-web/index.html');
 await page.click('#run');
 await page.waitForFunction(()=>document.querySelector('#output')?.textContent.startsWith('{'));
 const web=await page.$eval('#output',element=>JSON.parse(element.textContent));
 if(errors.length)throw new Error(JSON.stringify(errors));
 process.stdout.write(JSON.stringify({browser:await browser.version(),errors,rows,web}));
} finally {await browser.close();}
'''.replace('CONSUMER',CONSUMER).replace('DRIVER',json.dumps(str(puppeteer_root.resolve()/'package.json'))).replace('PROBE_BASE',json.dumps(f'http://127.0.0.1:{server.server_port}/'))
    probe = work / "browser-probe.mjs"
    probe.write_text(script)
    try:
        completed = subprocess.run(["node",str(probe)],capture_output=True,text=True,timeout=50)
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        (work/"browser-proof.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
        for row in result["rows"]:
            check(row)
        check({"scenario":"failure",**result["web"]})
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def run(work, *, toolchain, puppeteer_root):
    workspace(FIXTURE,work,toolchain)
    observations=[]
    for target, profile, name in (("node","esm-module","node"),("browser","esm-module","browser"),("browser","web-app","web")):
        command=["build","--workspace",work/"vibeflow_config.jsonc","--config",work/"project/configs/tasks.jsonc",
                 "--target",target,"--profile",profile,"--out-dir",work/("build-"+name)]
        if profile=="web-app":
            command += ["--html",work/"project/web/index.template.html","--app-entry",work/"project/web/app.ts"]
        result=json.loads(cli(command).stdout)
        assert result["status"] in {"PASS","CONCERNS"},result
        (work/(name+"-build-proof.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2))
        observations.append({"target":target,"profile":profile,"status":result["status"]})
        if profile=="esm-module":
            solo_command=list(command)
            solo_command[solo_command.index("--config")+1]=work/"project/configs/launch_only.jsonc"
            solo_command[-1]=work/("build-"+name+"-solo")
            solo_result=json.loads(cli(solo_command).stdout)
            assert solo_result["status"] in {"PASS","CONCERNS"},solo_result
            observations.append({"target":target,"profile":profile,"config":"launch_only","status":solo_result["status"]})
            for nested in ("nested","nested_manager"):
                nested_command=list(command)
                nested_command[nested_command.index("--config")+1]=work/"project/configs"/(nested+".jsonc")
                nested_command[-1]=work/("build-"+name+"-"+nested)
                nested_result=json.loads(cli(nested_command).stdout)
                assert nested_result["status"] in {"PASS","CONCERNS"},nested_result
                observations.append({"target":target,"profile":profile,"config":nested,"status":nested_result["status"]})
    consumer=work/"consumer.mjs"
    consumer.write_text("import * as workflow from './build-node/workflow.js';\nimport * as solo from './build-node-solo/workflow.js';\nimport * as nested from './build-node-nested/workflow.js';\nimport * as nestedManager from './build-node-nested_manager/workflow.js';\n"+CONSUMER+"\nconsole.log(JSON.stringify(await probe(workflow)));")
    completed=subprocess.run(["node",str(consumer)],cwd=work,capture_output=True,text=True,timeout=20)
    assert completed.returncode==0,completed.stderr
    rows=json.loads(completed.stdout)
    for row in rows:
        check(row)
        observations.append({"target":"node","scenario":row["scenario"],"status":"PASS"})
    proof=browser(work,puppeteer_root)
    observations.extend({"target":"Chromium","scenario":row["scenario"],"status":"PASS"} for row in proof["rows"])
    observations.append({"target":"Chromium","profile":"web-app","scenario":"failure","status":"PASS"})
    return {"status":"PASS","observations":observations,"browser":proof["browser"]}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir",type=Path)
    parser.add_argument("--toolchain-root",type=Path)
    parser.add_argument("--puppeteer-root",type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-task-management-") as temporary:
        work=args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True,exist_ok=True)
        report=run(work,toolchain=args.toolchain_root,puppeteer_root=args.puppeteer_root)
        (work/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(f"JavaScript task management: {report['status']} observations={len(report['observations'])} browser={report['browser']} report={work/'report.json'}")
