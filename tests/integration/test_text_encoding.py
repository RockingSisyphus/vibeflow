from tests.coordination.async_cases import async_case
"""UTF-8 artifacts survive source removal and non-UTF-8 host defaults."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from tests.targets.python.test_code_plugins import EXECUTABLE, executable_project
from vibeflow.coordination import WorkflowClient, WorkflowServer
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.project.workflow_launches import write_bundle_launches
MESSAGE = '通知服务：中文输入与输出🙂'

@pytest.fixture
def text_bundle(tmp_path):
    source = EXECUTABLE.replace('"type":"number"', '"type":"message"')
    source = source.replace('contract={"provides":', f'contract={{"requires":[{{"type":"message","display_name":"Message","cardinality":"exactly_one"}}],"input_semantics":{{"message":["Input text"]}},"params_schema":{{"text":{{"type":"string"}}}},"params_defaults":{{"text":{MESSAGE!r}}},"provides":')
    source = source.replace('return {"result": 7}', f'assert inputs["message"]["value"] == params["text"] == {MESSAGE!r}\n        return {{"result": inputs["message"]["value"]}}')
    project = tmp_path / 'source'
    workspace, config = executable_project(project, source)
    data = json.loads(config.read_text(encoding='utf-8'))
    data['pipeline']['inputs'] = [{'key': 'message', 'type': 'message', 'required': True, 'display_name': '输入'}]
    data['pipeline']['outputs'][0]['type'] = 'message'
    data['pipeline']['nodes'][1]['description'] = MESSAGE
    data['pipeline']['nodes'].append({'id': 'end', 'definition_id': 'demo.start', 'display_name': '结束', 'description': '完成'})
    data['pipeline']['edges'].append(['demo', 'end'])
    config.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    bundle = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle')).out_dir
    reference = json.loads((bundle / 'python-workflow.json').read_text(encoding='utf-8'))['workflow_reference']
    write_bundle_launches(bundle, [{'workflow': reference, 'launch': {'kind': 'process', 'command': [sys.executable, '中文.py'], 'env': {'MESSAGE': MESSAGE}}}])
    shutil.rmtree(project)
    initial = tmp_path / 'input.json'
    initial.write_text(json.dumps({'message': MESSAGE}, ensure_ascii=False), encoding='utf-8')
    return (bundle, initial)

def environment(mode):
    values = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
    values.update(LC_ALL='C', PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', PYTHONIOENCODING='utf-8', PYTHONWARNDEFAULTENCODING='1', PYTHONWARNINGS='error::EncodingWarning')
    values['VF_TEST_DEFAULT_ENCODING'] = mode
    return values

def probe(tmp_path, bundle, initial, entry):
    script = tmp_path / 'probe.py'
    script.write_text(f"""\nimport io, json, locale, os, runpy, sys\nfrom pathlib import Path\nif os.environ["VF_TEST_DEFAULT_ENCODING"] == "gbk":\n    original = io.text_encoding\n    def text_encoding(encoding, stacklevel=2):\n        return "gbk" if encoding is None else original(encoding, stacklevel)\n    io.text_encoding = text_encoding\nelse:\n    assert sys.flags.utf8_mode == 0\n    assert locale.getencoding().lower().replace("-", "") != "utf8"\nbundle = Path({str(bundle)!r})\nsys.path.insert(0, str(bundle / "_framework"))\ninitial = Path({str(initial)!r})\nif {entry!r} == "api":\n    from vibeflow.tooling.application.python import load_bundle\n    from vibeflow.tooling.project.workflow_launches import bundle_launches\n    assert bundle_launches(bundle)[0]["launch"]["env"]["MESSAGE"] == {MESSAGE!r}\n    value = load_bundle(bundle).run(json.loads(initial.read_text(encoding="utf-8")), run_root={str(tmp_path / 'api-runs')!r})\n    assert value.public_outputs == {{"result":{MESSAGE!r}}}\nelif {entry!r} == "cli":\n    sys.argv = [str(bundle / "run.py"), "run", "--input", str(initial), "--run-root", {str(tmp_path / 'cli-runs')!r}]\n    runpy.run_path(str(bundle / "run.py"), run_name="__main__")\nelse:\n    from vibeflow.tooling.application.coordination import main\n    raise SystemExit(main(["run-python", "--bundle", str(bundle), "--input", str(initial),\n        "--run-root", {str(tmp_path / 'host-runs')!r}]))\n""", encoding='utf-8')
    return [sys.executable, '-B', str(script)]

@pytest.mark.parametrize('mode', ['locale', 'gbk'])
@pytest.mark.parametrize('entry', ['api', 'cli', 'coordination'])
@async_case
async def test_source_free_bundle_preserves_utf8_under_non_utf8_defaults(tmp_path, text_bundle, mode, entry):
    bundle, initial = text_bundle
    command = probe(tmp_path, bundle, initial, entry)
    if entry != 'coordination':
        completed = subprocess.run(command, cwd=tmp_path, env=environment(mode), capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        if entry == 'cli':
            assert json.loads(completed.stdout)['status'] == 'PASS'
        return
    reference = json.loads((bundle / 'python-workflow.json').read_text(encoding='utf-8'))['workflow_reference']
    launch = {'kind': 'process', 'command': command, 'cwd': str(tmp_path), 'env': environment(mode)}
    with WorkflowServer(launches=[{'workflow': reference, 'launch': launch}]) as server:
        client = await WorkflowClient.open(server.url)
        try:
            instance = await client.call(reference, launch=launch, timeout=10)
            result = await client.wait(instance['id'], timeout=10)
            assert result['state'] == 'succeeded', result
            assert result['outputs'] == {'result': MESSAGE}
        finally:
            await client.finish()
