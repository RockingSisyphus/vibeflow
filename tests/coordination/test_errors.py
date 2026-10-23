"""Execution, transport and cleanup retain the same portable error information."""
import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess

import pytest

from tests.coordination.async_cases import async_case
from tests.coordination.test_in_process import descriptor
from vibeflow.coordination import Coordinator
from vibeflow.coordination.client import WorkflowClient
from vibeflow.coordination.host import run_host
from vibeflow.coordination.server import WorkflowServer


def failure():
    cause = ValueError('original cause'); cause.code = 'VF_CAUSE'
    disposed = RuntimeError('dispose failed'); disposed.code = 'VF_DISPOSE'
    original = RuntimeError('business failed'); original.code = 'VF_BUSINESS'
    original.__cause__ = cause
    original.cleanup_errors = [ExceptionGroup('cleanup failed', [disposed])]
    return original


def assert_details(record):
    assert record['code'] == 'VF_BUSINESS'
    assert record['cause']['code'] == 'VF_CAUSE'
    assert record['cleanup_errors'][0]['errors'][0]['code'] == 'VF_DISPOSE'


async def observe_failure(language, transport, server, *, delivery=False, cyclic=False):
    if language == 'python':
        original = failure()
        if cyclic:
            original.__cause__ = original
        if transport == 'in_process':
            scope = Coordinator()
            target = descriptor('worker', 'async')
            async def execute(inputs, options):
                raise original
            scope.bind(target, execute)
            ended = await scope.run(target['workflow'])
            await scope.aclose()
            assert ended['state'] == 'failed'
            return ended['error']
        def execute(client):
            if delivery:
                client.send('missing', 'default', 1)
            raise original
        with pytest.raises(RuntimeError) as caught:
            await run_host(execute, url=server.url, workflow={'root':'test','path':'worker'})
        assert caught.value is original
        ended = server.dispatch('instances', {})[0]
        assert ended['state'] == 'failed'
        return ended['error']
    resources = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources/coordination'
    script = '''
import {Coordinator} from COORDINATOR;
import {runConnected} from HOST;
const original=Object.assign(new Error('business failed'),{code:'VF_BUSINESS'});
original.cause=Object.assign(new Error('original cause'),{code:'VF_CAUSE'});
original.cleanupErrors=[new AggregateError([Object.assign(new Error('dispose failed'),{code:'VF_DISPOSE'})],'cleanup failed')];
if(CYCLIC)original.cause=original;
let report;
if(TRANSPORT==='in_process'){
  const scope=new Coordinator(),ref={root:'test',path:'worker'};
  scope.bind({workflow:ref,entry_mode:'async',entries:{},calls:[]},async()=>{throw original;});
  const ended=await scope.run(ref);
  if(ended.state!=='failed')throw Error('missing terminal failure');
  report=ended.error;await scope.close();
}else{
  try{
    await runConnected(async(inputs,options)=>{
      if(DELIVERY)options.capabilities['vibeflow.workflow'].send({id:'missing',payload:1});
      throw original;
    },{url:URL,workflow:{root:'test',path:'worker'}});
    throw Error('failure was swallowed');
  }catch(error){if(error!==original)throw error;}
}
console.log(JSON.stringify(report??{}));
'''
    values = {'COORDINATOR':(resources/'coordinator.mjs').as_uri(),
              'HOST':(resources/'workflow_host.mjs').as_uri(),
              'TRANSPORT':transport,'URL':server.url if server else None,
              'DELIVERY':delivery,'CYCLIC':cyclic}
    for name, value in values.items():
        script = script.replace(name, json.dumps(value))
    result = await asyncio.to_thread(subprocess.run, ['node','--input-type=module','-e',script],
                                     capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    if transport == 'http':
        ended = server.dispatch('instances', {})[0]
        assert ended['state'] == 'failed'
        return ended['error']
    return json.loads(result.stdout)


@pytest.mark.parametrize('language', ['python','javascript'])
@pytest.mark.parametrize('transport', ['in_process','http'])
@async_case
async def test_primary_cause_and_cleanup_group_survive_hosts(language, transport):
    with (WorkflowServer() if transport == 'http' else nullcontext(None)) as server:
        assert_details(await observe_failure(language, transport, server))


@pytest.mark.parametrize('language', ['python','javascript'])
@async_case
async def test_recursive_causes_still_produce_a_terminal_result(language):
    record = await observe_failure(language, 'in_process', None, cyclic=True)
    assert record['code'] == 'VF_BUSINESS'
    assert record['cause']['code'] == 'VF_BUSINESS' and record['cause']['recursive']


@pytest.mark.parametrize('language', ['python','javascript'])
@async_case
async def test_send_failure_keeps_the_original_run_error(language):
    with WorkflowServer() as server:
        record = await observe_failure(language, 'http', server, delivery=True)
        assert_details(record)
        assert record['cleanup_errors'][1]['code'] == 'VF_INSTANCE_UNKNOWN'


@pytest.mark.parametrize('mode', ['sync','async'])
@pytest.mark.parametrize('execution', ['plan','block','compiled'])
@async_case
async def test_nested_runtime_failure_keeps_original_cause_and_cleanup(tmp_path, mode, execution):
    from tests.fixtures.support.declarations import native_registry
    from vibeflow.core.flow import GraphConfig, NodeCallSpec, EdgeSpec, NodesetTypeSpec
    from vibeflow.core.workflows.coordination import workflow_descriptor
    from vibeflow.targets.python.runtime import PipelineRuntime
    from vibeflow.targets.python.runtime.workflow_host import bind_workflow
    from vibeflow.targets.python.sdk import node
    from vibeflow.targets.python.sdk.resources import definition
    @node(id='failure.terminal',node_type='vibeflow.node',flow_kind='terminal',contract={},rulesets=[])
    class Terminal:
        def run_pure(self, inputs, params):return {}
    @node(id='failure.work',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        def run_pure(self, inputs, params, context):
            def cleanup(reason):
                error = RuntimeError('dispose failed'); error.code = 'VF_DISPOSE'
                raise error
            context.signal.subscribe(cleanup)
            cause = ValueError('original cause'); cause.code = 'VF_CAUSE'
            error = RuntimeError('business failed'); error.code = 'VF_BUSINESS'
            raise error from cause
    registry = native_registry()
    for cls in (Terminal, Work):registry.register(definition(cls).descriptor, cls)
    body = GraphConfig(nodes=(NodeCallSpec('start','failure.terminal'),NodeCallSpec('bad','failure.work'),NodeCallSpec('end','failure.terminal')),
                       edges=(EdgeSpec('start','bad'),EdgeSpec('bad','end')))
    graph = GraphConfig(entry_mode=mode,nodes=(NodeCallSpec('start','failure.terminal'),NodeCallSpec('child','failure.child'),NodeCallSpec('end','failure.terminal')),
                        edges=(EdgeSpec('start','child'),EdgeSpec('child','end')),
                        nodeset_types={'failure.child':NodesetTypeSpec('failure.child','Child','Child',(),(),body)})
    def factory(**options):
        return PipelineRuntime(graph, registry=registry, run_dir=tmp_path,
                               runtime_options={'execution':execution}, **options)
    reference = {'root':'test','path':'worker'}
    described = workflow_descriptor(factory()._plan.workflow_plan, reference)
    scope = Coordinator(); bind_workflow(scope, described, factory)
    ended = await scope.run(reference)
    assert ended['state'] == 'failed'
    assert_details(ended['error'])
    await scope.aclose()


@async_case
async def test_cleanup_failure_retains_the_first_cancellation():
    from vibeflow.coordination.async_support import finish_cleanup
    started, release = asyncio.Event(), asyncio.Event()
    original = RuntimeError('cleanup failed')
    async def cleanup():
        started.set(); await release.wait(); raise original
    waiting = asyncio.create_task(finish_cleanup(cleanup()))
    await started.wait()
    waiting.cancel('original cancellation'); await asyncio.sleep(0)
    waiting.cancel('again'); await asyncio.sleep(0)
    assert not waiting.done()
    release.set()
    with pytest.raises(asyncio.CancelledError) as caught:
        await waiting
    assert str(caught.value) == 'original cancellation'
    assert caught.value.cleanup_errors == [original]


@async_case
async def test_cancelled_finish_waits_for_completion_and_control_listener():
    started, release, control_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    client = WorkflowClient('unused'); client.id = 'worker'
    async def request(operation, value):
        assert operation == 'complete'
        started.set(); await release.wait()
    async def control():
        await control_release.wait()
    client.request = request
    client._watcher = asyncio.create_task(control())
    finishing = asyncio.create_task(client.finish())
    await started.wait(); finishing.cancel()
    await asyncio.sleep(.005)
    assert not finishing.done()
    release.set(); await asyncio.sleep(.005)
    assert not finishing.done()
    control_release.set()
    with pytest.raises(asyncio.CancelledError):await finishing
    assert client.closed and client._finishing.done() and client._watcher.done()


@async_case
async def test_repeated_cancellation_keeps_late_worker_failure(tmp_path):
    from threading import Event
    from tests.targets.python.test_native_async import runtime
    from vibeflow.targets.python.sdk import node
    from vibeflow.coordination.protocol import error_record
    entered, release = Event(), Event()
    original = RuntimeError('late failure'); original.code = 'VF_BUSINESS'
    @node(id='failure.worker',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        def run_pure(self, inputs, params):
            entered.set(); release.wait(); raise original
    instance = runtime(tmp_path, Work)
    running = asyncio.create_task(instance.run_async())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        running.cancel(); await asyncio.sleep(0)
        running.cancel(); await asyncio.sleep(0)
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError) as caught:await running
    assert 'VF_BUSINESS' in json.dumps(error_record(caught.value))
