import asyncio

from functools import partial

def _run_async(runtime,*args,**kwargs):
    return asyncio.run(runtime.run_async(*args,**kwargs))

"""Package resources, scopes and process-boundary deployment of Python AOT."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.targets.python.test_code_plugins import EXECUTABLE, PLUGIN_SOURCE, executable_project
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle
from vibeflow.tooling.project.workspace_loader import load_workspace_config

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('execution', ('plan','block','compiled'))
@pytest.mark.parametrize('configuration', ('retry','wrapped_retry','outer_fixed','outer_condition','nested'))
def test_moved_math_bundle_covers_loop_and_nodeset_scopes(tmp_path, execution, configuration):
    source = tmp_path/'source'
    shutil.copytree(ROOT/'sandbox/python/workflow_math',source,ignore=shutil.ignore_patterns('__pycache__','runs'))
    rows = json.loads((source/'expectations.json').read_text())
    expected = next(row for row in rows if row['config'] == configuration)
    workspace = load_workspace_config(source/'vibeflow_config.jsonc')
    build_python_aot(PythonBuildRequest(workspace,source/'project/configs'/f'{configuration}.jsonc',tmp_path/'bundle'))
    shutil.rmtree(source)
    result = load_bundle(tmp_path/'bundle').run(expected['initial'],run_root=tmp_path/'runs',
        runtime_options={'execution':execution,'trace':'full'})
    for key,value in expected['expected_outputs'].items():
        assert result.context.get(key)['value'] == value
    assert result.context.get('runtime.stop_reason') == 'completed'


def test_moved_multifile_implementations_and_runtime_plugin(tmp_path):
    source = tmp_path/'source'
    shutil.copytree(ROOT/'sandbox/python/multifile_resources',source,ignore=shutil.ignore_patterns('__pycache__','runs'))
    build_python_aot(PythonBuildRequest(source/'vibeflow_config.jsonc',source/'project/configs/workflow.jsonc',tmp_path/'bundle'))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path/'bundle')
    first,second = bundle.create_runtime(run_dir=tmp_path/'first'),bundle.create_runtime(run_dir=tmp_path/'second')
    assert first.run({}).get('number')['value'] == second.run({}).get('number')['value']
    assert first._frames['model'].node is not second._frames['model'].node


@pytest.mark.parametrize('reader', ('path', 'package'))
def test_package_data_and_explicit_include_are_relocatable(tmp_path, reader):
    source = tmp_path/'source'
    source.mkdir()
    workspace, config = executable_project(source)
    package = source/'nodes/implementation'
    package.mkdir()
    (package/'__init__.py').write_text('')
    code = EXECUTABLE.replace('["vibeflow.process","demo.rules"]', '["vibeflow.document","demo.rules"]').replace('return {"result": 7}', 'return {"result": int(__import__("pathlib").Path(__file__).with_name("value.txt").read_text())}')
    if reader == 'package':
        code = 'from importlib.resources import files\n' + code.replace(
            '__import__("pathlib").Path(__file__).with_name("value.txt")',
            'files(__package__).joinpath("value.txt")')
    (package/'plugin.py').write_text(code)
    (package/'value.txt').write_text('23')
    (source/'extras').mkdir()
    (source/'extras/selected.txt').write_text('included')
    (source/'nodes/steps.py').unlink()
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle',include=('extras',)))
    shutil.rmtree(source)
    result = load_bundle(tmp_path/'bundle').run(run_root=tmp_path/'runs')
    assert result.context.get('result')['value'] == 23
    assert next((tmp_path/'bundle').rglob('extras/selected.txt')).read_text() == 'included'


def test_global_object_and_config_override_bind_at_runtime(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    code = EXECUTABLE.replace('contract={"provides":', 'contract={"params_schema":{"delta":{"type":"number"}},"params_defaults":{"delta":1},"provides":')
    code = code.replace('return {"result": 7}', 'return {"result": params["_global"]["model"] if params["delta"] == 8 else None}')
    workspace,config = executable_project(source,code)
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    bundle = load_bundle(tmp_path/'bundle')
    model = object()
    first = bundle.create_runtime(global_config={'model':model},node_config_overrides={'demo':{'delta':8}},run_dir=tmp_path/'run')
    assert first.run({}).get('result')['value'] is model


def test_delegated_cli_has_business_streams_and_exit_code_after_move(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    code = EXECUTABLE.replace('return {"result": 7}', 'print("business:" + " ".join(inputs["cli.argv"]["value"]))\n        return {"cli.exit_code": 7}')
    code = code.replace('contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Computed value"]}}',
        'contract={"requires":[{"type":"cli.argv","display_name":"Arguments","cardinality":"exactly_one"}],"provides":[{"key":"cli.exit_code","type":"cli.exit_code","display_name":"Exit"}],"input_semantics":{"cli.argv":["Business argv"]},"output_semantics":{"cli.exit_code":["Exit status"]}}')
    code = code.replace('rulesets=["vibeflow.process","demo.rules"]','rulesets=["vibeflow.io","demo.rules"]')
    workspace,config = executable_project(source,code)
    data = json.loads(config.read_text())
    data['pipeline']['inputs'] = [{'key':'cli.argv','type':'cli.argv','display_name':'Arguments','required':True}]
    data['pipeline']['outputs'] = [{'type':'cli.exit_code','as':'cli.exit_code','display_name':'Exit','cardinality':'exactly_one'}]
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    env = {key:value for key,value in os.environ.items() if key != 'PYTHONPATH'}
    result = subprocess.run([sys.executable,'-B',str(tmp_path/'bundle/run.py'),'delegate-cli',
        '--run-root',str(tmp_path/'runs'),'--run-id','cli','--','--flag','hello world'],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode == 7, result.stderr
    assert result.stdout == 'business:--flag hello world\n'
    assert result.stderr == ''
    assert 'CLI.DELEGATE.END' in (tmp_path/'runs/cli/vibeflow.log').read_text()
    assert 'business:--flag' in (tmp_path/'runs/cli/business.log').read_text()


def test_bundle_planned_stub_retains_concerns_and_live_global_object(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    workspace,config = executable_project(source)
    (source/'stubs').mkdir()
    (source/'stubs/stub.py').write_text('def run_stub(inputs,params):\n    return {"result":params["model"]}\n')
    data = json.loads(config.read_text())
    data['rulesets'] = ['vibeflow.workflow']
    data['pipeline']['nodes'].append({'id':'end','definition_id':'demo.start','display_name':'End','description':'Finish'})
    data['pipeline']['edges'].append(['demo','end'])
    data['pipeline']['nodes'][1].update(definition_id='future',status='planned',flow_kind='process',
        requires=[],provides=[{'key':'result','type':'number','display_name':'Result'}],
        planned_behavior={'kind':'python_stub','stub_module':'stubs/stub.py'})
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle',runtime_options={'allow_planned_stub':True}))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path/'bundle')
    model = object()
    result = bundle.run(global_config={'model':model},run_root=tmp_path/'runs')
    assert result.context.get('result')['value'] is model
    assert result.health.status == 'CONCERNS'
    assert result.health.info['production_ready'] is False


def test_overlapping_import_scopes_keep_lazy_modules_available(tmp_path):
    from contextlib import ExitStack
    import importlib
    from vibeflow.targets.python.sdk.loading import source_paths
    (tmp_path/'aot_lazy_support.py').write_text('value=42\n')
    before = list(sys.path)
    with ExitStack() as first, ExitStack() as second:
        first.enter_context(source_paths((tmp_path,)))
        second.enter_context(source_paths((tmp_path,)))
        first.close()
        assert importlib.import_module('aot_lazy_support').value == 42
    assert sys.path == before
    sys.modules.pop('aot_lazy_support',None)


def test_native_subplan_projection_and_node_order_roundtrip():
    from tests.block_compiler.strict_portable_plan import _loop_graph, _registry
    from tests.block_compiler.test_block_compiler import _compile_global
    from vibeflow.targets.python.project.compiler import GraphCompiler
    from vibeflow.targets.python.runtime.planning import build_execution_plan
    from vibeflow.block_compiler import workflow_plan_from_json
    from vibeflow.core.flow import GraphConfig, NodeCallSpec
    from vibeflow.core.models import ImplementationFact,ImplementationFacts
    graph,registry = _loop_graph(),_registry()
    compiled = GraphCompiler().compile_with_findings(graph,registry=registry)
    native = build_execution_plan(compiled.workflow.graph,compiled.compiled_graph,registry=registry,_contracts_resolved=True)
    child = native.frames['repeat'].subplan.to_workflow_plan()
    assert child.block(child.entry_block).path == ()
    assert child.blocks[0].order == native.frames['repeat'].subplan.order
    graph = GraphConfig(nodes=(NodeCallSpec('z','worker'),NodeCallSpec('a','worker')))
    plan = _compile_global(graph,ImplementationFacts((ImplementationFact('worker',flow_kind='process'),)))
    restored = workflow_plan_from_json(plan.to_json())
    assert restored == plan
    assert list(restored.blocks[0].order) == ['z','a']


def test_installed_plugin_package_is_collected_without_its_environment(tmp_path, monkeypatch):
    source, environment = tmp_path/'source',tmp_path.parent/(tmp_path.name+'-site')
    source.mkdir()
    package = environment/'selected_training_plugin'
    package.mkdir(parents=True)
    (package/'__init__.py').write_text(PLUGIN_SOURCE)
    (package/'asset.txt').write_text('package data')
    monkeypatch.syspath_prepend(str(environment))
    workspace,config = executable_project(source)
    data = json.loads(config.read_text())
    data['plugins'] = [{'source':{'kind':'package','ref':'selected_training_plugin'}}]
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    shutil.rmtree(environment)
    sys.modules.pop('selected_training_plugin',None)
    bundle = load_bundle(tmp_path/'bundle')
    assert bundle.run(run_root=tmp_path/'runs').context.get('result')['value'] == 7
    assert next((tmp_path/'bundle/_dependencies').rglob('asset.txt')).read_text() == 'package data'


def test_zip_installed_framework_can_build_a_standalone_bundle(tmp_path):
    import zipfile
    source = tmp_path/'source'
    source.mkdir()
    workspace,config = executable_project(source)
    archive = tmp_path/'kernel.zip'
    package = ROOT/'src/vibeflow'
    with zipfile.ZipFile(archive,'w') as output:
        for file in package.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                output.write(file,Path('vibeflow')/file.relative_to(package))
    env = dict(os.environ,PYTHONPATH=str(archive),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    command = 'from vibeflow.tooling.application.python import build_python_aot,PythonBuildRequest;import sys;build_python_aot(PythonBuildRequest(*sys.argv[1:]))'
    built = subprocess.run([sys.executable,'-B','-c',command,str(workspace.path),str(config),str(tmp_path/'bundle')],
        cwd=tmp_path,env=env,capture_output=True,text=True)
    assert built.returncode == 0,built.stderr
    shutil.rmtree(source)
    archive.unlink()
    env.pop('PYTHONPATH')
    result = subprocess.run([sys.executable,'-B',str(tmp_path/'bundle/run.py'),'run'],
        cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode == 0,result.stdout+result.stderr


@pytest.mark.parametrize('execution', ('plan','block','compiled'))
def test_ordinary_ports_keep_host_objects_and_target_execution_metadata(tmp_path, execution):
    source = tmp_path/'source'
    source.mkdir()
    from tests.fixtures.support.projects import register_root
    register_root(source)
    workspace = source.parent / 'vibeflow_config.jsonc'
    config = source/'workflow.jsonc'
    from vibeflow.core.workflows.interfaces import PORT_SCHEMA_TYPES, port_capability_descriptor
    ports = (ROOT / "tests/fixtures/support/port_nodes.py").read_text()
    (source / "nodes").mkdir()
    (source / "nodes/ports.py").write_text(ports.replace('"number"', '"value"').replace('"answer"', '"value"'))
    descriptor = port_capability_descriptor({"receive", "send"}).to_dict()
    descriptor.pop("kind")
    plugin = "from vibeflow.targets.python.sdk import Plugin, capability, data_schema\n"
    plugin += "interface=capability(**" + repr(descriptor) + ")\n"
    plugin += "schemas=[data_schema(type_key=k,schema=v) for k,v in " + repr(PORT_SCHEMA_TYPES) + ".items()]\n"
    plugin += "plugin=Plugin(id='ports',resources=[interface,*schemas,data_schema(type_key='value',schema={})])\n"
    (source / "plugins/ports").mkdir(parents=True)
    (source / "plugins/ports/plugin.py").write_text(plugin)
    config.write_text(json.dumps({'rulesets':[], 'plugins':[{'source':{'kind':'file','ref':'plugins/ports/plugin.py'}}],
        'pipeline':{'entry_mode': 'async', 'nodes':[{'id':name,'definition_id':key,'display_name':name,'description':name}
            for name,key in [('start','fixture.port.boundary'),('receive','fixture.port.receive'),
                             ('send','fixture.port.send'),('end','fixture.port.boundary')]],
            'edges':[['start','receive'],['receive','send'],['send','end']]}}))
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path/'bundle')
    received,seen = object(),[]
    port = {'receive':lambda _: {'value':received},'send':lambda item:seen.append(item['value'])}
    asyncio.run(bundle.run_async(capabilities={'vibeflow.port': port}, run_root=tmp_path / 'runs', runtime_options={'execution': execution}))
    assert seen == [received]
    call = bundle.workflow.blocks[0].node("receive")
    assert (call.completion,call.executor) == ('suspend','event_loop')
    assert str(source) not in bundle.workflow.to_json()


def test_bundle_locators_are_relocated_and_publication_handles_python_caches(tmp_path):
    from tests.targets.python.test_aot_bundle import build
    from vibeflow.targets.shared.aot_publish import validate_owned_build_directory, AotPublishError
    path = build(tmp_path)
    bundle = load_bundle(path)
    runtime = bundle.create_runtime(run_dir=tmp_path/'run')
    descriptor = runtime.registry.descriptor('demo')
    assert Path(descriptor.implementations[0].source.ref).is_relative_to(path)
    assert Path(runtime.registry.source_info('demo').path).is_relative_to(path)
    assert Path(bundle.workflow.source.ref).is_relative_to(path)
    cache = Path(descriptor.implementations[0].source.ref).parent / '__pycache__'
    cache.mkdir(parents=True, exist_ok=True)
    (cache/'plugin.cpython-313.pyc').write_bytes(b'generated cache')
    validate_owned_build_directory(path,manifest_format='vibeflow.aot-build.v5')
    (cache/'personal.txt').write_text('must preserve')
    with pytest.raises(AotPublishError,match='untracked'):
        validate_owned_build_directory(path,manifest_format='vibeflow.aot-build.v5')


def test_business_path_strings_are_not_relocated(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    ordinary = str(source/'external-checkpoint.pt')
    code = EXECUTABLE.replace('contract={"provides":',
        'contract={"params_schema":{"path":{"type":"string"}},"params_defaults":{"path":'+repr(ordinary)+'},"provides":')
    code = code.replace('return {"result": 7}','return {"result": params["path"]}')
    workspace,config = executable_project(source,code)
    build_python_aot(PythonBuildRequest(workspace,config,tmp_path/'bundle'))
    shutil.rmtree(source)
    assert load_bundle(tmp_path/'bundle').run(run_root=tmp_path/'runs').context.get('result')['value'] == ordinary


def test_separately_installed_runtime_factory_is_packaged(tmp_path, monkeypatch):
    source, environment = tmp_path / 'source', tmp_path / 'site'
    source.mkdir()
    package = environment / 'independent_runtime'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'helper.py').write_text('value = 23\n')
    (package / 'factory.py').write_text('from independent_runtime.helper import value\n'
        'class Runtime:\n    def before_run(self, context): assert value == 23\n'
        'def create(context): return Runtime()\n')
    monkeypatch.syspath_prepend(str(environment))
    code = EXECUTABLE.replace('from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,base_lib',
        'from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,base_lib,SourceLocator')
    code = code.replace('plugin=Plugin(',
        'plugin=Plugin(runtime=SourceLocator(kind="module",ref="independent_runtime.factory",export="create"),')
    workspace, config = executable_project(source, code)
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    shutil.rmtree(source)
    shutil.rmtree(environment)
    for name in tuple(sys.modules):
        if name == 'independent_runtime' or name.startswith('independent_runtime.'):
            monkeypatch.delitem(sys.modules, name)
    result = load_bundle(tmp_path / 'bundle').run(run_root=tmp_path / 'runs')
    assert result.context.get('result')['value'] == 7


def test_installed_namespace_package_across_two_roots_is_relocatable(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    roots = [tmp_path.parent / (tmp_path.name+'-site-a'), tmp_path.parent / (tmp_path.name+'-site-b')]
    for root in roots:
        (root / 'training_namespace').mkdir(parents=True)
        monkeypatch.syspath_prepend(str(root))
    (roots[0] / 'training_namespace/entry.py').write_text(
        'from training_namespace.implementation import plugin\n')
    (roots[1] / 'training_namespace/implementation.py').write_text(PLUGIN_SOURCE)
    (roots[0] / 'training_namespace/asset-a.txt').write_text('first')
    (roots[1] / 'training_namespace/asset-b.txt').write_text('second')
    workspace, config = executable_project(source)
    data = json.loads(config.read_text())
    data['plugins'] = [{'source': {'kind': 'module', 'ref': 'training_namespace.entry'}}]
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    for root in (source, *roots):
        shutil.rmtree(root)
    for name in tuple(sys.modules):
        if name == 'training_namespace' or name.startswith('training_namespace.'):
            monkeypatch.delitem(sys.modules, name)
    bundle = load_bundle(tmp_path / 'bundle')
    assert bundle.run(run_root=tmp_path / 'runs').context.get('result')['value'] == 7
    assert (tmp_path / 'bundle/_dependencies/training_namespace/asset-a.txt').read_text() == 'first'
    assert (tmp_path / 'bundle/_dependencies/training_namespace/asset-b.txt').read_text() == 'second'


def test_mapping_runtime_options_keep_workspace_and_bundle_defaults(tmp_path):
    from dataclasses import replace
    from types import MappingProxyType
    from vibeflow.tooling.application.python.project.project_options import _workspace_runtime_options
    source = tmp_path / 'source'
    source.mkdir()
    workspace, config = executable_project(source)
    defaults = {'execution': 'compiled', 'trace': 'off', 'node_hooks': False}
    workspace = replace(workspace, roots=(replace(workspace.roots[0], runtime_options=defaults),))
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    overrides = MappingProxyType({'run_hooks': False})
    expected = _workspace_runtime_options(config, workspace=workspace, overrides=overrides)
    bundle = load_bundle(tmp_path / 'bundle')
    assert bundle.effective_options(overrides) == expected
    runtime = bundle.create_runtime(runtime_options=overrides, run_dir=tmp_path / 'run')
    assert runtime.runtime_options == expected
    assert runtime.run({}).get('result')['value'] == 7


def test_runtime_factory_failure_has_source_error_model_and_releases_created_plugins(tmp_path):
    from vibeflow.tooling.application.python import CheckedRunError, run_workspace_checked
    source = tmp_path / 'source'
    source.mkdir()
    marker = tmp_path / 'released.txt'
    factory = ('class Runtime:\n'
        '    def dispose(self):\n'
        f'        with open({str(marker)!r},"a") as stream: stream.write("released\\n")\n'
        '        raise RuntimeError("dispose failure")\n'
        'def create(context): return Runtime()\n'
        'plugin=Plugin(runtime=create,')
    workspace, config = executable_project(source, plugin_source=PLUGIN_SOURCE.replace('plugin=Plugin(', factory))
    (source / 'plugins/broken').mkdir()
    (source / 'plugins/broken/plugin.py').write_text('from vibeflow.targets.python.sdk import Plugin\n'
        'def create(context): raise RuntimeError("factory root cause")\n'
        'plugin=Plugin(id="broken",runtime=create)\n')
    data = json.loads(config.read_text())
    data['plugins'].append({'source': {'kind': 'file', 'ref': 'plugins/broken/plugin.py'}})
    config.write_text(json.dumps(data))
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    runners = [lambda: run_workspace_checked(config, workspace=workspace, run_root=tmp_path / 'native-runs'),
               lambda: load_bundle(tmp_path / 'bundle').run(run_root=tmp_path / 'bundle-runs')]
    for run in runners:
        with pytest.raises(CheckedRunError) as captured:
            run()
        assert captured.value.result.health.status == 'ERROR'
        assert captured.value.result.health.errors[0].code == 'PLUGIN.FACTORY.LOAD'
        assert 'factory root cause' in str(captured.value.__cause__)
        assert len(captured.value.__cause__.cleanup_errors) == 1
        status = json.loads((captured.value.result.run_dir / 'status.json').read_text())
        assert status['state'] == 'failed'
    assert marker.read_text().splitlines() == ['released', 'released']


def test_runtime_disposal_failure_marks_low_level_bundle_runtime_failed(tmp_path):
    from tests.targets.python.test_aot_bundle import build
    code = PLUGIN_SOURCE.replace('plugin=Plugin(',
        'class Runtime:\n    def dispose(self): raise RuntimeError("dispose failure")\n'
        'def create(context): return Runtime()\nplugin=Plugin(runtime=create,')
    path = build(tmp_path, plugin_source=code)
    runtime = load_bundle(path).create_runtime(run_dir=tmp_path / 'run')
    with pytest.raises(RuntimeError, match='dispose failure'):
        runtime.run({})
    assert json.loads((tmp_path / 'run/status.json').read_text())['state'] == 'failed'


def test_build_cli_preserves_checked_run_concerns(tmp_path, capsys):
    from vibeflow.tooling.application.cli import main
    source = tmp_path / 'source'
    shutil.copytree(ROOT / 'sandbox/python/minimal', source,
                    ignore=shutil.ignore_patterns('runs', '__pycache__'))
    status = main(['build', '--workspace', str(source / 'vibeflow_config.jsonc'),
                   '--config', str(source / 'project/configs/config.jsonc'), '--out-dir', str(tmp_path / 'bundle')])
    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'CONCERNS'
    assert payload['result_code'] == 'VIBEFLOW_BUILD_CONCERNS'
    assert payload['warnings']


@pytest.mark.parametrize('execution', ('plan', 'block', 'compiled'))
def test_plugin_initialization_precedes_node_construction_without_changing_instance_grain(tmp_path, execution):
    from vibeflow.tooling.application.python import run_workspace_checked
    source = tmp_path / 'source'
    source.mkdir()
    marker = tmp_path / "ready"
    code = EXECUTABLE.replace('class Demo:',
        'class Demo:\n    def __init__(self):\n        from pathlib import Path\n        assert Path('+repr(str(marker))+').exists(), "plugin must precede Node construction"')
    lifecycle = ('class Runtime:\n    def dispose(self):\n        from pathlib import Path\n        Path('+repr(str(marker))+').unlink()\n'
        'def create(context):\n    from pathlib import Path\n    Path('+repr(str(marker))+').touch()\n    return Runtime()\nplugin=Plugin(runtime=create,')
    workspace, config = executable_project(source, code.replace('["vibeflow.process","demo.rules"]', '[]'), plugin_source=PLUGIN_SOURCE.replace('plugin=Plugin(', lifecycle))
    assert run_workspace_checked(config, workspace=workspace, run_root=tmp_path / 'native').context.get('result')['value'] == 7
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    shutil.rmtree(source)
    bundle = load_bundle(tmp_path / 'bundle')
    first = bundle.create_runtime(run_dir=tmp_path / 'first', runtime_options={'execution': execution})
    first.run({})
    node = first._frames['demo'].node
    first.run({})
    assert first._frames['demo'].node is node
    second = bundle.create_runtime(run_dir=tmp_path / 'second', runtime_options={'execution': execution})
    second.run({})
    assert second._frames['demo'].node is not node



def test_delayed_node_module_binds_after_runtime_plugin_and_is_not_imported_at_build(tmp_path, monkeypatch):
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.tooling.application.python import run_workspace_checked
    source = tmp_path / 'source'
    source.mkdir()
    marker = tmp_path / "ready"
    (source / 'delayed.py').write_text('from pathlib import Path\nassert Path('+repr(str(marker))+').exists(), "runtime plugin must initialize first"\n'
        'class Demo:\n    def run_pure(self,inputs,params): return {"result":7}\n')
    code = (EXECUTABLE[:EXECUTABLE.index('@node(node_type="demo.shell", id="demo",')] +
        'from vibeflow.targets.python.sdk import SourceLocator\nlate=node(id="demo",node_type="demo.shell",rulesets=[],contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Result"]}},source=SourceLocator(kind="file",ref="delayed.py",export="Demo"))\n')
    lifecycle = ('class Runtime: pass\ndef create(context):\n    from pathlib import Path\n    Path('+repr(str(marker))+').touch()\n    return Runtime()\nplugin=Plugin(runtime=create,')
    workspace, config = executable_project(source, code.replace('["vibeflow.process","demo.rules"]', '[]'), plugin_source=PLUGIN_SOURCE.replace('plugin=Plugin(', lifecycle))
    assert run_workspace_checked(config, workspace=workspace, run_root=tmp_path / 'native').context.get('result')['value'] == 7
    original = NodeRegistry.get
    def forbidden(registry, key):
        if key == 'demo': raise AssertionError('AOT build imported a delayed Node')
        return original(registry, key)
    with monkeypatch.context() as scope:
        scope.setattr(NodeRegistry, 'get', forbidden)
        build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    shutil.rmtree(source)
    assert load_bundle(tmp_path / 'bundle').run(run_root=tmp_path / 'aot').context.get('result')['value'] == 7
