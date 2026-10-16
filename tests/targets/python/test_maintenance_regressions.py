"""Original failure scenarios retained after removing application workarounds."""
import sys
import json
import shutil

import pytest

from tests.targets.python.test_code_plugins import executable_project, EXECUTABLE


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
        from vibeflow.tooling.application.python import runner
        monkeypatch.setattr(runner, "_execute_runtime", fail)
    with pytest.raises(ValueError, match="original business failure") as captured:
        workspace_service.run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs")
    assert released == ["second", "first"]
    assert len(captured.value.cleanup_errors) == 2


def test_planned_inventory_handles_deep_same_named_definitions_tasks_and_cycles():
    from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec
    from vibeflow.targets.python.runtime.helpers import has_planned, planned_items
    leaf = NodeSpec("leaf", "future", status="planned")
    deep = GraphConfig(nodes=(leaf,))
    inner = NodesetSpec("same", "Same", "Inner", (), (), deep)
    middle = GraphConfig(nodes=(), nodesets={"same": inner})
    outer = NodesetSpec("same", "Same", "Outer", (), (), middle)
    root = GraphConfig(nodes=(NodeSpec("manager", "manager", task_targets={"future": leaf}),), nodesets={"same": outer})
    deep.nodesets["cycle"] = outer
    assert has_planned(root)
    assert [item["id"] for item in planned_items(root)] == [
        "manager.$task.future", "nodeset.same.nodeset.same.leaf"]


def test_dispatch_option_selection_matches_argparse_and_stops_at_delegated_argv():
    from vibeflow.tooling.application.cli import _option_value
    assert _option_value(["--workspace", "first", "--workspace=second", "--", "--workspace", "business"], "--workspace") == "second"
    assert _option_value(["--workspace=first", "--workspace", "second"], "--workspace") == "second"


@pytest.mark.parametrize("previous_kind", ("namespace", "module"))
def test_switching_projects_replaces_module_namespace_and_child_caches(tmp_path, previous_kind):
    import importlib
    from vibeflow.targets.python.sdk.loading import source_paths, _discard_foreign_project_modules
    previous, current = tmp_path / "previous", tmp_path / "current"
    previous.mkdir(); current.mkdir()
    name = "switching_project_nodes"
    if previous_kind == "namespace":
        (previous / name).mkdir()
        (previous / name / "old.py").write_text("value = 'previous'\n")
        (current / (name + ".py")).write_text("value = 'current'\n")
    else:
        (previous / (name + ".py")).write_text("value = 'previous'\n")
        (current / name).mkdir()
        (current / name / "fresh.py").write_text("value = 'current'\n")
    with source_paths((previous,)):
        old = importlib.import_module(name)
        if previous_kind == "namespace": importlib.import_module(name + ".old")
    try:
        with source_paths((current,)):
            _discard_foreign_project_modules((current,))
            loaded = importlib.import_module(name)
            assert loaded is not old
            assert name + ".old" not in sys.modules
            if previous_kind == "namespace": assert loaded.value == "current"
            else: assert importlib.import_module(name + ".fresh").value == "current"
    finally:
        for key in tuple(sys.modules):
            if key == name or key.startswith(name + "."): sys.modules.pop(key)


@pytest.mark.parametrize("phase", ("compiler", "runtime"))
def test_partial_creation_disposes_in_creation_order_with_project_imports(tmp_path, phase):
    from vibeflow.tooling.application.python import (
        run_workspace_checked, CheckedRunError, PythonBuildRequest, build_python_aot, load_bundle)
    source = tmp_path / "source"
    source.mkdir()
    marker = tmp_path / "cleanup.txt"
    (source / "lazy_cleanup.py").write_text(
        f'def cleanup(label):\n    with open({str(marker)!r},"a") as stream: stream.write(label+"\\n")\n')
    (source / "lifecycle.py").write_text(
        'class Runtime:\n    def __init__(self,label): self.label=label\n'
        '    def dispose(self):\n        from lazy_cleanup import cleanup\n        cleanup(self.label)\n'
        'def first(context): return Runtime("first")\n'
        'def second(context): return Runtime("second")\n')
    code = EXECUTABLE.replace('Plugin,node,rule,ruleset,base_lib',
                              'Plugin,node,rule,ruleset,base_lib,SourceLocator')
    code = code.replace('plugin=Plugin(',
        f'plugin=Plugin(priority=300,{phase}=SourceLocator(kind="file",ref="lifecycle.py",export="first"),')
    workspace, config = executable_project(source, code)
    (source / "second.py").write_text('from vibeflow.targets.python.sdk import Plugin,SourceLocator\n'
        f'plugin=Plugin(id="second",priority=100,{phase}=SourceLocator(kind="file",ref="lifecycle.py",export="second"))\n')
    (source / "broken.py").write_text('from vibeflow.targets.python.sdk import Plugin\n'
        'def create(context): raise RuntimeError("factory failure")\n'
        f'plugin=Plugin(id="broken",priority=0,{phase}=create)\n')
    data = json.loads(config.read_text())
    data["plugins"].extend({"source": {"kind": "file", "ref": name}} for name in ("second.py", "broken.py"))
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
