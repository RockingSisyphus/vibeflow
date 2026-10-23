"""Native coroutine execution uses the public Runtime and declared SDK Nodes."""
import asyncio
from dataclasses import replace
from threading import Event

import pytest

from tests.fixtures.support.declarations import native_registry
from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.sdk import node
from vibeflow.targets.python.sdk.resources import definition


def runtime(tmp_path, worker, *, execution='plan', mode='async', plugins=None, **options):
    @node(id='native.terminal',node_type='vibeflow.node',flow_kind='terminal',contract={},rulesets=[])
    class Terminal:
        def run_pure(self,inputs,params):return {}
    registry=native_registry()
    for cls in (Terminal,worker):registry.register(definition(cls).descriptor,cls)
    graph=parse_graph_config_data({'pipeline':{'entry_mode':mode,'nodes':[
        {'id':key,'definition_id':identity,'display_name':key,'description':key}
        for key,identity in [('start','native.terminal'),('work',definition(worker).descriptor.id),('end','native.terminal')]],
        'edges':[['start','work'],['work','end']]}})
    return PipelineRuntime(graph,registry=registry,plugin_registry=plugins,run_dir=tmp_path,runtime_options={'execution':execution}, **options)


@pytest.mark.parametrize('execution',['plan','block','compiled'])
def test_native_coroutine_and_sync_nodes_finish_in_all_profiles(tmp_path,execution):
    observed=[]
    @node(id='native.work',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        async def run_pure(self,inputs,params,context):
            before=context.workflow.self()['id']
            await asyncio.sleep(.001)
            observed.append((before,context.workflow.self()['id']))
            return {}
    instance=runtime(tmp_path,Work,execution=execution)
    asyncio.run(instance.run_async())
    assert len(observed)==1 and observed[0][0]==observed[0][1]
    assert instance.trace.node_runs['work']==1
    with pytest.raises(Exception,match='VF_ENTRY_MODE_MISMATCH'):instance.run()


def test_coroutine_cancellation_waits_for_async_finally(tmp_path):
    observed=[]
    entered=asyncio.Event()
    @node(id='native.cancel',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        async def run_pure(self,inputs,params):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(.01)
                observed.append('cleaned')
    instance=runtime(tmp_path,Work)
    async def run():
        task=asyncio.create_task(instance.run_async())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert observed==['cleaned']
    asyncio.run(run())


def test_sync_graph_rejects_declared_coroutine_and_unexpected_awaitable(tmp_path):
    @node(id='native.bad',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        async def run_pure(self,inputs,params):return {}
    with pytest.raises(Exception,match='VF_ENTRY_MODE_SUSPEND_IN_SYNC'):
        runtime(tmp_path,Work,mode='sync').run()
    @node(id='native.lie',node_type='vibeflow.node',contract={},rulesets=[])
    class Liar:
        def run_pure(self,inputs,params):
            async def pending():return {}
            return pending()
    with pytest.raises(Exception,match='VF_COMPLETION_MISMATCH'):
        runtime(tmp_path,Liar,mode='sync').run()


def test_coroutine_source_and_relocated_aot_use_the_same_entry(tmp_path):
    import json
    import shutil
    from tests.targets.python.test_code_plugins import EXECUTABLE, executable_project
    from vibeflow.tooling.application.python.async_workspace import run_workspace_checked_async
    from vibeflow.tooling.application.python.build import PythonBuildRequest,build_python_aot
    from vibeflow.tooling.application.python.bundle import load_bundle
    source=EXECUTABLE.replace('from vibeflow.core.rules import RuleResult','import asyncio\nfrom vibeflow.core.rules import RuleResult')
    source=source.replace('class Demo:\n    def run_pure(self,inputs,params):','class Demo:\n    async def run_pure(self,inputs,params):\n        await asyncio.sleep(0)')
    workspace,config=executable_project(tmp_path/'source',source)
    data=json.loads(config.read_text());data['pipeline']['entry_mode']='async';config.write_text(json.dumps(data))
    output=asyncio.run(run_workspace_checked_async(config,workspace=workspace,run_root=tmp_path/'source-runs',preview_root=tmp_path/'preview'))
    assert output.public_outputs=={'result':7}
    built=build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(tmp_path/'source')
    shutil.move(str(built.out_dir),str(tmp_path/'relocated'))
    bundle=load_bundle(tmp_path/'relocated')
    result=asyncio.run(bundle.run_async(run_root=tmp_path/'aot-runs'))
    assert result.public_outputs=={'result':7}
    assert bundle.workflow_descriptor['entry_mode']=='async'


def test_async_plugin_hooks_and_dispose_in_source_and_moved_bundle(tmp_path):
    import json
    import shutil
    from tests.targets.python.test_code_plugins import EXECUTABLE, PLUGIN_SOURCE, executable_project
    from vibeflow.tooling.application.python.async_workspace import run_workspace_checked_async
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.bundle import load_bundle
    plugin=PLUGIN_SOURCE.replace('plugin=Plugin(', '''import asyncio
from vibeflow.targets.python.sdk import lifecycle
@lifecycle(id="demo.native",type="runtime",completion="suspend",rulesets=[])
def create(context):
    class Hooks:
        async def before_run(self, inputs):
            self.loop=asyncio.get_running_loop()
            self.ran=False
            await asyncio.sleep(0)
        async def after_run(self, outputs, trace):
            assert asyncio.get_running_loop() is self.loop
            await asyncio.sleep(0)
            self.ran=True
        async def dispose(self):
            await asyncio.sleep(0)
            assert self.ran
    return Hooks()
plugin=Plugin(''').replace('resources=[shell,check,rules]', 'resources=[shell,check,rules,create]')
    workspace,config=executable_project(tmp_path/'source',EXECUTABLE,plugin_source=plugin)
    data=json.loads(config.read_text());data['pipeline']['entry_mode']='async';config.write_text(json.dumps(data))
    result=asyncio.run(run_workspace_checked_async(config,workspace=workspace,run_root=tmp_path/'runs',preview_root=tmp_path/'preview'))
    assert result.public_outputs=={'result':7}
    built=build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(tmp_path/'source')
    assert asyncio.run(load_bundle(built.out_dir).run_async(run_root=tmp_path/'aot-runs')).public_outputs=={'result':7}


def test_cancellation_during_disposal_waits_then_propagates():
    from vibeflow.targets.python.project.plugins import dispose_instances_async, create_plugins_async
    started=asyncio.Event()
    cleaned=[]
    class Resource:
        async def dispose(self):
            started.set()
            await asyncio.sleep(.01)
            cleaned.append('disposed')
    async def run():
        task=asyncio.create_task(dispose_instances_async([Resource()]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert cleaned==['disposed']
        failure=ValueError('second factory failed')
        def create(owned):
            owned.append(Resource())
            raise failure
        with pytest.raises(ValueError) as caught:await create_plugins_async(create)
        assert caught.value is failure and cleaned==['disposed','disposed']
    asyncio.run(run())


def test_thread_local_cleanup_keeps_event_loop_responsive(tmp_path):
    from threading import local
    storage=local()
    entered,release,finished=Event(),Event(),Event()
    timeouts=[]
    class Cleanup:
        def __del__(self):
            entered.set()
            if not release.wait(2):timeouts.append('loop blocked')
            finished.set()
    @node(id='native.thread-exit',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        def run_pure(self,inputs,params):
            storage.resource=Cleanup()
            return {}
    instance=runtime(tmp_path,Work)
    async def run():
        task=asyncio.create_task(instance.run_async())
        while not entered.is_set():await asyncio.sleep(.001)
        assert not task.done() and not finished.is_set()
        release.set()
        await task
        assert finished.is_set() and not timeouts
    try:asyncio.run(run())
    finally:release.set()


def test_async_cancellation_callback_is_started_and_owned(tmp_path):
    entered=asyncio.Event()
    released=asyncio.Event()
    cleaned=[]
    @node(id='native.async-cleanup',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        async def run_pure(self,inputs,params,context):
            async def cleanup(reason):
                released.set()
                await asyncio.sleep(.005)
                cleaned.append('callback')
            context.signal.subscribe(cleanup)
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                await released.wait()
                cleaned.append('finally')
    instance=runtime(tmp_path,Work)
    async def run():
        task=asyncio.create_task(instance.run_async())
        await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert sorted(cleaned)==['callback','finally']
    asyncio.run(run())


def test_sync_entry_in_an_existing_loop_rejects_async_cleanup_without_starting_it(tmp_path):
    started=[]
    @node(id='native.sync-cleanup',node_type='vibeflow.node',contract={},rulesets=[])
    class Work:
        def run_pure(self,inputs,params,context):
            async def cleanup(reason):started.append('unexpected')
            context.signal.subscribe(cleanup)
            return {}
    instance=runtime(tmp_path,Work,mode='sync')
    async def run():
        with pytest.raises(BaseExceptionGroup,match='cleanup failed'):instance.run()
        await asyncio.sleep(0)
        assert started==[]
    asyncio.run(run())
