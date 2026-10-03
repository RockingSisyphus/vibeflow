"""Explicit extension selections reach the same engine before source binding."""
import json

import pytest

from vibeflow.targets.python.project.plugin_loader import load_plugins_from_config
from vibeflow.targets.python.project.resources import PluginResourceRegistry
from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
from vibeflow.tooling.project.workspace_loader import load_project_workspace


@pytest.mark.parametrize("selection", [(), ("vibeflow.plugin",)])
def test_plugin_import_rule_is_selected_and_blocks_the_actual_write(tmp_path, selection):
    marker = tmp_path / "loaded"
    path = tmp_path / "extension.py"
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\nclass Plugin: pass\n')
    resources = PluginResourceRegistry()
    resources.register("extension",module=str(path),display_name="Extension",description="Selected source",
                       rulesets=selection)
    registry, findings = load_plugins_from_config({"plugins":["extension"]},base_path=tmp_path,
                                                  plugin_resource_registry=resources)
    assert marker.exists() == (not selection)
    assert bool(registry.runtime_plugins()) == (not selection)
    assert [item.code for item in findings] == (["NODE.IMPORT.SIDE_EFFECT"] if selection else [])
    if selection:
        assert findings[0].object_type == "plugin"
        assert findings[0].object_id == "extension"
    else:
        assert registry.to_dict()["plugins"][0]["rulesets"] == []
        assert "effect_scope" not in registry.to_dict()["plugins"][0]


def test_declared_library_rule_checks_only_its_reached_sources_before_binding(tmp_path):
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
    write("manifests/nodes/leaf.jsonc",{"kind":"node","type_key":"leaf","display_name":"Leaf",
        "description":"Selected implementation","version":"1","flow_kind":"process","rulesets":[],"contract":{},
        "implementations":[{"language":"python","targets":["python"],"source":{"kind":"file","ref":"leaf.py","export":"Leaf"}}]})
    write("manifests/base_lib/library.jsonc",{"kind":"base_lib","id":"library","rulesets":["test.library"],
        "display_name":"Library","description":"One reached library",
        "implementations":[{"language":"python","targets":["python"],"source":{"kind":"file","ref":"library.py"}}]})
    write("manifests/rules/library.jsonc",{"kind":"rule","id":"test.library","scope":"source",
        "implementations":[{"language":"python","source":{"kind":"file","ref":"rule.py","export":"check"}}]})
    write("manifests/rulesets/library.jsonc",{"kind":"ruleset","id":"test.library",
        "calls":[{"id":"library","rule_id":"test.library"}],"entrypoints":{"import":["library"]}})
    write("vibeflow_project.jsonc",{"project_target":"python","quality_enabled":False,
        "descriptors":{group:["manifests/"+group] for group in ("nodes","base_lib","rules","rulesets")}})
    write("main.jsonc",{"rulesets":[],"pipeline":{"nodes":[{"id":"leaf","type_used":"leaf",
        "display_name":"Leaf","description":"One real call"}]}})
    report = validate_workspace_config_path(tmp_path / "main.jsonc",workspace=load_project_workspace(tmp_path / "main.jsonc"))
    finding = next(item for item in report.errors if item.code == "TEST.LIBRARY.REJECT")
    assert finding.object_type == "base_lib" and finding.object_id == "library"
    assert not marker.exists()
    from vibeflow.tooling.application.rule_review import effective_rule_plans
    preview = effective_rule_plans(tmp_path / "main.jsonc",phase="import")
    selected = next(item for item in preview["resources"] if item["id"] == "library")
    assert selected["rulesets"] == ["test.library"]
    assert selected["selection_source"] == str(tmp_path / "manifests/base_lib/library.jsonc")
    assert not marker.exists()


def test_resource_registration_preserves_explicit_rule_choices(tmp_path):
    # Declarations need no executable symbols to expose their review selection.
    from vibeflow.targets.python.project.resources import BaseLibRegistry
    libraries = BaseLibRegistry()
    libraries.register("lib",module="library",display_name="Library",description="One declared library",rulesets=("custom",))
    assert libraries.get("lib").to_dict()["rulesets"] == ["custom"]
