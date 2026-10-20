"""Fixed bundle facts may be shared; execution state and import ownership may not."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from tests.targets.python.test_aot_bundle import build
from tests.targets.python.test_code_plugins import EXECUTABLE, executable_project
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle, PythonBundle
from vibeflow.targets.python.sdk.plugin import Plugin


def test_warm_runtime_does_not_reparse_facts_or_rebuild_plugin_index(tmp_path, monkeypatch):
    path = build(tmp_path)
    calls = []
    original = Plugin.bindings

    def bindings(owner):
        if owner.id == 'demo':
            calls.append(owner)
        return original(owner)

    monkeypatch.setattr(Plugin, 'bindings', bindings)
    bundle = load_bundle(path)
    assert not calls  # Loading facts must not bootstrap plugins early.

    def forbidden(*args, **kwargs):
        raise AssertionError('runtime repeated fixed descriptor decoding')

    monkeypatch.setattr(PythonBundle, '_descriptor', forbidden)
    first = bundle.create_runtime(run_dir=tmp_path / 'first')
    assert not calls
    second = bundle.create_runtime(run_dir=tmp_path / 'second')
    for runtime in (first, second):
        assert runtime.run({}).get('result')['value'] == 7
    assert len(calls) == 1
    assert first.registry is not second.registry
    assert first._frames['demo'].node is not second._frames['demo'].node


def test_cached_metadata_preserves_config_and_lifecycle_instance_isolation(tmp_path):
    marker = tmp_path / 'lifecycle.txt'
    source = EXECUTABLE.replace('class Demo:\n', 'class Demo:\n    def __init__(self):\n        self.used = False\n')
    source = source.replace('return {"result": 7}',
        'assert not self.used\n        self.used = True\n        return {"result": params["delta"]}')
    source = source.replace('contract={"provides":',
        'contract={"params_schema":{"delta":{"type":"number"}},"params_defaults":{"delta":1},"provides":')
    source = source.replace('plugin=Plugin(', f'''
from pathlib import Path
class Monitor:
    def __init__(self): self.used = False
    def before_run(self, context):
        assert not self.used
        self.used = True
    def dispose(self):
        with Path({str(marker)!r}).open('a') as stream: stream.write('disposed\\n')
def create(context): return Monitor()
plugin=Plugin(runtime=create,''')
    path = build(tmp_path, source)
    bundle = load_bundle(path)
    for i, expected in enumerate((3, 9, 1)):
        overrides = {'demo': {'delta': expected}} if i < 2 else None
        runtime = bundle.create_runtime(run_dir=tmp_path / f'run-{i}', node_config_overrides=overrides)
        assert runtime.run({}).get('result')['value'] == expected
    assert marker.read_text().splitlines() == ['disposed'] * 3


def test_same_named_modules_stay_with_their_bundle_after_a_b_a_switch(tmp_path):
    bundles = []
    for name, value in [('a', 11), ('b', 29)]:
        root = tmp_path / name
        root.mkdir()
        source = root / 'source'
        source.mkdir()
        (source / 'support.py').write_text(f'VALUE = {value}\n')
        code = EXECUTABLE.replace('return {"result": 7}', 'from support import VALUE\n        return {"result": VALUE}')
        code = code.replace('@node(type_key="demo",', '@node(type_key="demo",implementation_files=["support.py"],')
        workspace, config = executable_project(source, code)
        build_python_aot(PythonBuildRequest(workspace, config, root / 'bundle'))
        bundles.append(load_bundle(root / 'bundle'))
    for i, (bundle, expected) in enumerate([(bundles[0], 11), (bundles[1], 29), (bundles[0], 11)]):
        assert bundle.create_runtime(run_dir=tmp_path / f'run-{i}').run({}).get('result')['value'] == expected


@pytest.mark.parametrize('warm', [False, True])
def test_concurrent_calls_keep_node_instances_and_parameter_overrides_separate(tmp_path, warm):
    source = EXECUTABLE.replace('class Demo:\n', 'class Demo:\n    def __init__(self):\n        self.used = False\n')
    source = source.replace('return {"result": 7}',
        'assert not self.used\n        self.used = True\n        return {"result": params["delta"]}')
    source = source.replace('contract={"provides":',
        'contract={"params_schema":{"delta":{"type":"number"}},"params_defaults":{"delta":1},"provides":')
    bundle = load_bundle(build(tmp_path, source))
    if warm:
        assert bundle.create_runtime(run_dir=tmp_path / 'warm').run({}).get('result')['value'] == 1
    def invoke(value):
        return bundle.create_runtime(run_dir=tmp_path / f'run-{value}',
            node_config_overrides={'demo': {'delta': value}},
            runtime_options={'execution': 'compiled'}).run({}).get('result')['value']
    with ThreadPoolExecutor(max_workers=4) as workers:
        assert list(workers.map(invoke, range(4))) == list(range(4))
