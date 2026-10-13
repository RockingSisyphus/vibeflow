"""Native task controller behavior in emitted JavaScript, including actual cleanup."""
import json
from pathlib import Path
import subprocess
import pytest

from tests.targets.javascript.aot_fixtures import emit_fixture


def task_plan():
    terminal = lambda key: {"id":key,"type_used":"fixture.terminal","implementation":{"kind":"file","ref":"./nodes.mjs","export":"terminal"},"flow_kind":"terminal","is_terminal":True}
    worker = {"id":"worker", "type_used":"fixture.worker", "flow_kind":"process", "completion":"suspend",
              "requires":[{"type":"request"}], "provides":[{"key":"value","type":"value"}],
              "implementation":{"kind":"file","ref":"./nodes.mjs","export":"worker"}}
    manager = {"id":"manage","type_used":"fixture.manager","flow_kind":"task_manager","completion":"suspend",
               "requires":[{"type":"scenario"}],"provides":[{"key":"report","type":"report"}],
               "implementation":{"kind":"file","ref":"./nodes.mjs","export":"manage"},
               "task_targets":{"worker":{"nodes":[worker],"entries":["worker"],
                   "inputs":[{"key":"request","type":"request","required":True}],"outputs":[]}}}
    return {"workflow_id":"fixture.tasks","entry_mode":"async",
            "inputs":[{"key":"scenario","type":"scenario","required":True}],
            "outputs":[{"type":"report","cardinality":"exactly_one","as":"report"}],
            "nodes":[terminal("start"),manager,terminal("end")],
            "routes":[{"source":"start","target":"manage"},{"source":"manage","target":"end"}],
            "schemas":{"scenario":{"type":"string"},"request":{"type":"object"},"value":{"type":"string"},"report":{"type":"array"}}}


def test_task_results_ownership_cancellation_and_late_waits(tmp_path):
    (tmp_path/"workflow.mjs").write_text(emit_fixture(task_plan()).source)
    (tmp_path/"nodes.mjs").write_text('''
export function terminal(){return {};}
export async function worker(inputs, params, context) {
 const {scenario,label}=inputs.request.value;
 globalThis.events.push('start:'+label);
 let listener;
 try {
  if(scenario==='failure' && label==='B') throw new Error('B failed');
  if(scenario==='success') return {value:label};
  if(scenario==='uncooperative') await new Promise(resolve=>globalThis.release=resolve);
  else await new Promise(resolve=>{
   listener=resolve;context.signal.addEventListener('abort',listener,{once:true});
   if(context.signal.aborted)resolve();
  });
  return {value:label};
 } finally {
  if(listener)context.signal.removeEventListener('abort',listener);
  globalThis.events.push('cleanup_start:'+label);
  await new Promise(resolve=>setTimeout(resolve,40));
  globalThis.events.push('cleanup_end:'+label);
 }
}
export async function manage(inputs,params,context) {
 const scenario=inputs.scenario.value;
 const refs=['A','B','C'].map(label=>context.tasks.start('worker',{request:{scenario,label}}));
 if(scenario==='failure') {
  const first=await context.tasks.waitAny(refs);
  if(first.task.task_id!==refs[1].task_id || first.status!=='failed')throw new Error('wrong first failure');
  if(!events.includes('cleanup_end:B'))throw new Error('early notification');
  globalThis.events.push('notified');
  context.tasks.requestStop(refs.filter(ref=>ref!==refs[1]));
 } else if(scenario==='stop_return'||scenario==='stop_wait') {
  await Promise.resolve(); await Promise.resolve();
  context.tasks.requestStop(refs);
  if(scenario==='stop_wait') await context.tasks.waitAllExited(refs);
  globalThis.events.push('manager_return');
  return {report:refs};
 }
 const outcomes=await context.tasks.waitAllExited([...refs,refs[0]]);
 if(outcomes.length!==3)throw new Error('not deduplicated');
 const late=await context.tasks.waitAny([refs[1]]);
 if(late!==outcomes[1])throw new Error('late result changed');
 if(await context.tasks.waitAny([])!==null)throw new Error('empty any');
 if((await context.tasks.waitAllExited([])).length)throw new Error('empty all');
 if(context.tasks.requestStop(refs).some(ack=>ack.state!=='already_exited'))throw new Error('live control retained');
 for (const invalid of [[{run_id:'foreign',task_id:'1'}],[{...refs[0],task_id:'missing'}]]) {
  try{await context.tasks.waitAny(invalid);throw new Error('bad ref accepted');}
  catch(error){if(error.code!=='VF_TASK_REF_INVALID')throw error;}
 }
 try{context.tasks.start('missing',{});throw new Error('bad target accepted');}
 catch(error){if(error.code!=='VF_TASK_TARGET_UNKNOWN')throw error;}
 return {report:outcomes};
}
''')
    consumer = '''
import {runWorkflowAsync} from './workflow.mjs';
const rows=[];
for(const scenario of ['failure','success','stop_return','stop_wait']) {
 globalThis.events=[];
 const result=await runWorkflowAsync({scenario},{trace:'off'});
 events.push('workflow_return');
 if(scenario==='stop_return' && events.indexOf('manager_return')>events.indexOf('cleanup_end:A'))throw new Error('stop request implicitly joined');
 if(scenario==='stop_wait' && events.indexOf('manager_return')<events.indexOf('cleanup_end:A'))throw new Error('join returned early');
 for(const label of ['A','B','C'])if(events.indexOf('cleanup_end:'+label)>events.indexOf('workflow_return'))throw new Error('root returned early');
 rows.push({scenario,result,events});
}
console.log(JSON.stringify(rows));
'''
    (tmp_path/"consumer.mjs").write_text(consumer)
    completed=subprocess.run(["node",str(tmp_path/"consumer.mjs")],capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
    rows=json.loads(completed.stdout)
    assert [item["status"] for item in rows[0]["result"]["report"]]==["cancelled","failed","cancelled"]
    assert [item["outputs"]["value"] for item in rows[1]["result"]["report"]]==["A","B","C"]


def test_capability_race_loser_is_owned_until_actual_execution_and_cleanup(tmp_path):
    plan = task_plan()
    worker = plan["nodes"][1]["task_targets"]["worker"]["nodes"][0]
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
export async function manage(inputs,params,context) {
 const ref=context.tasks.start('worker',{request:{}});
 const result=await context.tasks.waitAny([ref]);
 globalThis.events.push('notified');
 return {report:[result]};
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
}}}).then(result=>{finished=true;return result;});
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
    assert result["result"]["report"][0]["outputs"]["value"]=="winner"
    assert result["events"]==["node_body_return","underlying_done","cleanup_done","notified"]


def test_cancelled_node_can_await_capability_cleanup_before_workflow_returns(tmp_path):
    plan=task_plan()
    worker=plan["nodes"][1]["task_targets"]["worker"]["nodes"][0]
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
export async function manage(inputs,params,context) {
 const ref=context.tasks.start('worker',{request:{}});
 const result=await context.tasks.waitAny([ref]);
 return {report:[result]};
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


@pytest.mark.parametrize('nested',[False,True])
def test_task_target_all_inputs_preserve_envelopes(tmp_path,nested):
    plan=task_plan();target=plan['nodes'][1]['task_targets']['worker']['nodes'][0]
    target['requires']=[{'type':'number','cardinality':'all'}]
    target['provides']=[{'key':'sum','type':'number'}]
    plan['nodes'][1]['task_targets']['worker']['inputs']=[{'key':'number','type':'number','required':False}]
    plan['schemas']['number']={'type':'number'}
    if nested:
        from copy import deepcopy
        body=deepcopy(target)
        target.pop('implementation');target['is_nodeset']=True
        start,end=deepcopy(plan['nodes'][0]),deepcopy(plan['nodes'][2])
        target['subplan']={'nodes':[start,body,end],'entries':['start'],
            'routes':[{'source':'start','target':'worker'},{'source':'worker','target':'end'}],
            'inputs':[{'key':'numbers','type':'number','required':False}],
            'outputs':[{'type':'number','cardinality':'exactly_one','as':'sum'}]}
    (tmp_path/'workflow.mjs').write_text(emit_fixture(plan).source)
    (tmp_path/'nodes.mjs').write_text('''
export function terminal(){return {};}
export function worker(inputs){return {sum:inputs.number.reduce((total,item)=>total+item.value,0)};}
export async function manage(inputs,params,context){
 const refs=[[],[1],[1,2,3]].map(number=>context.tasks.start('worker',{number}));
 const outcomes=await context.tasks.waitAllExited(refs);
 return {report:outcomes};
}
''')
    (tmp_path/'consumer.mjs').write_text("import {runWorkflowAsync} from './workflow.mjs';console.log(JSON.stringify(await runWorkflowAsync({scenario:'all'})));" )
    result=subprocess.run(['node',str(tmp_path/'consumer.mjs')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    outcomes=json.loads(result.stdout)['report']
    assert [item['status'] for item in outcomes]==['succeeded']*3,outcomes
    assert [item['outputs']['sum'] for item in outcomes]==[0,1,6]


def test_many_short_tasks_keep_late_results_without_restarting(tmp_path):
    (tmp_path/'workflow.mjs').write_text(emit_fixture(task_plan()).source)
    (tmp_path/'nodes.mjs').write_text('''
export function terminal(){return {};}
export function worker(inputs){return {value:String(inputs.request.value.index)};}
export async function manage(inputs,params,context){
 const refs=[];
 for(let batch=0;batch<8;batch++){
  const current=Array.from({length:64},(_,index)=>context.tasks.start('worker',{request:{index:batch*64+index}}));
  const outcomes=await context.tasks.waitAllExited(current);
  if(outcomes.some(outcome=>outcome.status!=='succeeded'))throw new Error('short task failed');
  refs.push(...current);
 }
 if(new Set(refs.map(ref=>ref.task_id)).size!==512)throw new Error('identity reused');
 if((await context.tasks.waitAny([{...refs[0]}])).outputs.value!=='0')throw new Error('late result lost');
 if(context.tasks.requestStop(refs).some(ack=>ack.state!=='already_exited'))throw new Error('active control retained');
 return {report:await context.tasks.waitAllExited([...refs,refs[0]])};
}
''')
    (tmp_path/'consumer.mjs').write_text('''
import {runWorkflowAsync} from './workflow.mjs';
const trace=[];const result=await runWorkflowAsync({scenario:'short'},{trace:'full',onTrace:event=>trace.push(event)});
console.log(JSON.stringify({count:result.report.length,last:result.report.at(-1).outputs.value,
 started:trace.filter(event=>event.kind==='task_started').length,exited:trace.filter(event=>event.kind==='task_exited').length}));
''')
    completed=subprocess.run(['node',str(tmp_path/'consumer.mjs')],capture_output=True,text=True,timeout=15)
    assert completed.returncode==0,completed.stderr
    assert json.loads(completed.stdout)=={'count':512,'last':'511','started':512,'exited':512}


@pytest.mark.parametrize('primary',[False,True])
def test_capability_cleanup_failure_after_node_body_preserves_primary(tmp_path,primary):
    plan=task_plan();worker=plan['nodes'][1]['task_targets']['worker']['nodes'][0]
    worker['capabilities']=[{'id':'fixture.ops','operations':['block']}]
    plan['capabilities']=[{'id':'fixture.ops','operations':{'block':{'input_type':'request','output_type':'value','completion':'suspend'}}}]
    (tmp_path/'workflow.mjs').write_text(emit_fixture(plan).source)
    (tmp_path/'nodes.mjs').write_text('''
export function terminal(){return {};}
export async function worker(inputs,params,context){
 await Promise.race([context.capabilities['fixture.ops'].block({}),Promise.resolve('fast')]);
 if(inputs.request.value.primary)throw new Error('node primary failure');
 return {value:'fast'};
}
export async function manage(inputs,params,context){
 const ref=context.tasks.start('worker',{request:{primary:inputs.scenario.value==='primary'}});
 return {report:[await context.tasks.waitAny([ref])]};
}
''')
    (tmp_path/'consumer.mjs').write_text('''
import {runWorkflowAsync} from './workflow.mjs';
const events=[];
const result=await runWorkflowAsync({scenario:SCENARIO},{capabilities:{'fixture.ops':{
 block:(_,context)=>new Promise((resolve,reject)=>{
  context.signal.addEventListener('abort',()=>{
   events.push('cleanup_started');
   Promise.resolve().then(()=>{events.push('cleanup_finished');reject(new Error('operation cleanup failure'));});
  },{once:true});
 })
}}});
events.push('notified');console.log(JSON.stringify({result,events}));
'''.replace('SCENARIO',json.dumps('primary' if primary else 'normal')))
    completed=subprocess.run(['node',str(tmp_path/'consumer.mjs')],capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
    data=json.loads(completed.stdout);outcome=data['result']['report'][0]
    assert outcome['status']=='failed',data
    assert data['events']==['cleanup_started','cleanup_finished','notified']
    assert 'operation cleanup failure' in json.dumps(outcome)
    if primary:
        assert 'node primary failure' in outcome['error']['message']
        assert outcome['error']['cleanup_errors']
