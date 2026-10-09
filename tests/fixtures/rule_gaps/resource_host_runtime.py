"""FIFO, timer and receipt ownership live in the actual Host support module."""
from pathlib import Path
import json

from resource_support import project, cli, replace, config, observe
from resource_runtime import execute

SUPPORT='''export function createSession(signal:AbortSignal){
  let active=false;let count=0;let timer:ReturnType<typeof setTimeout>|null=null;
  const queue:Array<{value:number;resolve:(value:number)=>void;reject:(reason:unknown)=>void}>=[];
  const receipts=new Map<number,number>();
  globalThis.__events.push("create");
  function pump(){
    timer=null;const item=queue.shift();if(!item)return;
    if(signal.aborted){item.reject(Error("cancelled"));return;}
    count+=1;const value=item.value+count;receipts.set(count,value);
    globalThis.__receipts.push([count,receipts.get(count)]);item.resolve(value);
    if(queue.length)timer=setTimeout(pump,5);
  }
  return {
    start(){active=true;globalThis.__events.push("start");},
    next(value:number){return new Promise<number>((resolve,reject)=>{
      if(!active){reject(Error("stopped"));return;}
      queue.push({value,resolve,reject});if(timer===null)timer=setTimeout(pump,5);
    });},
    stop(){active=false;if(timer!==null)clearTimeout(timer);timer=null;
      for(const item of queue.splice(0))item.reject(Error("cancelled"));
      globalThis.__events.push("stop");}
  };
}
'''


def run_cases(work,toolchain):
    rows=[]
    for browser in (False,True):
        for variant in ("fifo","receipts","cancel_timer","dual"):
            case=f"runtime.host_async.{'browser' if browser else 'node'}.{variant}"
            root=project(work/case,toolchain=toolchain)
            (root/"host_support.ts").write_text(SUPPORT)
            replace(root,"host.ts",'createHost(){const session=createSession();','createHost(context){const session=createSession(context.signal);')
            replace(root,"plugin.ts",'completion:"immediate"','completion:"suspend"')
            replace(root,"node.ts",'rulesets:["vibeflow.process"]','completion:"suspend",capabilities:[{id:"demo.session",operations:["next"]}],rulesets:["vibeflow.io"]')
            replace(root,"node.ts",'run(){return {result:multiply(library.implementation(2),2)};}','async run(inputs,params,context){return {result:await context.capabilities["demo.session"].next(2)};}')
            config(root,lambda data:data["pipeline"].update(entry_mode="async"))
            actual=cli(root,"build",name="build",extra=["--target","browser" if browser else "node","--profile","single-esm","--out-dir",root/"dist"])
            metrics={"runtime_exit_code":0,"events":["create","start","stop"]}
            script='globalThis.__events=[];globalThis.__receipts=[];const a=workflow.createWorkflowHost();await a.start();'
            if variant=="cancel_timer":
                script+='const pending=a.runWorkflowAsync({});await new Promise(resolve=>setTimeout(resolve,1));const settled=pending.then(()=>"resolved",()=>"cancelled");await a.stop();const value=await settled;await new Promise(resolve=>setTimeout(resolve,15));'
                metrics.update(value="cancelled",receipts=[])
            elif variant=="dual":
                script+='const b=workflow.createWorkflowHost();await b.start();const value=await Promise.all([a.runWorkflowAsync({}),a.runWorkflowAsync({}),b.runWorkflowAsync({})]);await b.stop();await a.stop();'
                metrics.update(value=[4,5,4],receipts=[[1,4],[1,4],[2,5]],events=["create","start","create","start","stop","stop"])
            else:
                script+='const value=await Promise.all([a.runWorkflowAsync({}),a.runWorkflowAsync({}),a.runWorkflowAsync({})]);await a.stop();'
                metrics.update(value=[4,5,6],receipts=[[1,4],[2,5],[3,6]])
            script+='return {value:Array.isArray(value)?value.map(item=>item.number):value,events:globalThis.__events,receipts:globalThis.__receipts};'
            if actual["metrics"]["exit_code"]==0:
                entry=actual["payload"]["entry"]
                execution=execute(root,script,browser=True,entry=entry) if browser else execute(root,'const workflow=await import('+json.dumps(Path(entry).as_uri())+');console.log(JSON.stringify(await(async()=>{'+script+'})()));')
                actual["metrics"].update(runtime_exit_code=execution["metrics"]["exit_code"],**execution["payload"])
                actual["execution"]=execution
            rows.append(observe(case,"resource-runtime",actual,metrics=metrics))
    return rows
