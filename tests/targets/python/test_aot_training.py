"""CPU integration: AOT preserves native model/Tensor identities and updates."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from vibeflow.tooling.application.python import PythonBuildRequest,build_python_aot,load_bundle


TRAINING = '''from vibeflow.targets.python.sdk import Plugin,node
@node(type_key="cpu.terminal",flow_kind="terminal",contract={},rulesets=[])
class Terminal:
    def run_pure(self,inputs,params):
        return {}
@node(type_key="cpu.train",flow_kind="global_state",rulesets=["vibeflow.global_state"],contract={"requires":[{"type":"batch","display_name":"Batch","cardinality":"exactly_one"}],"provides":[{"key":"loss","type":"number","display_name":"Loss"},{"key":"model","type":"model","display_name":"Model"},{"key":"batch","type":"batch.seen","display_name":"Seen batch"}],"input_semantics":{"batch":["CPU training Tensor"]},"output_semantics":{"loss":["Training loss"],"model":["Same model"],"batch":["Same Tensor"]}})
class Train:
    def run_pure(self,inputs,params):
        model=params["_global"]["model"]
        optimizer=params["_global"]["optimizer"]
        batch=inputs["batch"]["value"]
        optimizer.zero_grad()
        loss=model(batch).square().mean()
        loss.backward()
        optimizer.step()
        return {"loss":loss.item(),"model":model,"batch":batch}
plugin=Plugin(id="cpu",resources=[Terminal,Train])
'''


def test_cpu_training_matches_source_after_project_removal(tmp_path):
    torch = pytest.importorskip('torch')
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.workspace_service import _environment_or_report,_prepare_workspace_graph
    from vibeflow.targets.python.runtime import PipelineRuntime
    source = tmp_path/'source'
    source.mkdir()
    (source/'vibeflow_config.jsonc').write_text('{"roots":[{"id":"cpu","path":"."}]}')
    (source/'vibeflow_project.jsonc').write_text('{"project_target":"python"}')
    (source/'plugin.py').write_text(TRAINING)
    config = source/'workflow.jsonc'
    config.write_text(json.dumps({'plugins':[{'source':{'kind':'file','ref':'plugin.py'}}],'rulesets':[],
        'pipeline':{'inputs':[{'key':'input','type':'batch','display_name':'Batch','required':True}],
            'nodes':[{'id':name,'type_used':kind,'display_name':name,'description':name}
                for name,kind in [('start','cpu.terminal'),('train','cpu.train'),('end','cpu.terminal')]],
            'edges':[['start','train'],['train','end']],
            'outputs':[{'type':kind,'as':name,'display_name':name,'cardinality':'exactly_one'}
                for kind,name in [('number','loss'),('model','model'),('batch.seen','batch')]]}}))
    workspace = load_workspace_config(source/'vibeflow_config.jsonc')
    torch.manual_seed(41)
    initial = torch.nn.Linear(2,1)
    models = [copy.deepcopy(initial),copy.deepcopy(initial)]
    batch = torch.tensor([[1.,2.],[2.,1.]])
    environment = _environment_or_report(workspace,config)
    prepared = _prepare_workspace_graph(config,workspace=workspace,env=environment)
    options = {'execution':'compiled','trace':'off'}
    native = PipelineRuntime(prepared.graph,registry=environment.registry,run_dir=tmp_path/'native',runtime_options=options,
        global_config={'model':models[0],'optimizer':torch.optim.SGD(models[0].parameters(),lr=.1)})
    expected = [native.run({'input':batch}).get('loss')['value'] for _ in range(3)]
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    runtime = load_bundle(tmp_path/'bundle').create_runtime(run_dir=tmp_path/'aot',runtime_options=options,
        global_config={'model':models[1],'optimizer':torch.optim.SGD(models[1].parameters(),lr=.1)})
    observed = []
    for _ in range(3):
        result = runtime.run({'input':batch})
        observed.append(result.get('loss')['value'])
        assert result.get('model')['value'] is models[1]
        assert result.get('batch')['value'] is batch
    assert expected == observed
    for left,right in zip(models[0].parameters(),models[1].parameters()):
        assert torch.equal(left,right)
