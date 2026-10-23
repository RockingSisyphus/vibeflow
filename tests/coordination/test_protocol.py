from tests.coordination.async_cases import async_case
import json
from pathlib import Path
import subprocess
from threading import Thread
import pytest
from vibeflow.coordination import CoordinationError, WorkflowClient, WorkflowServer
from vibeflow.targets.python.runtime.lifecycle import CancellationSignal

@async_case
async def test_early_messages_ids_and_repeatable_terminal_results():
    with WorkflowServer() as server:
        a, b = (await WorkflowClient.open(server.url), await WorkflowClient.open(server.url))
        try:
            assert a.id != b.id
            a.send(b.id, 'requests', {'request': 42, 'reply_to': a.id})
            await a.flush()
            message = await b.receive('requests', timeout=2)
            assert message == {'sender': a.id, 'port': 'requests', 'payload': {'request': 42, 'reply_to': a.id}}
            await b.finish(outputs={'answer': 84})
            assert (await a.wait(b.id, timeout=2))['outputs'] == {'answer': 84}
            assert (await a.wait(b.id, timeout=2))['state'] == 'succeeded'
            with pytest.raises(CoordinationError, match=b.id):
                await a.kill(b.id + 'stale', timeout=1)
        finally:
            await a.finish()
            await b.finish()

@async_case
async def test_cancel_receive_does_not_stop_peer_and_kill_confirms_exit():
    with WorkflowServer() as server:
        a = await WorkflowClient.open(server.url)
        b = await WorkflowClient.open(server.url, stop=lambda: b.finish(state='cancelled'))
        try:
            signal = CancellationSignal()
            signal.request_stop('cancel local wait')
            with pytest.raises(Exception, match='VF_ABORTED'):
                await a.operations()['receive'].with_signal(signal)({})
            assert (await a.request('status', {'id': b.id}))['state'] == 'running'
            assert (await a.kill(b.id, timeout=2))['state'] == 'cancelled'
        finally:
            await a.finish()
            await b.finish()

@async_case
async def test_node_and_python_use_the_same_wire_protocol(tmp_path):
    module = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources/coordination/workflow_client.mjs'
    with WorkflowServer() as server:
        a = await WorkflowClient.open(server.url)
        script = f'\nimport {{WorkflowClient}} from {json.dumps(module.as_uri())};\nconst client=await WorkflowClient.open({json.dumps(server.url)});\ntry {{\n  client.send({json.dumps(a.id)},"requests",{{text:"中文",reply_to:client.id}});\n  const reply=await client.receive("reply",{{timeout:3}});\n  if(reply.payload.answer!==42)throw new Error("wrong reply");\n  await client.finish({{outputs:reply.payload}});\n}} finally {{await client.finish();}}\n'
        process = subprocess.Popen(['node', '--input-type=module', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            message = await a.receive('requests', timeout=3)
            assert message['payload']['text'] == '中文'
            a.send(message['sender'], 'reply', {'answer': 42})
            await a.flush()
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, stdout + stderr
            assert (await a.wait(message['sender'], timeout=2))['outputs'] == {'answer': 42}
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            await a.finish()

@async_case
async def test_unsupported_stop_and_cancelled_wait_preserve_peer_identity():
    with WorkflowServer() as server:
        a, b = (await WorkflowClient.open(server.url), await WorkflowClient.open(server.url))
        try:
            with pytest.raises(CoordinationError) as unsupported:
                await a.kill(b.id, timeout=1)
            assert unsupported.value.code == 'VF_STOP_UNSUPPORTED'
            with pytest.raises(CoordinationError) as timeout:
                await a.wait(b.id, timeout=0.02)
            assert timeout.value.code == 'VF_WAIT_TIMEOUT'
            assert (await a.request('status', {'id': b.id}))['state'] == 'running'
            await b.finish(outputs={'value': 7})
            assert (await a.wait(b.id))['outputs'] == {'value': 7}
        finally:
            await a.finish()
            await b.finish()

@pytest.mark.parametrize('host', ['python', 'node'])
@async_case
async def test_invalid_json_outputs_report_failed_instead_of_leaving_a_running_instance(tmp_path, host):
    with WorkflowServer() as server:
        observer = await WorkflowClient.open(server.url)
        try:
            if host == 'python':
                from vibeflow.coordination.host import run_host
                with pytest.raises(TypeError):
                    await run_host(lambda client: object(), workflow='bad-result', url=server.url)
                identity = next((item['id'] for item in await observer.request('instances', {}) if item['workflow'] == 'bad-result'))
            else:
                module = Path(__file__).resolve().parents[2] / 'src/vibeflow/targets/javascript/resources/coordination/workflow_client.mjs'
                result = subprocess.run(['node', '--input-type=module', '-e', f'\nimport {{WorkflowClient}} from {json.dumps(module.as_uri())};\nconst client=await WorkflowClient.open({json.dumps(server.url)});\nlet rejected=false;\ntry {{await client.finish({{outputs:{{bad:NaN}}}});}}catch(error){{rejected=error instanceof TypeError;}}\nif(!rejected)throw new Error("non-JSON result accepted");\nconsole.log(JSON.stringify({{id:client.id}}));\n'], text=True, capture_output=True, timeout=10)
                assert result.returncode == 0, result.stderr
                identity = json.loads(result.stdout)['id']
            status = await observer.wait(identity, timeout=2)
            assert status['state'] == 'failed'
            assert status['error']['code'] == 'VF_RESULT_NOT_JSON'
        finally:
            await observer.finish()
