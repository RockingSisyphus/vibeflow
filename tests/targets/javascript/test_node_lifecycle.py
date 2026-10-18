"""Ordinary Node lifecycle in emitted JavaScript, including actual cleanup."""
import json
from pathlib import Path
import subprocess
import pytest

from tests.targets.javascript.aot_fixtures import emit_fixture


def lifecycle_plan():
    terminal=lambda name:{"id":name,"type_used":"fixture.terminal","flow_kind":"terminal","is_terminal":True,
        "implementation":{"kind":"file","ref":"./nodes.mjs","export":"terminal"}}
    return {"entry_mode":"async","inputs":[{"key":"scenario","type":"scenario","required":True}],
        "outputs":[{"type":"value","cardinality":"exactly_one","as":"value"}],
        "nodes":[terminal("start"),{"id":"worker","type_used":"fixture.worker","flow_kind":"process",
            "completion":"suspend","requires":[{"type":"scenario"}],"provides":[{"key":"value","type":"value"}],
            "implementation":{"kind":"file","ref":"./nodes.mjs","export":"worker"}},terminal("end")],
        "routes":[{"source":"start","target":"worker"},{"source":"worker","target":"end"}]}





def test_capability_race_loser_is_owned_until_actual_execution_and_cleanup(tmp_path):
    plan = lifecycle_plan()
    worker = plan["nodes"][1]
    worker["capabilities"] = [{"id":"fixture.ops","operations":["fast","slow"]}]
    plan["capabilities"] = [{"id":"fixture.ops","operations":{
        key:{"input_type":"request","output_type":"value","completion":"suspend"}
        for key in ("fast","slow")}}]
    (tmp_path/"workflow.mjs").write_text(emit_fixture(plan).source)
    (tmp_path/"nodes.mjs").write_text('''
export function terminal(){return {};}
export async function worker(inputs,params,context) {
 const value=await Promise.race([context.capabilities['fixture.ops'].fast({}),context.capabilities['fixture.ops'].slow({})]);
 globalThis.events.push('node_body_return');
 return {value};
}

''')
    (tmp_path/"consumer.mjs").write_text('''
import {runWorkflowAsync} from './workflow.mjs';
globalThis.events=[];
let release,started;
const began=new Promise(resolve=>started=resolve);
const operation=new Promise(resolve=>release=resolve);
let finished=false;
const running=runWorkflowAsync({scenario:'race'},{trace:'off',capabilities:{'fixture.ops':{
 fast:()=>Promise.resolve('winner'),
 slow:async(_,context)=>{started();await operation;events.push('underlying_done');await new Promise(resolve=>setTimeout(resolve,40));events.push('cleanup_done');return 'loser';},
}}}).then(result=>{finished=true;events.push('notified');return result;});
await began;
await new Promise(resolve=>setTimeout(resolve,0));
if(finished||events.includes('notified'))throw new Error('uncooperative loser escaped Node ownership');
if(!events.includes('node_body_return'))throw new Error('race winner was not delivered');
release();
const result=await running;
if(events.indexOf('cleanup_done')>events.indexOf('notified'))throw new Error('early final notification');
console.log(JSON.stringify({result,events}));
''')
    completed=subprocess.run(["node",str(tmp_path/"consumer.mjs")],capture_output=True,text=True,timeout=10)
    assert completed.returncode == 0, completed.stderr
    result=json.loads(completed.stdout)
    assert result["result"]["value"]=="winner"
    assert result["events"]==["node_body_return","underlying_done","cleanup_done","notified"]


def test_cancelled_node_can_await_capability_cleanup_before_workflow_returns(tmp_path):
    plan=lifecycle_plan()
    worker=plan["nodes"][1]
    worker["capabilities"]=[{"id":"fixture.ops","operations":["block","cleanup"]}]
    plan["capabilities"]=[{"id":"fixture.ops","operations":{
        key:{"input_type":"request","output_type":"value","completion":"suspend"}
        for key in ("block","cleanup")}}]
    (tmp_path/"workflow.mjs").write_text(emit_fixture(plan).source)
    (tmp_path/"nodes.mjs").write_text('''
export function terminal(){return {};}
export async function worker(inputs,params,context) {
 try {return {value:await context.capabilities['fixture.ops'].block({})};}
 finally {await context.capabilities['fixture.ops'].cleanup({});globalThis.events.push('cleanup_done');}
}

''')
    (tmp_path/"consumer.mjs").write_text('''
import {runWorkflowAsync} from './workflow.mjs';
globalThis.events=[];
const controller=new AbortController();
let began,cleaning,release;
const started=new Promise(resolve=>began=resolve);
const cleanupStarted=new Promise(resolve=>cleaning=resolve);
const barrier=new Promise(resolve=>release=resolve);
let finished=false;const statuses=[];
const running=runWorkflowAsync({scenario:'cancel'},{trace:'off',signal:controller.signal,onStatus:s=>statuses.push(s.state),capabilities:{'fixture.ops':{
 block:(_,context)=>new Promise((resolve,reject)=>{began();context.signal.addEventListener('abort',()=>reject(new DOMException('cancelled','AbortError')),{once:true});}),
 cleanup:async(_,context)=>{if(!context.signal.aborted)throw new Error('cancel not delivered');cleaning();await barrier;return 'cleaned';},
}}}).then(()=>{finished=true;return {success:true};},error=>{finished=true;return {code:error.code};});
await started;controller.abort('stop');await cleanupStarted;
if(finished)throw new Error('workflow returned before cleanup');
if(statuses.at(-1)!=='stopping')throw new Error('not observably stopping');
release();const result=await running;
if(events.at(-1)!=='cleanup_done')throw new Error('cleanup missing');
console.log(JSON.stringify({result,events,statuses}));
''')
    completed=subprocess.run(["node",str(tmp_path/"consumer.mjs")],capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
    result=json.loads(completed.stdout)
    assert result["result"]["code"]=="VF_ABORTED"
    assert result["statuses"]==["starting","running","stopping","failed"]










@pytest.mark.parametrize('primary',[False,True])
def test_capability_cleanup_failure_after_node_body_preserves_primary(tmp_path,primary):
    plan=lifecycle_plan();worker=plan['nodes'][1]
    worker['capabilities']=[{'id':'fixture.ops','operations':['block']}]
    plan['capabilities']=[{'id':'fixture.ops','operations':{'block':{'input_type':'request','output_type':'value','completion':'suspend'}}}]
    (tmp_path/'workflow.mjs').write_text(emit_fixture(plan).source)
    (tmp_path/'nodes.mjs').write_text('''
export function terminal(){return {};}
export async function worker(inputs,params,context){
 await Promise.race([context.capabilities['fixture.ops'].block({}),Promise.resolve('fast')]);
 if(inputs.scenario.value==='primary')throw new Error('node primary failure');
 return {value:'fast'};
}

''')
    (tmp_path/'consumer.mjs').write_text('''
import {runWorkflowAsync} from './workflow.mjs';
const events=[];
let failure;try {await runWorkflowAsync({scenario:SCENARIO},{capabilities:{'fixture.ops':{
 block:(_,context)=>new Promise((resolve,reject)=>{
  context.signal.addEventListener('abort',()=>{
   events.push('cleanup_started');
   Promise.resolve().then(()=>{events.push('cleanup_finished');reject(new Error('operation cleanup failure'));});
  },{once:true});
 })
}}});}catch(error){failure={message:error.message,cause:String(error.cause),cleanup_errors:(error.cleanupErrors||[]).map(item=>({message:item.message,cause:String(item.cause)}))};}
events.push('notified');console.log(JSON.stringify({failure,events}));
'''.replace('SCENARIO',json.dumps('primary' if primary else 'normal')))
    completed=subprocess.run(['node',str(tmp_path/'consumer.mjs')],capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
    data=json.loads(completed.stdout);outcome=data['failure']
    assert outcome,data
    assert data['events']==['cleanup_started','cleanup_finished','notified']
    assert 'operation cleanup failure' in json.dumps(outcome)
    if primary:
        assert 'node primary failure' in outcome['cause']
        assert outcome['cleanup_errors']


def test_branch_failure_cancels_siblings_and_waits_for_real_finally(tmp_path):
    terminal=lambda name:{'id':name,'type_used':'native.boundary','flow_kind':'terminal','is_terminal':True,
        'implementation':{'kind':'file','ref':'./nodes.mjs','export':'terminal'}}
    worker=lambda name:{'id':name,'type_used':'native.'+name,'flow_kind':'process','completion':'suspend',
        'implementation':{'kind':'file','ref':'./nodes.mjs','export':name}}
    plan={'entry_mode':'async','nodes':[terminal('start'),worker('slow'),worker('failure'),
        {**terminal('end'),'join_policy':'all'}],
        'routes':[{'source':a,'target':b} for a,b in [('start','slow'),('start','failure'),('slow','end'),('failure','end')]]}
    (tmp_path/'workflow.mjs').write_text(emit_fixture(plan).source)
    (tmp_path/'nodes.mjs').write_text('''
let began;const started=new Promise(resolve=>began=resolve);
export function terminal(){return {};}
export async function slow(inputs,params,context){
 began();
 try {await new Promise(resolve=>context.signal.addEventListener('abort',resolve,{once:true}));}
 finally {await new Promise(resolve=>setTimeout(resolve,20));globalThis.cleaned=true;}
 return {};
}
export async function failure(){await started;throw new Error('sibling failed');}
''')
    (tmp_path/'probe.mjs').write_text('''
import {runWorkflowAsync} from './workflow.mjs';
let failure;try{await runWorkflowAsync({});}catch(error){failure=error;}
if(!failure || !String(failure.cause).includes('sibling failed'))throw Error('failure lost');
if(!globalThis.cleaned)throw Error('finally still active after workflow returned');
console.log('cleaned');
''')
    result=subprocess.run(['node',str(tmp_path/'probe.mjs')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='cleaned'
