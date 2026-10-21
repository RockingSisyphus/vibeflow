"""Original failure scenarios retained after removing application workarounds."""
import sys
import json
import shutil

import pytest

from tests.targets.python.test_code_plugins import executable_project, EXECUTABLE, PLUGIN_SOURCE


def test_source_api_keeps_lazy_import_paths_only_during_execution(tmp_path):
    from vibeflow.tooling.application.python import run_workspace_checked
    project = tmp_path / "source"
    project.mkdir()
    (project / "late_module.py").write_text("value = 19\n")
    source = EXECUTABLE.replace('return {"result": 7}', 'import late_module\n        return {"result": late_module.value}')
    # This is an ordinary Python execution contract; no static source Rules selected.
    source = source.replace('rulesets=["vibeflow.process","demo.rules"]', 'rulesets=[]')
    workspace, config = executable_project(project, source)
    result = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs",
                                   runtime_options={"trace": "off"})
    assert result.context.get("result")["value"] == 19
    assert str(project) not in sys.path


@pytest.mark.parametrize("boundary", ("runtime", "compiler"))
def test_source_failure_keeps_primary_and_releases_every_plugin(tmp_path, monkeypatch, boundary):
    from vibeflow.tooling.application.python import workspace_service
    from vibeflow.tooling.application.python.project import lifecycle
    from vibeflow.targets.python.project.plugins import PluginRegistry
    workspace, config = executable_project(tmp_path)
    released = []
    class Plugin:
        def __init__(self, name): self.name = name
        def dispose(self):
            released.append(self.name)
            raise RuntimeError("cleanup " + self.name)
    original = lifecycle.lifecycle_registry
    def registry(*args, plugin_types, **kwargs):
        if boundary not in plugin_types:
            return original(*args, plugin_types=plugin_types, **kwargs)
        result = PluginRegistry()
        for name in ("first", "second"):
            result.register(Plugin(name), plugin_type=boundary)
        return result
    monkeypatch.setattr(lifecycle, "lifecycle_registry", registry)
    def fail(*args, **kwargs): raise ValueError("original business failure")
    if boundary == "compiler":
        monkeypatch.setattr(workspace_service.GraphCompiler, "compile_with_findings", fail)
    else:
        from vibeflow.tooling.application.python import execution
        monkeypatch.setattr(execution, "_execute_runtime", fail)
    with pytest.raises(ValueError, match="original business failure") as captured:
        workspace_service.run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs")
    assert released == ["second", "first"]
    assert len(captured.value.cleanup_errors) == 2


def test_planned_inventory_handles_deep_same_named_definitions_and_cycles():
    from vibeflow.core.flow import GraphConfig, NodeCallSpec, NodesetTypeSpec
    from vibeflow.targets.python.runtime.helpers import has_planned, planned_items
    leaf = NodeCallSpec("leaf", "future", status="planned")
    deep = GraphConfig(nodes=(leaf,))
    inner = NodesetTypeSpec("same", "Same", "Inner", (), (), deep)
    middle = GraphConfig(nodes=(), nodeset_types={"same": inner})
    outer = NodesetTypeSpec("same", "Same", "Outer", (), (), middle)
    root = GraphConfig(nodes=(leaf,), nodeset_types={"same": outer})
    deep.nodeset_types["cycle"] = outer
    assert has_planned(root)
    assert [item["id"] for item in planned_items(root)] == [
        "leaf", "nodeset.same.nodeset.same.leaf"]


def test_dispatch_option_selection_matches_argparse_and_stops_at_delegated_argv():
    from vibeflow.tooling.application.cli import _option_value
    assert _option_value(["--workspace", "first", "--workspace=second", "--", "--workspace", "business"], "--workspace") == "second"
    assert _option_value(["--workspace=first", "--workspace", "second"], "--workspace") == "second"


@pytest.mark.parametrize("previous_kind", ("namespace", "module"))
def test_switching_projects_keeps_owned_modules_independent(tmp_path, previous_kind):
    from vibeflow.targets.python.sdk.source_namespace import source_namespace
    previous, current = tmp_path / "previous", tmp_path / "current"
    previous.mkdir(); current.mkdir()
    name = "switching_project_nodes"
    if previous_kind == "namespace":
        (previous / name).mkdir()
        (previous / name / "old.py").write_text("value = 'previous'\n")
        (current / (name + ".py")).write_text("value = 'current'\n")
        old_import = f"from {name}.old import value\n"
        new_import = f"from {name} import value\n"
    else:
        (previous / (name + ".py")).write_text("value = 'previous'\n")
        (current / name).mkdir()
        (current / name / "fresh.py").write_text("value = 'current'\n")
        old_import = f"from {name} import value\n"
        new_import = f"from {name}.fresh import value\n"
    (previous / "probe.py").write_text(old_import)
    (current / "probe.py").write_text(new_import)
    old = source_namespace(previous).load(previous / "probe.py")
    loaded = source_namespace(current).load(current / "probe.py")
    assert old.value == "previous" and loaded.value == "current"
    assert name not in sys.modules


@pytest.mark.parametrize("phase", ("compiler", "runtime"))
def test_partial_creation_disposes_in_creation_order_with_project_imports(tmp_path, phase):
    from vibeflow.tooling.application.python import (
        run_workspace_checked, CheckedRunError, PythonBuildRequest, build_python_aot, load_bundle)
    source = tmp_path / "source"
    marker = tmp_path / "cleanup.txt"
    plugin = 'from vibeflow.targets.python.sdk import SourceLocator\n' + PLUGIN_SOURCE.replace(
        'plugin=Plugin(', f'plugin=Plugin(priority=300,{phase}=SourceLocator("file","lifecycle.py","first"),')
    workspace, config = executable_project(source, plugin_source=plugin)
    helpers = ('class Runtime:\n    def __init__(self,label): self.label=label\n'
        '    def dispose(self):\n        from .lazy_cleanup import cleanup\n        cleanup(self.label)\n'
        'def first(context): return Runtime("first")\n'
        'def second(context): return Runtime("second")\n')
    demo = source / "plugins/demo"
    (demo / "lifecycle.py").write_text(helpers)
    cleanup = f'def cleanup(label):\n    with open({str(marker)!r},"a") as stream: stream.write(label+"\\n")\n'
    (demo / "lazy_cleanup.py").write_text(cleanup)
    second = source / "plugins/second"
    second.mkdir()
    (second / "lifecycle.py").write_text(helpers)
    (second / "lazy_cleanup.py").write_text(cleanup)
    (second / "plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin,SourceLocator\n'
        f'plugin=Plugin(id="second",priority=100,{phase}=SourceLocator("file","lifecycle.py","second"))\n')
    broken = source / "plugins/broken"
    broken.mkdir()
    (broken / "plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin\n'
        'def create(context): raise RuntimeError("factory failure")\n'
        f'plugin=Plugin(id="broken",priority=0,{phase}=create)\n')
    data = json.loads(config.read_text())
    data["plugins"].extend({"source": {"kind": "file", "ref": name}} for name in (
        "plugins/second/plugin.py", "plugins/broken/plugin.py"))
    config.write_text(json.dumps(data))
    if phase == "runtime":
        build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "bundle"))
    with pytest.raises(CheckedRunError) as captured:
        run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "native")
    assert captured.value.result.health.errors[0].code == "PLUGIN.FACTORY.LOAD"
    assert marker.read_text().splitlines() == ["second", "first"]
    assert str(source) not in sys.path
    if phase == "runtime":
        assert not getattr(captured.value.__cause__, "cleanup_errors", ())
        marker.write_text("")
        shutil.rmtree(source)
        with pytest.raises(CheckedRunError) as bundled:
            load_bundle(tmp_path / "bundle").run(run_root=tmp_path / "aot")
        assert bundled.value.result.health.errors[0].code == "PLUGIN.FACTORY.LOAD"
        assert not getattr(bundled.value.__cause__, "cleanup_errors", ())
        assert marker.read_text().splitlines() == ["second", "first"]
