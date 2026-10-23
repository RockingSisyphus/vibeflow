"""Explicit bindings use native Runtime roots, with one coordinator state owner."""
import asyncio
from concurrent.futures import Future

import pytest

from tests.coordination.async_cases import async_case
from tests.targets.python.test_native_async import runtime
from vibeflow.coordination import Coordinator, CoordinationError
from vibeflow.core.workflows.coordination import workflow_descriptor
from vibeflow.targets.python.runtime.workflow_host import bind_workflow
from vibeflow.targets.python.sdk import node


def descriptor(name, mode='sync', calls=()):
    return {'workflow':{'root':'test','path':name},'entry_mode':mode,'entries':{},'default_entry':'',
            'inputs':[],'outputs':[],'calls':list(calls)}


def test_sync_calls_copy_values_remove_records_and_preserve_error():
    coordinator = Coordinator()
    seen = []
    def worker(inputs, options):
        seen.append(options['workflow_instance_id'])
        inputs['items'].append(9)
        return inputs
    target = descriptor('worker')
    coordinator.bind(target,worker)
    inputs = {'items':[1]}
    for _ in range(100):
        assert coordinator.invoke_sync({'workflow':target['workflow'],'inputs':inputs}) == {'items':[1,9]}
    assert inputs == {'items':[1]} and not coordinator.instances and len(set(seen)) == 100
    original = ValueError('expression failed')
    coordinator.bind(descriptor('broken'),lambda i,o:(_ for _ in ()).throw(original))
    with pytest.raises(ValueError) as caught:
        coordinator.invoke_sync({'workflow':descriptor('broken')['workflow']})
    assert caught.value is original and not coordinator.instances
    assert caught.value.workflow_calls[0]["workflow"]["path"] == "broken"
    coordinator.bind(descriptor('pending'),lambda i,o:Future())
    with pytest.raises(CoordinationError,match='pending work'):
        coordinator.invoke_sync({'workflow':descriptor('pending')['workflow']})
    assert not coordinator.instances


@async_case
async def test_sync_nested_calls_execute_on_the_calling_worker():
    from threading import get_ident
    coordinator = Coordinator()
    leaf = descriptor('leaf')
    child = descriptor('child', calls=[{'operation':'invoke_sync','workflow':leaf['workflow']}])
    identities = []
    def calculate(inputs, options):
        identities.append(options['workflow_instance_id'])
        return {'caller':inputs['caller'],'executed':get_ident()}
    def nested(inputs, options):
        identities.append(options['workflow_instance_id'])
        return options['capabilities']['vibeflow.workflow']['invoke_sync'](
            {'workflow':leaf['workflow'],'inputs':inputs})
    coordinator.bind(leaf, calculate).bind(child, nested)
    owner = coordinator.register({'workflow':{'root':'test','path':'application'}})['id']
    operations = coordinator.operations(owner)
    result = await asyncio.to_thread(lambda:operations['invoke_sync'](
        {'workflow':child['workflow'],'inputs':{'caller':get_ident()}}))
    assert result['caller'] == result['executed'] != get_ident()
    assert len({owner,*identities}) == 3 and list(coordinator.instances) == [owner]
    await coordinator.aclose()


@async_case
async def test_owned_async_instances_wait_cancel_kill_release_and_close():
    coordinator = Coordinator()
    peer = descriptor('peer','async')
    caller = descriptor('caller','async',[{'operation':'call','workflow':peer['workflow'],'launch':{'kind':'in_process'}}])
    cleaned = []
    async def worker(inputs, options):
        try:
            api = options['capabilities']['vibeflow.workflow']
            message = await api['receive']({'port':'request'})
            api['send']({'id':message['sender'],'payload':message['payload']})
            return {'value':message['payload']}
        finally:
            await asyncio.sleep(.005)
            cleaned.append(options['workflow_instance_id'])
    coordinator.bind(peer,worker).bind(caller,lambda i,o:None)
    owner = coordinator.register({'workflow':caller['workflow']})['id']
    operations = coordinator.operations(owner)
    with pytest.raises(CoordinationError):
        coordinator.invoke_sync({'workflow':peer['workflow']})
    identities = [(await operations['call']({'workflow':peer['workflow'],'launch':{'kind':'in_process'}}))['id'] for _ in range(2)]
    with pytest.raises(CoordinationError) as timeout:
        await operations['wait']({'id':identities[0],'timeout':.001})
    assert timeout.value.code == 'VF_WAIT_TIMEOUT'
    waiting = asyncio.create_task(operations['wait']({'id':identities[0]}))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):await waiting
    assert coordinator.instances[identities[0]]['state'] == 'running'
    operations['send']({'id':identities[0],'port':'request','payload':42})
    assert (await operations['receive']({}))['payload'] == 42
    first = await operations['wait']({'id':identities[0]})
    assert first == await operations['wait']({'id':identities[0]})
    assert first['outputs'] == {'value':42} and identities[0] in cleaned
    with pytest.raises(CoordinationError):
        await operations['kill']({'id':identities[1],'workflow':caller['workflow']})
    ended = await operations['kill']({'id':identities[1],'workflow':peer['workflow']})
    assert ended['state'] == 'cancelled' and identities[1] in cleaned
    coordinator.release(identities[0])
    assert identities[0] not in coordinator.instances
    third = await operations['call']({'workflow':peer['workflow'],'launch':{'kind':'in_process'}})
    await asyncio.sleep(0)
    await coordinator.aclose()
    assert third['id'] in cleaned and not coordinator.instances


@pytest.mark.parametrize('execution',['plan','block','compiled'])
@async_case
async def test_real_runtime_bindings_have_independent_identity_and_observation(tmp_path,execution):
    from vibeflow.targets.python.runtime.observation import current_observation
    seen = []
    coordinator = Coordinator()
    child_ref = {'root':'test','path':'child'}
    @node(id='native.child',node_type='vibeflow.node',contract={},rulesets=[])
    class Child:
        def run_pure(self,inputs,params,context):
            seen.append((context.workflow.self()['id'],current_observation()))
            return {}
    def child(**options):
        return runtime(tmp_path/'child',Child,mode='sync',execution=execution,**options)
    child_descriptor = workflow_descriptor(child(workflow_instance_id='description')._plan.workflow_plan,child_ref)
    bind_workflow(coordinator,child_descriptor,child)
    @node(id='native.parent',node_type='vibeflow.node',contract={},rulesets=[],
          capabilities=[{'id':'vibeflow.workflow','operations':['invoke_sync']}])
    class Parent:
        async def run_pure(self,inputs,params,context):
            before = current_observation()
            parent_id = context.workflow.self()['id']
            context.capabilities['vibeflow.workflow']['invoke_sync']({'workflow':child_ref})
            assert current_observation() is before
            assert seen[-1][0] != parent_id and seen[-1][1] is not before
            return {}
    parent = runtime(tmp_path/'parent',Parent,execution=execution)
    owner = coordinator.register({'workflow':{'root':'test','path':'unbound-root'}})['id']
    parent._capabilities = {'vibeflow.workflow':coordinator.operations(owner)}
    await parent.run_async()
    assert len(coordinator.instances) == 1
    await coordinator.aclose()


def test_named_sync_entry_and_nested_declared_call_are_immediate():
    coordinator=Coordinator()
    leaf=descriptor('leaf')
    leaf['entries']={'evaluate':{'inputs':[],'outputs':[]}}
    leaf['default_entry']='evaluate'
    def evaluate(inputs,options):
        assert options['entry']=='evaluate'
        return {'value':inputs['n']*2,'id':options['workflow_instance_id']}
    coordinator.bind(leaf,evaluate)
    parent=descriptor('parent',calls=[{'operation':'invoke_sync','workflow':leaf['workflow']}])
    def invoke(inputs,options):
        child=options['capabilities']['vibeflow.workflow']['invoke_sync']({'workflow':leaf['workflow'],'inputs':inputs})
        assert child['id']!=options['workflow_instance_id']
        return {'value':child['value']+1}
    coordinator.bind(parent,invoke)
    assert coordinator.invoke_sync({'workflow':parent['workflow'],'inputs':{'n':4}})=={'value':9}
    assert not coordinator.instances


def test_generated_javascript_contracts_and_launch_migration():
    from vibeflow.targets.javascript.resources import read_text, coordination_contract_source
    from vibeflow.core.workflows.references import launch_configuration
    assert read_text('coordination/contracts.mjs')==coordination_contract_source()
    with pytest.raises(ValueError,match='launch.kind is required'):
        launch_configuration({'command':['browser-aot']})
    with pytest.raises(ValueError,match='allows only kind'):
        launch_configuration({'kind':'in_process','command':['fake']})
    assert launch_configuration({'kind':'in_process'})=={'kind':'in_process'}


@async_case
async def test_aborted_receive_after_handled_cancellation_keeps_queued_message():
    from vibeflow.targets.python.runtime.lifecycle import CancellationSignal
    scope = Coordinator()
    identity = scope.register({'workflow': {'root': 'test', 'path': 'receiver'}})['id']
    api = scope.operations(identity)
    try:
        api['send']({'id': identity, 'payload': 'retained'})
        asyncio.current_task().cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.sleep(0)
        signal = CancellationSignal()
        signal.request_stop('already aborted')
        with pytest.raises(asyncio.CancelledError):
            await api['receive'].with_signal(signal)({'timeout': 0})
        assert (await api['receive']({'timeout': 0}))['payload'] == 'retained'
    finally:
        await scope.aclose()
