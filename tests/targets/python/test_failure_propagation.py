"""Public execution preserves the initiating failure through nested cleanup."""
import asyncio
from dataclasses import replace

import pytest

from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.core.flow import EdgeSpec
from vibeflow.coordination.protocol import error_record
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.runtime.trace import RuntimeTraceSink
from vibeflow.targets.python.sdk import node
from vibeflow.targets.python.sdk.resources import definition
from vibeflow.tooling.application.python.project.declarations import default_python_registry


@node(id='failure.terminal', node_type='vibeflow.node', flow_kind='terminal', contract={}, rulesets=[])
class Terminal:
    def run_pure(self, inputs, params):
        return {}


def call(name, identity, **extra):
    return dict(id=name, definition_id=identity, display_name=name, description=name, **extra)


def pipeline(identity, mode):
    return dict(entry_mode=mode, nodes=[call('start', 'failure.terminal'), call('work', identity),
                                      call('end', 'failure.terminal')],
                edges=[['start', 'work'], ['work', 'end']])


def runtime(tmp_path, worker, *, mode='async', execution='plan', shape='plain', plugins=None):
    registry = default_python_registry()
    for cls in (Terminal, worker):
        registry.register(definition(cls).descriptor, cls)
    body = pipeline(definition(worker).descriptor.id, mode)
    types = []
    if shape != 'plain':
        for identity in ('failure.inner', 'failure.outer'):
            types.append(dict(type_key=identity, display_name=identity, description=identity,
                              requires=[], provides=[], pipeline=body))
            body = pipeline(identity, mode)
        if shape == 'loop':
            body['nodes'][1] = call('work', 'vibeflow.loop.while', requires=[], provides=[],
                loop=dict(body='failure.outer', max_iterations=1, stop_after=1, carry=[], outputs=[]))
    graph = parse_graph_config_data(dict(pipeline=body, nodeset_types=types))
    return PipelineRuntime(graph, registry=registry, plugin_registry=plugins, run_dir=tmp_path,
                           runtime_options={'execution': execution, 'trace': 'off'})


@pytest.mark.parametrize('execution', ['plan', 'block', 'compiled'])
@pytest.mark.parametrize('shape', ['nodeset', 'loop'])
@pytest.mark.parametrize('coroutine', [False, True])
def test_nested_business_error_remains_primary(tmp_path, execution, shape, coroutine):
    original = ValueError('caller.binding needs conversation')
    if coroutine:
        @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
        class Worker:
            async def run_pure(self, inputs, params):
                await asyncio.sleep(0)
                raise original
    else:
        @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
        class Worker:
            def run_pure(self, inputs, params):
                raise original
    instance = runtime(tmp_path, Worker, execution=execution, shape=shape)
    with pytest.raises(ValueError) as caught:
        asyncio.run(instance.run_async())
    assert caught.value is original
    assert error_record(caught.value)['code'] == 'ValueError'


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_failed_hooks_do_not_replace_business_failure_and_all_are_run(tmp_path, mode):
    original = ValueError('invalid input')
    observed = []
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        def run_pure(self, inputs, params):
            raise original
    class Hooks:
        def node_failed(self, *args):
            observed.append(self.name)
            raise RuntimeError(self.name)
    plugins = PluginRegistry()
    for name in ('first observer failed', 'second observer failed'):
        hook = Hooks(); hook.name = name
        plugins.register(hook)
    instance = runtime(tmp_path, Worker, mode=mode, plugins=plugins)
    with pytest.raises(ValueError) as caught:
        instance.run() if mode == 'sync' else asyncio.run(instance.run_async())
    assert caught.value is original
    assert observed == ['first observer failed', 'second observer failed']
    assert len(error_record(original)['cleanup_errors']) == 2


@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('business_fails', [False, True])
def test_summary_io_failure_is_secondary_only_when_execution_already_failed(tmp_path, monkeypatch, mode, business_fails):
    original = ValueError('invalid input')
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        def run_pure(self, inputs, params):
            if business_fails:
                raise original
            return {}
    def unavailable(*args):
        raise OSError('summary storage unavailable')
    monkeypatch.setattr(RuntimeTraceSink, 'write_summary', unavailable)
    instance = runtime(tmp_path, Worker, mode=mode)
    with pytest.raises(ValueError if business_fails else OSError) as caught:
        instance.run() if mode == 'sync' else asyncio.run(instance.run_async())
    if business_fails:
        assert caught.value is original
        assert error_record(original)['cleanup_errors'][0]['code'] == 'OSError'


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_observation_close_failure_does_not_mask_business_error(tmp_path, monkeypatch, mode):
    from vibeflow.targets.python.runtime.observation import RunObservation
    original = ValueError('invalid input')
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        def run_pure(self, inputs, params):
            raise original
    close = RunObservation.close
    def unavailable(observer):
        close(observer)
        raise OSError('observation close failed')
    monkeypatch.setattr(RunObservation, 'close', unavailable)
    instance = runtime(tmp_path, Worker, mode=mode)
    with pytest.raises(ValueError) as caught:
        instance.run() if mode == 'sync' else asyncio.run(instance.run_async())
    assert caught.value is original
    assert error_record(original)['cleanup_errors'][0]['message'] == 'observation close failed'


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_stop_observer_error_is_retained_without_masking_business_failure(tmp_path, monkeypatch, mode):
    from vibeflow.targets.python.runtime.observation import RunObservation
    original = ValueError('invalid input')
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        def run_pure(self, inputs, params):
            raise original
    transition = RunObservation.transition
    def unavailable(observer, state, error=None):
        if state == 'stopping':
            raise OSError('stop observer failed')
        return transition(observer, state, error)
    monkeypatch.setattr(RunObservation, 'transition', unavailable)
    instance = runtime(tmp_path, Worker, mode=mode)
    with pytest.raises(ValueError) as caught:
        instance.run() if mode == 'sync' else asyncio.run(instance.run_async())
    assert caught.value is original
    assert error_record(original)['cleanup_errors'][0]['errors'][0]['message'] == 'stop observer failed'


def test_external_cancellation_remains_primary_when_finally_fails(tmp_path):
    entered = asyncio.Event()
    cleaned = []
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        async def run_pure(self, inputs, params):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.append(True)
                raise ValueError('cleanup failed')
    async def run():
        task = asyncio.create_task(runtime(tmp_path, Worker).run_async())
        await entered.wait()
        task.cancel('external stop')
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert cleaned == [True]
        assert error_record(caught.value)['cleanup_errors'][0]['message'] == 'cleanup failed'
    asyncio.run(run())


def test_later_external_cancellation_does_not_replace_observed_business_failure(tmp_path):
    observed = asyncio.Event()
    release = asyncio.Event()
    original = ValueError('business failed before stop')
    attempts = []
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        def run_pure(self, inputs, params):
            attempts.append(True)
            if len(attempts) == 1:
                raise original
            return {}
    class Hooks:
        async def node_failed(self, *args):
            observed.set()
            await release.wait()
    plugins = PluginRegistry(); plugins.register(Hooks())
    instance = runtime(tmp_path, Worker, plugins=plugins, shape='nodeset')
    async def run():
        task = asyncio.create_task(instance.run_async())
        await observed.wait()
        task.cancel('late stop')
        release.set()
        with pytest.raises(ValueError) as caught:
            await task
        assert caught.value is original
        await instance.run_async()
        assert len(attempts) == 2
    asyncio.run(run())


def test_simultaneous_branch_errors_are_execution_errors_not_cleanup(tmp_path):
    entered = asyncio.Event()
    failures = [ValueError('first business failure'), RuntimeError('second business failure')]
    started = []
    @node(id='failure.worker', node_type='vibeflow.node', contract={}, rulesets=[])
    class Worker:
        async def run_pure(self, inputs, params):
            index = len(started); started.append(index)
            if len(started) == 2:
                entered.set()
            await entered.wait()
            raise failures[index]
    instance = runtime(tmp_path, Worker)
    from dataclasses import replace
    from vibeflow.core.flow import EdgeSpec
    graph = replace(instance.graph, nodes=(*instance.graph.nodes,
                    replace(instance.graph.nodes[1], id='peer')),
                    edges=(*instance.graph.edges, EdgeSpec('start', 'peer'), EdgeSpec('peer', 'end')))
    instance = PipelineRuntime(graph, registry=instance.registry, run_dir=tmp_path / 'parallel')
    with pytest.raises((ValueError, RuntimeError)) as caught:
        asyncio.run(instance.run_async())
    primary = caught.value
    assert any(primary is error for error in failures)
    secondary = next(error for error in failures if error is not primary)
    assert primary.execution_errors == [secondary]
    assert not getattr(primary, 'cleanup_errors', [])
    assert error_record(primary)['errors'][0]['message'] == str(secondary)


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_aot_nested_failure_after_removing_source(tmp_path, mode):
    import json
    import shutil
    from tests.targets.python.test_code_plugins import EXECUTABLE, executable_project
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.bundle import load_bundle
    source = EXECUTABLE.replace('return {"result": 7}',
        'raise ValueError("caller.binding needs conversation")')
    assert source != EXECUTABLE
    workspace, config = executable_project(tmp_path / 'source', source)
    data = json.loads(config.read_text())
    body = {**data['pipeline'], 'entry_mode': mode}
    for index in range(2):
        identity = f'failure.layer{index}'
        nodeset = dict(type_key=identity, display_name=identity, description=identity,
            requires=[], provides=[{'key':'out', 'type':'number', 'display_name':'Out'}], pipeline=body)
        path = config.parent / f'layer{index}.jsonc'
        path.write_text(json.dumps(nodeset))
        data.setdefault('nodeset_imports', []).append({'path': path.name})
        body = {'entry_mode':mode, 'nodes':[call('start','demo.start'), call('work',identity),
                call('end','demo.start')], 'edges':[['start','work'],['work','end']],
                'outputs':[{'type':'number','cardinality':'exactly_one','as':'result','display_name':'Result'}]}
    data['pipeline'] = body
    config.write_text(json.dumps(data))
    built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    shutil.rmtree(tmp_path / 'source')
    bundle = load_bundle(built.out_dir)
    with pytest.raises(ValueError, match='caller.binding needs conversation'):
        bundle.run(run_root=tmp_path / 'runs') if mode == 'sync' else asyncio.run(bundle.run_async(run_root=tmp_path / 'runs'))


def parallel_runtime(instance, directory, execution):
    graph=replace(instance.graph,nodes=(*instance.graph.nodes,replace(instance.graph.nodes[1],id='peer')),
                  edges=(*instance.graph.edges,EdgeSpec('start','peer'),EdgeSpec('peer','end')))
    return PipelineRuntime(graph,registry=instance.registry,run_dir=directory,
                           runtime_options={'execution':execution,'trace':'off'})


@pytest.mark.parametrize('mode',['sync','async'])
@pytest.mark.parametrize('broken',[False,True])
def test_cli_exit_does_not_hide_owned_cleanup_failure(tmp_path, mode, broken):
    cleaned=[]
    @node(id='failure.worker',node_type='vibeflow.node',flow_kind='terminal',contract={},rulesets=[])
    class Worker:
        def run_pure(self,inputs,params,context):
            def cleanup(reason):
                cleaned.append(True)
                if broken:raise RuntimeError('owned cleanup failed')
            context.signal.subscribe(cleanup)
            raise SystemExit(7)
    instance=runtime(tmp_path,Worker,mode=mode);instance.delegate_cli=True
    if broken:
        with pytest.raises(ExceptionGroup) as caught:
            instance.run() if mode=='sync' else asyncio.run(instance.run_async())
        record=error_record(caught.value)
        assert record['business_exit']=={'exit_code':7,'source':'work'}
        assert record['errors'][0]['message']=='owned cleanup failed'
    else:
        result=instance.run() if mode=='sync' else asyncio.run(instance.run_async())
        assert result.get('cli.exit_code')['value']==7
    assert cleaned==[True]


@pytest.mark.parametrize('execution',['plan','block','compiled'])
def test_cancelled_sibling_finally_is_cleanup_not_independent_execution(tmp_path,execution):
    started=[];ready=asyncio.Event()
    @node(id='failure.worker',node_type='vibeflow.node',contract={},rulesets=[])
    class Worker:
        async def run_pure(self,inputs,params):
            index=len(started);started.append(index)
            if len(started)==2:ready.set()
            if index==0:
                await ready.wait()
                raise ValueError('original business failure')
            try:await asyncio.Event().wait()
            finally:raise RuntimeError('sibling cleanup failure')
    instance=parallel_runtime(runtime(tmp_path/'unused',Worker),tmp_path/'run',execution)
    with pytest.raises(ValueError) as caught:asyncio.run(instance.run_async())
    record=error_record(caught.value)
    assert [error['message'] for error in record['cleanup_errors']]==['sibling cleanup failure']
    assert 'errors' not in record


def test_failure_stops_sibling_before_waiting_for_own_cleanup(tmp_path):
    started=[];peer_entered=asyncio.Event();peer_stopped=asyncio.Event();cleaned=[]
    @node(id='failure.worker',node_type='vibeflow.node',contract={},rulesets=[])
    class Worker:
        async def run_pure(self,inputs,params,context):
            index=len(started);started.append(index)
            if index==0:
                async def cleanup(reason):
                    await peer_stopped.wait()
                    cleaned.append(True)
                context.signal.subscribe(cleanup)
                await peer_entered.wait()
                raise ValueError('failure initiates stop')
            try:
                peer_entered.set()
                await asyncio.Event().wait()
            finally:peer_stopped.set()
    async def run():
        instance=parallel_runtime(runtime(tmp_path/'unused',Worker),tmp_path/'run','plan')
        task=asyncio.create_task(instance.run_async())
        try:
            await asyncio.wait_for(peer_stopped.wait(),2)
            with pytest.raises(ValueError,match='failure initiates stop'):await task
            assert cleaned==[True]
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
    asyncio.run(run())
