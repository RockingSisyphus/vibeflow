"""Actual Python/Node subprocess hosts and cross-target workflow calls."""
import json
from pathlib import Path
import sys
from time import sleep
import pytest
from tests.e2e.async_cases import async_case
from tests.e2e.host_projects import python_project,node_module
from tests.e2e.support import cli
from vibeflow.coordination import WorkflowClient,WorkflowServer

@pytest.fixture(scope="module",autouse=True)
def prepared_javascript_dependencies(toolchain):
    return toolchain


@pytest.mark.parametrize('target', ['python-source', 'python-aot', 'node'])
@async_case
async def test_instances_exchange_messages_and_kill_confirms_actual_workflow_end(tmp_path, target):
    resources = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources'
    if target.startswith('python'):
        workspace, config = python_project(tmp_path)
        command = [sys.executable, '-B', '-m', 'vibeflow.coordination', 'run-python', '--run-root', str(tmp_path / 'runs'), '--preview-root', str(tmp_path / 'preview')]
        if target == 'python-aot':
            
            built = json.loads(cli(tmp_path,"build","--workspace",workspace,"--config",config,"--out-dir",tmp_path / "bundle").stdout)
            command += ['--bundle', str(built['out_dir'])]
        else:
            command += ['--config', str(config), '--workspace', str(workspace)]
    else:
        command = ['node', str(resources / 'coordination' / 'workflow_node.mjs'), str(node_module(tmp_path))]
    reference = {'root': tmp_path.name if target.startswith('python') else 'peer', 'path': 'workflow.jsonc'}
    launch = {'kind': 'process', 'command': command, 'cwd': str(tmp_path)}
    with WorkflowServer(launches=[{'workflow': reference, 'launch': launch}]) as server:
        caller = await WorkflowClient.open(server.url)
        instances = []
        try:
            for value in (7, 11):
                identity = (await caller.call(reference, launch=launch, timeout=15))['id']
                instances.append(identity)
                caller.send(identity, 'request', {'value': value})
            await caller.flush()
            replies = [await caller.receive('reply', timeout=15) for _ in instances]
            assert {reply['payload']['self'] for reply in replies} == set(instances)
            assert sorted((reply['payload']['value'] for reply in replies)) == [21, 33]
            for identity in instances:
                result = await caller.wait(identity, timeout=15)
                assert result['state'] == 'succeeded', result
                assert result['outputs']['result'] in (21, 33)
            waiting = (await caller.call(reference, launch=launch, timeout=15))['id']
            instances.append(waiting)
            stopped = await caller.kill(waiting, workflow=reference, timeout=15)
            assert stopped['state'] == 'cancelled', stopped
        finally:
            for identity in instances:
                if (await caller.request('status', {'id': identity}))['state'] not in {'succeeded', 'failed', 'cancelled'}:
                    await caller.kill(identity, timeout=15)
            await caller.finish()

@pytest.mark.parametrize('caller_target', ['python-source', 'python-aot', 'node'])
@async_case
async def test_ordinary_workflow_node_calls_other_target_sends_receives_and_waits(tmp_path, caller_target):
    """The caller is a real Node implementation, rather than a raw test client."""
    resources = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources'
    caller_root, peer_root = (tmp_path / 'caller', tmp_path / 'peer')
    caller_root.mkdir()
    peer_root.mkdir()

    def python_command(root, *, caller=False, aot=False, peer=None):
        workspace, config = python_project(root)
        if caller:
            plugin = root / 'nodes/steps.py'
            source = plugin.read_text().replace('[{"operation":"send"},{"operation":"receive"}]', '[{"operation":"send"},{"operation":"receive"},{"operation":"call"},{"operation":"wait"}]')
            source = source.replace('        message=await api.receive({"port":"request"})', '        peer=await api.call({"workflow":params["workflow"],"launch":params["launch"]})\n        api.send({"id":peer["id"],"port":"request","payload":{"value":7}})\n        message=await api.receive({"port":"reply"})\n        await api.wait({"id":peer["id"]})')
            source = source.replace('        api.send({"id":message["sender"],"port":"reply","payload":{"value":value,"self":context.workflow.self()["id"]}})\n', '')
            plugin.write_text(source)
            declaration = json.loads(config.read_text())
            declaration['pipeline']['nodes'][1]['config'] = peer
            config.write_text(json.dumps(declaration))
        command = [sys.executable, '-B', '-m', 'vibeflow.coordination', 'run-python', '--run-root', str(root / 'runs'), '--preview-root', str(root / 'preview')]
        if aot:
            
            built = json.loads(cli(root,"build","--workspace",workspace,"--config",config,"--out-dir",root / "bundle").stdout)
            return command + ['--bundle', str(built['out_dir'])]
        return command + ['--workspace', str(workspace), '--config', str(config)]
    if caller_target == 'node':
        peer_command = python_command(peer_root, aot=True)
    else:
        peer_command = ['node', str(resources / 'coordination/workflow_node.mjs'), str(node_module(peer_root))]
    peer = {'workflow': {'root': 'peer', 'path': 'workflow.jsonc'}, 'launch': {'kind': 'process', 'command': peer_command, 'cwd': str(tmp_path)}}
    caller_command = ['node', str(resources / 'coordination/workflow_node.mjs'), str(node_module(caller_root, caller=True, peer=peer))] if caller_target == 'node' else python_command(caller_root, caller=True, aot=caller_target.endswith('aot'), peer=peer)
    reference = {'root': 'caller', 'path': 'workflow.jsonc'}
    launch = {'kind': 'process', 'command': caller_command, 'cwd': str(tmp_path)}
    with WorkflowServer(launches=[peer, {'workflow': reference, 'launch': launch}]) as server:
        client = await WorkflowClient.open(server.url)
        try:
            identity = (await client.call(reference, launch=launch, timeout=20))['id']
            result = await client.wait(identity, timeout=30)
            assert result['state'] == 'succeeded', result
            assert result['outputs'] == {'result': 63}
        finally:
            for instance in await client.request('instances', {}):
                if instance['id'] != client.id and instance['state'] not in {'succeeded', 'failed', 'cancelled'}:
                    await client.kill(instance['id'], timeout=15)
            await client.finish()

@async_case
async def test_launcher_and_caller_exit_do_not_end_the_registered_workflow(tmp_path):
    resources = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources'
    command = ['node', str(resources / 'coordination' / 'workflow_node.mjs'), str(node_module(tmp_path))]
    wrapper = tmp_path / 'launch.py'
    wrapper.write_text('import subprocess\nsubprocess.Popen(' + repr(command) + ')\n')
    reference = {'root': 'peer', 'path': 'workflow.jsonc'}
    launch = {'kind': 'process', 'command': [sys.executable, str(wrapper)], 'cwd': str(tmp_path)}
    with WorkflowServer(launches=[{'workflow': reference, 'launch': launch}]) as server:
        caller = await WorkflowClient.open(server.url)
        observer = await WorkflowClient.open(server.url)
        identity = None
        try:
            identity = (await caller.call(reference, launch=launch, timeout=15))['id']
            await caller.finish()
            sleep(0.1)
            assert (await observer.request('status', {'id': identity}))['state'] == 'running'
            observer.send(identity, 'request', {'value': 9})
            assert (await observer.receive('reply', timeout=10))['payload']['value'] == 27
            assert (await observer.wait(identity, timeout=10))['state'] == 'succeeded'
        finally:
            if identity and (await observer.request('status', {'id': identity}))['state'] not in {'succeeded', 'failed', 'cancelled'}:
                await observer.kill(identity, workflow=reference, timeout=10)
            await observer.finish()
            await caller.finish()

