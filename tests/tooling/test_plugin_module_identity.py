"""Plugin configuration and its declared library share one owned module tree."""
import json
from pathlib import Path
import shutil

from tests.targets.python.test_code_plugins import executable_project, EXECUTABLE, PLUGIN_SOURCE


def project(root, value):
    source = EXECUTABLE.replace('from vibeflow.core.rules import RuleResult',
        'from plugins.demo.arithmetic import calculate').replace('return {"result": 7}',
        'return {"result": calculate(41)}').replace('id="demo",contract=',
        'id="demo",base_libs=["demo.math"],contract=')
    plugin = ('from vibeflow.targets.python.sdk import base_lib,SourceLocator\n'
        'from . import arithmetic\n'
        'math=base_lib(id="demo.math",rulesets=[],source=SourceLocator("file","arithmetic.py","calculate"))\n'
        'class Runtime: pass\n'
        'def create(context):\n    arithmetic.shift=context["config"]["value"]\n    return Runtime()\n'
        + PLUGIN_SOURCE.replace('resources=[shell,check,rules]', 'runtime=create,resources=[shell,check,rules,math]'))
    # Declare the helper before bootstrap; the SDK binds it at preparation time.
    package = Path(root) / 'plugins/demo'
    package.mkdir(parents=True)
    (package / 'arithmetic.py').write_text('shift=0\ndef calculate(value):return value+shift\n')
    workspace, config = executable_project(root, source, plugin_source=plugin)
    data = json.loads(config.read_text())
    data['plugins'][0]['config'] = {'value':value}
    config.write_text(json.dumps(data))
    return workspace, config


def test_source_configuration_and_delayed_imports_share_the_plugin_module(tmp_path):
    from vibeflow.tooling.application.python import run_workspace_checked
    workspace, config = project(tmp_path / 'source', 9)
    first = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / 'runs', run_id='first')
    data = json.loads(config.read_text()); data['plugins'][0]['config']['value'] = 20
    config.write_text(json.dumps(data))
    second = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / 'runs', run_id='second')
    assert first.context.get('result')['value'] == 50
    assert second.context.get('result')['value'] == 61


def test_relocated_aot_configuration_uses_its_bundle_module(tmp_path):
    from vibeflow.tooling.application.python import PythonBuildRequest, build_python_aot, load_bundle
    workspace, config = project(tmp_path / 'source', 9)
    build_python_aot(PythonBuildRequest(workspace, config, tmp_path / 'bundle'))
    shutil.rmtree(tmp_path / 'source')
    bundle = load_bundle(tmp_path / 'bundle')
    for index in range(2):
        result = bundle.run(run_root=tmp_path / 'runs', run_id=str(index))
        assert result.context.get('result')['value'] == 50
