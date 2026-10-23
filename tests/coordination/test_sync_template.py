"""Official InvokeSync declarations survive source removal and produce relations."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('language',['python','javascript'])
def test_official_sync_template_build_bind_execute_and_link(tmp_path,language,capsys):
    from distribution.build import _copy_coordination_templates
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.cli import main
    from vibeflow.tooling.project.config_loader import strip_jsonc_comments
    _copy_coordination_templates(tmp_path/'templates')
    template=tmp_path/'templates/kernel/templates/workflow_nodes'
    source=tmp_path/'project'
    if language=='python':
        from tests.targets.python.test_code_plugins import project
        code=(template/'nodes.py').read_text()+'''
@node(id="fixture.boundary",node_type="vibeflow.node",flow_kind="terminal",contract={},rulesets=[])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(id="fixture.calc",node_type="vibeflow.node",contract={"provides":[{"key":"value","type":"example.result","display_name":"Result"}],"output_semantics":{"value":["Computed result"]}},rulesets=[])
class Calc:
    def run_pure(self,inputs,params):return {"value":42}
'''
        _,config=project(source,code,plugin_source=(template/'protocol.py').read_text())
    else:
        from tests.targets.javascript.test_code_plugins import project
        _,config=project(source,'',plugin_source='')
        (source/'nodes/steps.ts').unlink()
        (source/'nodes/nodes.mjs').write_text((template/'nodes.mjs').read_text()+'''
export const boundary=defineNode({id:"fixture.boundary",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[],run(){return {};}});
export const calc=defineNode({id:"fixture.calc",node_type:"vibeflow.node",contract:{provides:[{key:"value",type:"example.result",display_name:"Result"}],output_semantics:{value:["Computed result"]}},rulesets:[],run(){return {value:42};}});
''')
        for name in ('protocol.mjs','interfaces.mjs'):shutil.copy2(template/name,source/'plugins/demo'/name)
    workspace_path=tmp_path/'vibeflow_config.jsonc'
    workspace_path.write_text(json.dumps({'roots':[{'id':'project','path':'project'}]}))
    workspace=load_workspace_config(workspace_path)
    def call(name,definition,**extra):
        return dict(id=name,definition_id=definition,display_name=name,description=name,**extra)
    child={'plugins':[{'source':{'kind':'file','ref':'plugins/demo/'+('plugin.py' if language=='python' else 'protocol.mjs')}}],
           'rulesets':[], 'pipeline':{'nodes':[call('start','fixture.boundary'),call('calc','fixture.calc'),call('end','fixture.boundary')],
           'edges':[['start','calc'],['calc','end']], 'entries':{'evaluate':{'start':'start'}},
           'outputs':[{'type':'example.result','as':'computed','display_name':'Result','cardinality':'exactly_one'}]}}
    child_config=source/'child.jsonc';child_config.write_text(json.dumps(child))
    parent=json.loads(json.dumps(child));parent['pipeline'].pop('entries')
    reference={'root':'project','path':'child.jsonc','entry':'evaluate'}
    parent['pipeline']['nodes'][1]=call('calc','example.invokesync',config={'workflow':reference})
    parent['pipeline']['outputs'][0]['as']='result';config.write_text(json.dumps(parent))
    capsys.readouterr()
    assert main(['export-architecture','--workspace',str(workspace.path),'--config',str(config)])==0
    architecture=json.loads(strip_jsonc_comments(capsys.readouterr().out))
    action=architecture['call_policies']['["calc"]']['actions'][0]
    assert action['operation']=='invoke_sync' and action['workflow']==reference
    from vibeflow.tooling.architecture.relations import workflow_relations
    relations=workflow_relations(architecture,{'root_id':'project','path':'workflow.jsonc'})
    assert relations[0]['kind']=='invoke_sync' and relations[0]['entry']=='evaluate'
    if language=='python':
        from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
        if is_mermaid_svg_renderer_available():
            from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
            from vibeflow.tooling.application.python.presentation.preview import python_preview
            exported=load_workspace_graph_for_export(config,workspace=workspace,validate_health=True,_include_presentation=True)
            preview=python_preview(exported[6],config=config,workspace=workspace,preview_root=tmp_path/'preview')
            browser=Path(__file__).resolve().parents[1]/'fixtures/preview/invoke-sync.cjs'
            navigated=subprocess.run(['node',str(browser),str(_find_mmdc().resolve()),str(tmp_path/'preview/vibeflow-preview.html'),preview.metadata['id']],text=True,capture_output=True,timeout=30)
            assert navigated.returncode==0,navigated.stdout+navigated.stderr
        from vibeflow.tooling.application.python import PythonBuildRequest,build_python_aot,load_bundle
        from vibeflow.coordination import Coordinator
        from vibeflow.targets.python.runtime.workflow_host import bind_workflow
        child_build=build_python_aot(PythonBuildRequest(workspace,child_config,tmp_path/'child'))
        parent_build=build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'parent'))
        shutil.rmtree(source)
        scope=Coordinator()
        for path in (child_build.out_dir,parent_build.out_dir):
            bundle=load_bundle(path)
            def factory(bundle=bundle,**options):
                return bundle.create_runtime(run_dir=tmp_path/'runs'/options['workflow_instance_id'],**options)
            bind_workflow(scope,bundle.workflow_descriptor,factory)
        assert scope.invoke_sync({'workflow':bundle.workflow_descriptor['workflow']})=={'result':{'computed':42}}
        assert not scope.instances
    else:
        from vibeflow.tooling.application.javascript.build import ProjectBuildRequest,build_project_aot
        child_build=build_project_aot(ProjectBuildRequest(workspace.path,child_config,tmp_path/'child','node','esm-module'))
        parent_build=build_project_aot(ProjectBuildRequest(workspace.path,config,tmp_path/'parent','node','esm-module'))
        shutil.rmtree(source)
        resource=Path(__file__).resolve().parents[2]/'src/vibeflow/targets/javascript/resources/coordination/coordinator.mjs'
        code=f'''import {{Coordinator}} from {json.dumps(resource.as_uri())};
import * as child from {json.dumps(child_build.entry.as_uri())};
import * as parent from {json.dumps(parent_build.entry.as_uri())};
const scope=new Coordinator();scope.bind(child.workflowDescriptor,child.runWorkflow);scope.bind(parent.workflowDescriptor,parent.runWorkflow);
const result=scope.invoke_sync({{workflow:parent.workflowDescriptor.workflow}});
if(result.then||scope.instances.size)throw Error('sync contract violated');console.log(JSON.stringify(result));'''
        result=subprocess.run(['node','--input-type=module','-e',code],text=True,capture_output=True,timeout=15)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)=={'result':{'computed':42}}
