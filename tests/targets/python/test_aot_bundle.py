"""Source-free deployment and native execution contracts for Python AOT."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.targets.python.test_code_plugins import executable_project, EXECUTABLE
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def build(tmp_path, source=EXECUTABLE):
    project = tmp_path / 'source'
    project.mkdir()
    workspace, config = executable_project(project, source)
    data = json.loads(config.read_text())
    data['pipeline']['nodes'].append({'id':'end','type_used':'demo.start','display_name':'End','description':'Finish'})
    data['pipeline']['edges'].append(['demo','end'])
    config.write_text(json.dumps(data))
    result = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'built'))
    relocated = tmp_path / 'relocated'
    result.out_dir.rename(relocated)
    shutil.rmtree(project)
    return relocated


@pytest.mark.parametrize('execution', ('plan','block','compiled'))
@pytest.mark.parametrize('trace', ('full','boundary','off'))
def test_moved_bundle_runs_without_source_or_compilers(tmp_path, monkeypatch, execution, trace):
    path = build(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('AOT reentered source compilation')
    from vibeflow.targets.python.project import compiler
    from vibeflow.targets.python.runtime import preparation, block_compiler
    monkeypatch.setattr(compiler.GraphCompiler,'compile_with_findings',forbidden)
    monkeypatch.setattr(compiler.GraphCompiler,'prepare_implementation_facts',forbidden)
    from vibeflow.tooling.application.python import workspace_service
    from vibeflow.tooling.application.python.presentation import prepared
    monkeypatch.setattr(workspace_service,'_prepare_workspace_graph',forbidden)
    monkeypatch.setattr(workspace_service,'_validate_prepared_workspace_graph',forbidden)
    monkeypatch.setattr(prepared,'prepare_python_presentation',forbidden)
    monkeypatch.setattr(preparation,'prepare_python_workflow',forbidden)
    monkeypatch.setattr(block_compiler,'compile_blocks',forbidden)
    bundle = load_bundle(path)
    runtime = bundle.create_runtime(run_dir=tmp_path/'run', runtime_options={'execution':execution,'trace':trace})
    first = runtime.run({})
    second = runtime.run({})
    assert first.get('result')['value'] == second.get('result')['value'] == 7
    assert second.get('runtime.stop_reason') == 'completed'
    assert first is not second


def test_standalone_cli_uses_shipped_framework(tmp_path):
    path = build(tmp_path)
    environment = {key:value for key,value in os.environ.items() if key != 'PYTHONPATH'}
    environment['PYTHONNOUSERSITE'] = '1'
    result = subprocess.run([sys.executable,'-B',str(path/'run.py'),'run','--runtime-profile','train'],
        cwd=tmp_path,env=environment,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['status'] == 'PASS'
    report = json.loads((Path(payload['run_dir']) / 'workflow_execution_report.json').read_text())
    assert report['validation_scope'] == 'vibeflow_workflow_execution'
    assert 'declared_outputs' in {item['id'] for item in report['checked']}
    assert (path/'_framework/vibeflow/block_compiler/model.py').is_file()


def test_snapshot_handles_recursive_graph_definition_tables(tmp_path):
    from vibeflow.core.flow import GraphConfig, NodesetSpec
    from vibeflow.targets.python.runtime.support.snapshot import encode_snapshot, decode_snapshot
    graph = GraphConfig(nodes=())
    definition = NodesetSpec('self','Self','Recursive declaration',(),(),graph)
    graph.nodesets['self'] = definition
    restored = decode_snapshot(json.loads(json.dumps(encode_snapshot(graph))))
    assert restored.nodesets['self'].graph is restored


def test_same_bundle_has_independent_runs_and_preserves_input_objects(tmp_path):
    source = EXECUTABLE.replace('return {"result": 7}', 'return {"result": inputs["payload"]["value"]}')
    project = tmp_path/'source'
    project.mkdir()
    workspace, config = executable_project(project,source)
    data = json.loads(config.read_text())
    data['pipeline']['inputs'] = [{'key':'payload','type':'payload','required':True,'display_name':'Payload'}]
    # The SDK declaration is authoritative, including the new input contract.
    code = (project/'plugin.py').read_text().replace('contract={"provides":',
        'contract={"requires":[{"type":"payload","display_name":"Payload","cardinality":"exactly_one"}],"input_semantics":{"payload":["Input object"]},"provides":')
    (project/'plugin.py').write_text(code)
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    bundle = load_bundle(tmp_path/'bundle')
    value = object()
    first = bundle.run({'payload':value},run_root=tmp_path/'runs')
    second = bundle.run({'payload':value},run_root=tmp_path/'runs')
    assert first.context.get('result')['value'] is value
    assert second.context.get('result')['value'] is value
    assert first.run_dir != second.run_dir


def test_portable_plan_reading_preserves_tasks_and_rejects_old_abi():
    from tests.block_compiler.test_block_compiler import _compile, _linear_graph
    from vibeflow.block_compiler import workflow_plan_from_dict
    plan = _compile(_linear_graph())
    assert workflow_plan_from_dict(plan.to_dict()) == plan
    old = {**plan.to_dict(),'abi_version':'vibeflow.workflow.v6'}
    with pytest.raises(ValueError,match='ABI'):
        workflow_plan_from_dict(old)


@pytest.mark.parametrize('execution', ('plan','block','compiled'))
@pytest.mark.parametrize('configuration', ('tasks','nested','nested_manager','launch_only'))
def test_task_sandbox_runs_from_a_moved_bundle(tmp_path, execution, configuration):
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    repository = Path(__file__).resolve().parents[3]
    source = tmp_path/'source'
    shutil.copytree(repository/'sandbox/python/task_management',source,ignore=shutil.ignore_patterns('__pycache__','runs'))
    workspace = load_workspace_config(source/'vibeflow_config.jsonc')
    config = source/'project/configs'/f'{configuration}.jsonc'
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path/'bundle')
    result = bundle.run({'scenario':'success'},run_root=tmp_path/'runs',
        runtime_options={'execution':execution,'trace':'full'})
    assert result.context.get('runtime.stop_reason') == 'completed'
    trace = (result.run_dir/'runtime_trace.jsonl').read_text()
    assert 'task_started' in trace and 'task_exited' in trace


def test_runtime_plugin_is_created_per_run_and_disposed_after_success(tmp_path):
    marker = tmp_path/'events.txt'
    plugin_code = f'''
class Runtime:
    def before_run(self, inputs):
        with open({str(marker)!r},'a') as stream: stream.write('before\\n')
    def dispose(self):
        with open({str(marker)!r},'a') as stream: stream.write('dispose\\n')
def create(context):
    with open({str(marker)!r},'a') as stream: stream.write('create\\n')
    return Runtime()
'''
    source = EXECUTABLE.replace('plugin=Plugin(',plugin_code+'\nplugin=Plugin(runtime=create,')
    path = build(tmp_path,source)
    assert not marker.exists()
    bundle = load_bundle(path)
    runtime = bundle.create_runtime(run_dir=tmp_path/'run')
    assert not marker.exists()
    runtime.run({})
    runtime.run({})
    assert marker.read_text().splitlines() == ['create','before','dispose'] * 2


def test_bundle_failure_keeps_managed_tasks_until_they_exit(tmp_path):
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    repository = Path(__file__).resolve().parents[3]
    source = tmp_path/'source'
    shutil.copytree(repository/'sandbox/python/task_management',source,ignore=shutil.ignore_patterns('__pycache__','runs'))
    config = source/'project/configs/tasks.jsonc'
    build_python_aot(PythonBuildRequest(load_workspace_config(source/'vibeflow_config.jsonc'),config,tmp_path/'bundle'))
    shutil.rmtree(source)
    with pytest.raises(Exception,match='parent failed'):
        load_bundle(tmp_path/'bundle').run({'scenario':'root_failure'},run_root=tmp_path/'runs')
    trace = next((tmp_path/'runs').glob('*/runtime_trace.jsonl')).read_text()
    assert 'task_exited' in trace


def test_plugin_disposal_preserves_primary_failure_and_releases_all_instances(tmp_path):
    from vibeflow.targets.python.project.plugins import PluginRegistry, release_runtime_plugins
    events = []
    class Resource:
        def __init__(self, name, fail): self.name,self.fail = name,fail
        def dispose(self):
            events.append(self.name)
            if self.fail: raise ValueError(self.name)
    registry = PluginRegistry()
    registry.register(Resource('first',False))
    registry.register(Resource('second',True))
    primary = RuntimeError('business failure')
    release_runtime_plugins(registry, primary=primary)
    assert events == ['second','first']
    assert str(primary) == 'business failure'
    assert len(primary.cleanup_errors) == 1


@pytest.mark.parametrize('execution', ('plan','block','compiled'))
def test_bundle_cancellation_waits_for_real_cleanup_and_releases_lock(tmp_path, execution):
    from concurrent.futures import ThreadPoolExecutor
    import time
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    source = tmp_path/'source'
    shutil.copytree(Path(__file__).resolve().parents[3]/'sandbox/python/task_management',source,
        ignore=shutil.ignore_patterns('__pycache__','runs'))
    config = source/'project/configs/tasks.jsonc'
    data = load_raw_config_document(config).data
    data['pipeline']['execution_lock'] = {'key':'aot.cancellation'}
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(source/'vibeflow_config.jsonc',config,tmp_path/'bundle'))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path/'bundle')
    directory = tmp_path/'run'
    runtime = bundle.create_runtime(run_dir=directory,runtime_options={'execution':execution,'trace':'full'})
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runtime.run,{'scenario':'external_cancel'})
        deadline = time.monotonic() + 10
        trace = directory/'runtime_trace.jsonl'
        try:
            while not trace.exists() or 'worker_started' not in trace.read_text():
                if future.done(): future.result()
                assert time.monotonic() < deadline, 'worker did not start'
                time.sleep(.01)
        finally:
            runtime.request_stop('external test cancellation')
        with pytest.raises(Exception, match='VF_ABORTED'):
            future.result(timeout=10)
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    kinds = [item['kind'] for item in events]
    assert 'cleanup_finished' in kinds
    assert 'task_exited' in kinds
    assert kinds.index('cleanup_finished') < kinds.index('lock_released')
    assert bundle.create_runtime(run_dir=tmp_path/'next').run({'scenario':'success'}).get('runtime.stop_reason') == 'completed'
