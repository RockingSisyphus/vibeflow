"""Explicit extension selections reach the same engine before source binding."""
import json

import pytest

from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
from vibeflow.tooling.project.workspace_loader import load_project_workspace


@pytest.mark.parametrize("selection", [(), ("vibeflow.plugin",)])
def test_plugin_import_rule_is_selected_and_blocks_the_actual_write(tmp_path, selection):
    marker = tmp_path / "loaded"
    path = tmp_path / "extension.py"
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\nclass Plugin: pass\n')
    (tmp_path / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    with path.open("a") as handle:
        handle.write("\ndef create(context): return Plugin()\n")
    (tmp_path / "plugin.py").write_text("from vibeflow.targets.python.sdk import Plugin, SourceLocator\n" +
        f"plugin=Plugin(id='extension',runtime=SourceLocator(kind='file',ref='extension.py',export='create'),rulesets={selection!r})\n")
    config = tmp_path / "main.jsonc"
    config.write_text(json.dumps({"plugins":[{"source":{"kind":"file","ref":"plugin.py"}}],"rulesets":[],"pipeline":{"nodes":[{"id":"stub","type_used":"planned.stub","status":"planned","flow_kind":"process","requires":[],"provides":[],"display_name":"Stub","description":"Native planned call"}]}}))
    report = validate_workspace_config_path(config,workspace=load_project_workspace(config))
    assert not marker.exists()
    if not selection:
        from vibeflow.tooling.application.python.project.declarations import declared_python_registry
        from vibeflow.tooling.application.python.project.lifecycle import lifecycle_registry
        from vibeflow.targets.python.project.plugins import release_runtime_plugins
        registry = declared_python_registry(load_project_workspace(config), config)
        instances = lifecycle_registry(registry, workflow_id="test", config_path=config, plugin_types=("runtime",))
        release_runtime_plugins(instances)
        assert marker.exists()
    assert ("NODE.IMPORT.SIDE_EFFECT" in [item.code for item in report.errors]) == bool(selection)
    assert not report.errors if not selection else all(item.object_id == "extension.runtime" for item in report.errors)
    if selection:
        assert report.errors[0].object_type == "plugin"
        assert report.errors[0].object_id == "extension.runtime"


def test_declared_library_rule_checks_only_its_reached_sources_before_binding(tmp_path):
    from tests.fixtures.support.plugins import write_plugin
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
    marker = tmp_path / "library-loaded"
    (tmp_path / "library.py").write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\n')
    (tmp_path / "leaf.py").write_text('import library\nclass Leaf:\n    def run_pure(self,inputs,params): return {}\n')
    (tmp_path / "rule.py").write_text('''
def check(context, inputs, params):
    assert context.subject["kind"] == "base_lib" and context.subject["id"] == "library"
    assert "call" not in context.facts
    assert [source.module for source in context.require("source_context").files] == ["library"]
    return {"findings":[{"code":"TEST.LIBRARY.REJECT","message":"Review reached library",
        "object_type":"base_lib","object_id":context.subject["id"]}]}
''')
    declarations = ({"kind":"node","type_key":"leaf","display_name":"Leaf",
        "description":"Selected implementation","version":"1","flow_kind":"process","rulesets":[],"contract":{},
        "implementations":[{"language":"python","targets":["python"],"source":{"kind":"file","ref":"leaf.py","export":"Leaf"}}]},
    {"kind":"base_lib","id":"library","rulesets":["test.library"],
        "display_name":"Library","description":"One reached library",
        "implementations":[{"language":"python","targets":["python"],"source":{"kind":"file","ref":"library.py"}}]},
    {"kind":"rule","id":"test.library","scope":"source",
        "implementations":[{"language":"python","source":{"kind":"file","ref":"rule.py","export":"check"}}]},
    {"kind":"ruleset","id":"test.library",
        "calls":[{"id":"library","rule_id":"test.library"}],"entrypoints":{"import":["library"]}})
    write("vibeflow_project.jsonc",{"project_target":"python","quality_enabled":False,
})
    plugin = write_plugin(tmp_path, declarations, target="python")
    write("main.jsonc",{"plugins":[plugin], "rulesets":[],"pipeline":{"nodes":[{"id":"leaf","type_used":"leaf",
        "display_name":"Leaf","description":"One real call"}]}})
    report = validate_workspace_config_path(tmp_path / "main.jsonc",workspace=load_project_workspace(tmp_path / "main.jsonc"))
    finding = next(item for item in report.errors if item.code == "TEST.LIBRARY.REJECT")
    assert finding.object_type == "base_lib" and finding.object_id == "library"
    assert not marker.exists()
    from vibeflow.tooling.application.rule_review import effective_rule_plans
    preview = effective_rule_plans(tmp_path / "main.jsonc",phase="import")
    selected = next(item for item in preview["resources"] if item["id"] == "library")
    assert selected["rulesets"] == ["test.library"]
    assert selected["selection_source"] == str(tmp_path / "code_plugin.py")
    assert not marker.exists()


def test_resource_registration_preserves_explicit_rule_choices(tmp_path):
    from vibeflow.targets.python.sdk import base_lib, SourceLocator
    library = base_lib(id="lib", display_name="Library", description="One declared library",
        source=SourceLocator(kind="file", ref=str(tmp_path / "library.py")), rulesets=("custom",))
    assert library.descriptor.to_dict()["rulesets"] == ["custom"]
