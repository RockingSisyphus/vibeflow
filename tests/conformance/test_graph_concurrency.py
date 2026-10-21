"""Ordinary graph fanout/join owns execution, results and actual cleanup."""
import json
import subprocess
from threading import Barrier, Event
import time

import pytest

from tests.fixtures.support.declarations import native_registry
from tests.targets.javascript.aot_fixtures import emit_fixture
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.project.graph_config import parse_graph_config


def _call(name, key, **options):
    return dict(id=name, definition_id=key, display_name=name, description=name, **options)


@pytest.mark.parametrize('execution', ['plan', 'block', 'compiled'])
@pytest.mark.parametrize('nested', [False,True])
def test_python_dispatch_limit_can_exceed_default_and_repeats_in_nested_loops(tmp_path, execution, nested):
    count = 12
    barrier = Barrier(count)
    registry = native_registry()

    class Terminal:
        def run_pure(self, inputs, params):
            return {}

    collections=[]
    class Collector:
        def run_pure(self, inputs, params):
            collections.append(1)
            return {'report': [item['value'] for item in inputs['receipt']]}

    registry.register(NodeDescriptor('native.terminal', 'Terminal', 'Boundary', '1', 'terminal',
        contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"), Terminal)
    registry.register(NodeDescriptor('native.collect', 'Collect', 'Collect complete results', '1', 'process',
        contract=NodeContractDescriptor(requires=(DataRequirement('receipt','all',display_name='Receipt'),),
            provides=(DataProvider('report','report',display_name='Report'),), input_semantics={'receipt':('Independent receipt',)}, output_semantics={'report':('Collected values',)}), rulesets=(), node_type="vibeflow.node"), Collector)
    for index in range(count):
        def implementation(value):
            class Worker:
                def run_pure(self, inputs, params):
                    barrier.wait(timeout=5)
                    time.sleep((count-value)*.001)
                    return {f'receipt{value}': value}
            return Worker
        registry.register(NodeDescriptor(f'native.work{index}', 'Work', 'Independent work', '1', 'process',
            contract=NodeContractDescriptor(provides=(DataProvider(f'receipt{index}','receipt',display_name='Receipt'),), output_semantics={f'receipt{index}':('Independent receipt',)}), rulesets=(), node_type="vibeflow.node"), implementation(index))
    nodes = [_call('start','native.terminal',config={'max_concurrency':count}), *[_call(f'w{i}',f'native.work{i}') for i in range(count)],
             _call('collect','native.collect',join_policy='all'), _call('end','native.terminal')]
    graph = parse_graph_config({'pipeline':{'nodes':nodes,
        'edges':[['start',f'w{i}'] for i in range(count)]+[[f'w{i}','collect'] for i in range(count)]+[['collect','end']],
        'outputs':[{'type':'report','cardinality':'exactly_one','as':'report','display_name':'Report'},
                   {'type':'receipt','cardinality':'all','as':'receipts','display_name':'Receipts'}]}})
    if nested:
        from vibeflow.core.flow import GraphConfig,NodeCallSpec,NodesetTypeSpec,LoopSpec,LoopOutputSpec,EdgeSpec
        from vibeflow.core.contracts import PipelineOutputSpec
        definition=NodesetTypeSpec("native.batch","Batch","Ordinary parallel graph",(),(),graph)
        graph=GraphConfig(nodes=(NodeCallSpec("start","native.terminal"),
            NodeCallSpec("batch","vibeflow.loop.while",provides=(DataProvider("report","report",display_name="Report"),),
                loop=LoopSpec(body="native.batch",stop_after=3,outputs=(LoopOutputSpec("report","report"),))),
            NodeCallSpec("end","native.terminal")),edges=(EdgeSpec("start","batch"),EdgeSpec("batch","end")),
            nodeset_types={definition.type_key:definition},outputs=(PipelineOutputSpec("report","exactly_one",display_name="Report"),))
    runtime = PipelineRuntime(graph,registry=registry,run_dir=tmp_path,
                              runtime_options=RuntimeOptions(execution=execution))
    for round in range(3):
        result = runtime.run()
        assert result.get('report')['value'] == list(range(count))
        assert len(collections)==(round+1)*(3 if nested else 1)
        if not nested:
            assert [item['value'] for item in result.get('receipts')] == list(range(count))
            assert runtime.trace.node_runs['collect'] == 1


@pytest.mark.parametrize('execution', ['plan', 'block', 'compiled'])
def test_python_failure_waits_for_sibling_finally(tmp_path, execution):
    started, cleaned = Event(), Event()
    registry = native_registry()

    class Terminal:
        def run_pure(self, inputs, params): return {}

    class Worker:
        def run_pure(self, inputs, params, context):
            started.set()
            try: context.signal.wait()
            finally:
                time.sleep(.02)
                cleaned.set()
            return {}

    class Failure:
        def run_pure(self, inputs, params):
            assert started.wait(2)
            raise ValueError('branch failed')

    for key,kind,implementation in [('terminal','terminal',Terminal),('work','process',Worker),('fail','process',Failure)]:
        registry.register(NodeDescriptor('native.'+key,key,key,'1',kind,
            contract=NodeContractDescriptor(),rulesets=(), node_type="vibeflow.node"),implementation)
    graph = parse_graph_config({'pipeline':{'nodes':[_call('start','native.terminal'),
        _call('work','native.work'),_call('fail','native.fail'),
        _call('collect','native.terminal',join_policy='all')],
        'edges':[['start','work'],['start','fail'],['work','collect'],['fail','collect']]}})
    runtime = PipelineRuntime(graph,registry=registry,run_dir=tmp_path,
                              runtime_options=RuntimeOptions(execution=execution))
    with pytest.raises(Exception,match='branch failed'): runtime.run()
    assert cleaned.is_set()


def test_javascript_all_ready_branches_execute_and_join_once(tmp_path):
    count = 12
    def node(name, export, **extra):
        return {'id':name,'definition_id':'native.'+name,'flow_kind':'process',
                    'implementation':{'kind':'file','ref':'./nodes.mjs','export':export},**extra}
    terminal = lambda name: node(name,'terminal',flow_kind='terminal',is_terminal=True,max_concurrency=count)
    workers = [node(f'w{i}','work',completion='suspend',params={'index':i},
                    provides=[{'key':'receipt','type':'receipt'}]) for i in range(count)]
    plan = {'entry_mode':'async','nodes':[terminal('start'),*workers,
        node('collect','collect',join_policy='all',requires=[{'type':'receipt','cardinality':'all'}],
             provides=[{'key':'report','type':'report'}]),terminal('end')],
        'routes':[{'source':'start','target':f'w{i}'} for i in range(count)]+
                 [{'source':f'w{i}','target':'collect'} for i in range(count)]+[{'source':'collect','target':'end'}],
        'outputs':[{'type':'report','cardinality':'exactly_one','as':'report','display_name':'Report'},
                   {'type':'receipt','cardinality':'all','as':'receipts','display_name':'Receipts'}]}
    emitted = emit_fixture(plan)
    (tmp_path/'workflow.mjs').write_text(emitted.source)
    (tmp_path/'nodes.mjs').write_text('''
let started=0,collects=0,release;
const barrier=new Promise(resolve=>release=resolve);
export function terminal(){return {};}
export async function work(inputs,params){
  if(++started===12)release();
  await barrier;
  await new Promise(resolve=>setTimeout(resolve,12-params.index));
  return {receipt:params.index};
}
export function collect(inputs){
  if(++collects!==1)throw Error('duplicate collection');
  return {report:inputs.receipt.map(item=>item.value)};
}
''')
    (tmp_path/'run.mjs').write_text("import {runWorkflowAsync} from './workflow.mjs';console.log(JSON.stringify(await runWorkflowAsync({},{trace:'off'})));")
    result = subprocess.run(['node',str(tmp_path/'run.mjs')],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['report'] == list(range(count))
    assert json.loads(result.stdout)['receipts'] == list(range(count))
