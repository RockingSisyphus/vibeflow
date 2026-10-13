"""Both Target renderers retain manager identity and complete Chinese labels."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from tests.tooling.test_presentation_cascade import Empty
from vibeflow.core.descriptors import DescriptorCatalogs, NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.tooling.application.javascript.audit import _javascript_graph_document
from vibeflow.tooling.application.javascript.review import render_mermaid
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.presentation.mermaid import render_mermaid_svg
from vibeflow.tooling.project.graph_config import parse_graph_config


@pytest.mark.parametrize('severity', ['', 'warning', 'error'])
def test_manager_visual_identity_and_long_label_in_real_browser(tmp_path, severity):
    renderer=os.environ.get('VIBEFLOW_MERMAID_RENDERER_ROOT')
    if not renderer:pytest.skip('real Mermaid renderer is not configured')
    label='父调用者启动和停止多个并发任务并等待所有实际执行及异步清理完成的任务管理节点'
    descriptor=NodeDescriptor('fixture.manager','Manager','Task control','1','task_manager',
                              rulesets=(),contract=NodeContractDescriptor())
    registry=NodeRegistry();registry.register(descriptor,Empty)
    catalogs=DescriptorCatalogs.empty();catalogs.nodes.register(descriptor)
    graph=parse_graph_config({'pipeline':{'entry_mode':'async','nodes':[
        {'id':'manage','type_used':'fixture.manager','display_name':label,
         'description':'完整的中文名称和执行语义必须保留，状态颜色不会改变管理权限。'}], 'edges':[]}})
    compiled=GraphCompiler().compile(graph,registry=registry)
    health={'errors':[],'warnings':[]}
    if severity:health['errors' if severity=='error' else 'warnings']=[
        {'severity':severity,'rule_id':'fixture.visual','object_type':'node','object_id':'manage','message':'状态颜色探针'}]
    status='healthError' if severity=='error' else 'healthWarning' if severity else ''
    architecture={'workflow':_javascript_graph_document(graph,compiled,source={},graph_lock_scope='graph',
        catalogs=catalogs,health_classes={(id(graph),'manage'):status})}
    texts={'python':export_mermaid(graph,compiled=compiled,registry=registry,health_report=health),
        'javascript':render_mermaid(SimpleNamespace(graph=graph,compiled=compiled,catalogs=catalogs,architecture=architecture))}
    paths=[]
    for target,text in texts.items():
        assert 'shape: dbl-circ' in text and '任务管理' in text and label in text,text
        if not severity:assert '#FCE7F3' in text and '#BE185D' in text and '#831843' in text
        else:assert status in text
        path=tmp_path/(target+'.svg');render_mermaid_svg(text,path);paths.append(str(path))
    script=tmp_path/'inspect.mjs'
    script.write_text('''
import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const require=createRequire(RENDERER);const {default:puppeteer}=await import(pathToFileURL(require.resolve('puppeteer')).href);
const browser=await puppeteer.launch({headless:true,args:['--no-sandbox','--disable-setuid-sandbox']});
try {const page=await browser.newPage();const proof=[];
 for(const path of PATHS){await page.goto(pathToFileURL(path).href);
  proof.push(await page.evaluate(()=>{
   const node=[...document.querySelectorAll('g.node')].find(node=>node.textContent.includes('任务管理'));
   if(!node)throw new Error('manager label lost');
   const circles=[...node.querySelectorAll('circle')];if(circles.length!==2)throw new Error('double circle lost');
   const box=node.querySelector('.label').getBoundingClientRect();
   const inner=circles.map(circle=>circle.getBoundingClientRect()).sort((a,b)=>a.width-b.width)[0];
   const radius=inner.width/2,cx=inner.x+radius,cy=inner.y+inner.height/2;
   for(const x of [box.left,box.right])for(const y of [box.top,box.bottom])
    if(Math.hypot(x-cx,y-cy)>radius+1)throw new Error('full label exceeds inner circle');
   return {text:node.textContent,circles:circles.length,label:{width:box.width,height:box.height},radius};
  }));
 }
 console.log(JSON.stringify({browser:await browser.version(),proof}));
} finally {await browser.close();}
'''.replace('RENDERER',json.dumps(str(Path(renderer)/'package.json'))).replace('PATHS',json.dumps(paths)))
    result=subprocess.run(['node',str(script)],capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr
    proof=json.loads(result.stdout);assert len(proof['proof'])==2
    (tmp_path/'layout-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
