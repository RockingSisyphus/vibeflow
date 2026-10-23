"""The same bundled AOT host runs in Node and an actual page without transport."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.coordination.test_hosts import node_module
from tests.targets.javascript.aot_fixtures import plan_fixture
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.tooling.presentation.mermaid import _find_mmdc, is_mermaid_svg_renderer_available


@pytest.mark.parametrize('environment',['node','browser'])
def test_bundled_in_process_sync_async_and_actual_cleanup(tmp_path,environment):
    if environment == 'browser' and not is_mermaid_svg_renderer_available():
        pytest.skip('Chromium dependencies are supplied by the full gate')
    resources = Path(__file__).resolve().parents[2]/'src/vibeflow/targets/javascript/resources'
    # This peer is an emitted async workflow, including native cancellation.
    node_module(tmp_path)
    nodes = tmp_path/'nodes.mjs'
    nodes.write_text(nodes.read_text().replace('  const message=await api.receive', '  try {\n  const message=await api.receive').replace('  return {out:value};',
        '  return {out:value};\n  } finally {await new Promise(r=>setTimeout(r,5));globalThis.cleaned=(globalThis.cleaned||0)+1;}'))
    plan,bindings=plan_fixture({'entry_mode':'sync','nodes':[
        {'id':'calc','definition_id':'calc','is_terminal':True,'flow_kind':'terminal','implementation':{'kind':'file','ref':'./calc.mjs','export':'run'},
         'provides':[{'key':'out','type':'number'}]}],
        'outputs':[{'type':'number','as':'result','cardinality':'exactly_one'}]})
    (tmp_path/'calc.mjs').write_text('export function run(inputs,params,context){globalThis.childId=context.workflow.self().id;return {out:42};}')
    emitted=emit_workflow_module(plan,javascript_bindings=bindings,workflow_reference={'root':'test','path':'sync'})
    (tmp_path/'sync.mjs').write_text(emitted.source)
    script = '''
import assert from 'ASSERT';
import {Coordinator} from 'COORDINATOR';
import * as sync from './sync.mjs';
import * as peer from './workflow.mjs';
export async function probe(){
  const host=new Coordinator(),syncRef={root:'test',path:'sync'},peerRef={root:'test',path:'peer'};
  host.bind(sync.workflowDescriptor,sync.runWorkflow);
  host.bind({...peer.workflowDescriptor,workflow:peerRef},peer.runWorkflowAsync);
  const owner=host.register({root:'test',path:'application'}),api=host.operations(owner.id);
  for(let i=0;i<100;i++){
    const result=api.invoke_sync({workflow:syncRef});
    assert(result.result===42 && !result.then && globalThis.childId!==owner.id,'ordinary synchronous return');
  }
  assert(host.instances.size===1,'no synchronous records retained');
  let refused=false;
  try {api.invoke_sync({workflow:peerRef});}catch(error){refused=error.code==='VF_WORKFLOW_SYNC_UNSUPPORTED';}
  assert(refused,'async target refused');
  const a=await api.call({workflow:peerRef,launch:{kind:'in_process'}});
  const b=await api.call({workflow:peerRef,launch:{kind:'in_process'}});
  const waiting=new AbortController();
  const cancelled=api.wait({id:a.id},{signal:waiting.signal});waiting.abort(new DOMException('cancel wait','AbortError'));
  try {await cancelled;throw Error('wait accepted cancellation');}catch(error){assert(error.name==='AbortError','local cancellation');}
  assert(host.instance(a.id).state==='running','wait does not stop peer');
  api.send({id:a.id,port:'request',payload:{value:14}});
  const message=await api.receive({port:'reply'});
  assert(message.payload.value===42 && message.payload.self===a.id,'actual AOT message round trip');
  const first=await api.wait({id:a.id});
  assert(first.outputs.result===42,'actual AOT outputs');
  assert(JSON.stringify(first)===JSON.stringify(await api.wait({id:a.id})),'repeatable result');
  const second=await api.kill({id:b.id,workflow:peerRef});
  assert(second.state==='cancelled' && globalThis.cleaned===2,'kill awaits actual finally');
  host.release(a.id);host.release(b.id);
  const c=await api.call({workflow:peerRef,launch:{kind:'in_process'}});
  await new Promise(r=>setTimeout(r,5));
  await host.close();
  assert(globalThis.cleaned===3 && host.instances.size===0,'close awaits owned work');
  return {result:42,cleaned:globalThis.cleaned};
}
'''.replace("import assert from 'ASSERT';", "const assert=(condition,message)=>{if(!condition)throw Error(message);};").replace('COORDINATOR',(resources/'coordination/coordinator.mjs').as_posix())
    (tmp_path/'probe.mjs').write_text(script)
    esbuild=Path(os.environ['VIBEFLOW_TEST_TOOLCHAIN_ROOT'])/'node_modules/.bin/esbuild'
    result=subprocess.run([str(esbuild),str(tmp_path/'probe.mjs'),'--bundle','--format=iife','--platform=browser','--global-name=Probe',f'--outfile={tmp_path / "probe.js"}'],text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    if environment=='node':
        driver=tmp_path/'run.cjs'
        driver.write_text((tmp_path/'probe.js').read_text()+'\nProbe.probe().then(value=>console.log(JSON.stringify(value))).catch(error=>{console.error(error);process.exitCode=1;});')
        result=subprocess.run(['node',str(driver)],text=True,capture_output=True,timeout=20)
    else:
        driver=tmp_path/'browser.cjs'
        driver.write_text('''const {createRequire}=require('node:module');
const puppeteer=createRequire(process.argv[2])('puppeteer');
(async()=>{const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
try {const page=await browser.newPage();let network=0;page.on('request',()=>network++);
await page.goto('about:blank');await page.addScriptTag({path:process.argv[3]});
const result=await page.evaluate(()=>Probe.probe());if(network)throw Error('unexpected network requests: '+network);
console.log(JSON.stringify(result));}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});''')
        result=subprocess.run(['node',str(driver),str(_find_mmdc().resolve()),str(tmp_path/'probe.js')],text=True,capture_output=True,timeout=25)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)=={'result':42,'cleaned':3}
