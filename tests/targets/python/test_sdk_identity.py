"""Direct SDK objects and locator assertions describe one implementation."""

import json
import pytest

from vibeflow.tooling.project.descriptor_loader import DescriptorLoadError, load_workflow_plugins
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def project(tmp_path, options="", suffix=""):
    (tmp_path / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "p", "path": "."}]}))
    (tmp_path / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (tmp_path / "plugin.py").write_text(
        'from vibeflow.targets.python.sdk import Plugin,node\n'
        f'@node(type_key="actual",contract={{}},rulesets=[]{options})\n'
        'class Actual:\n'
        '    implementation = "ordinary business attribute"\n'
        '    def run_pure(self,inputs,params):\n'
        '        return {}\n' + suffix + '\nplugin=Plugin(id="example",resources=[Actual])\n')
    config = tmp_path / "workflow.jsonc"
    config.write_text(json.dumps({"plugins": [{"source": {"kind": "file", "ref": "plugin.py"}}],
        "pipeline": {"nodes": [], "edges": []}}))
    return load_workspace_config(tmp_path / "vibeflow_config.jsonc"), config


@pytest.mark.parametrize("kind,reference,export", [("file","./plugin.py","Actual"),
    ("module","plugin","Actual"), ("file","plugin.py","Alias")])
def test_same_source_metadata_and_loaded_alias_use_actual_symbol(tmp_path, kind, reference, export):
    source = {"language":"python", "targets":["python"], "completion":"immediate",
              "source":{"kind":kind,"ref":reference,"export":export},
              "implementation_files":[{"kind":"file","ref":"support.py"}]}
    (tmp_path / "support.py").write_text('def helper():\n    return 1\n')
    workspace, config = project(tmp_path, ',implementations='+repr([source]), 'Alias = Actual\n')
    loaded = load_workflow_plugins(workspace, config)
    implementation = loaded.catalogs.nodes.require("actual").implementations[0]
    assert implementation.source.ref == str(tmp_path / "plugin.py")
    assert implementation.source.export == "Actual"
    assert implementation.completion == "immediate"
    assert implementation.implementation_files[0].ref == str(tmp_path / "support.py")
    actual = loaded.bindings[("example", "node", "actual")]
    assert actual.implementation == "ordinary business attribute"


def test_different_source_reports_both_positions_without_importing_it(tmp_path):
    marker = tmp_path / "wrong-imported"
    (tmp_path / "wrong.py").write_text(f'open({str(marker)!r},"w").write("loaded")\nclass Wrong: pass\n')
    source = {"language":"python", "targets":["python"],
              "source":{"kind":"file","ref":"wrong.py","export":"Wrong"}}
    workspace, config = project(tmp_path, ',implementations='+repr([source]))
    with pytest.raises(DescriptorLoadError) as captured:
        load_workflow_plugins(workspace, config)
    error = captured.value
    assert error.code == "RESOURCE.IMPLEMENTATION.CONFLICT"
    assert error.details["actual"]["path"] == str(tmp_path / "plugin.py")
    assert error.details["declared"]["ref"] == str(tmp_path / "wrong.py")
    assert not marker.exists()


def test_sdk_fixed_contributions_rebind_config_without_revalidating_resources(monkeypatch):
    from vibeflow.core.rules import RulesetDescriptor
    from vibeflow.targets.python.sdk import Plugin, ruleset
    resource = ruleset(id="fixed", calls=[])
    monkeypatch.setattr(RulesetDescriptor, "to_dict", lambda _: pytest.fail("not a serialization boundary"))
    plugin = Plugin(id="fixed", resources=[resource])
    first = plugin.contributions({"items":[1]})
    second = plugin.contributions({"items":[2]})
    assert first.resources is second.resources
    assert first.config["items"] == (1,)
    assert second.config["items"] == (2,)
    with pytest.raises(ValueError, match="object"):
        plugin.contributions([])


def test_failed_declaration_preserves_root_error_and_closes_all_definitions(monkeypatch):
    from vibeflow.tooling.project import descriptor_loader
    closed = []

    class Definition:
        def __init__(self, name, fails=False):
            self.name, self.fails = name, fails

        def close(self):
            closed.append(self.name)
            if self.fails:
                raise RuntimeError("first cleanup failed")

    original = DescriptorLoadError("PLUGIN.DECLARATION.INVALID", "root failure",
                                   details={"declaration": "original"})

    def fail(*args, definitions, **kwargs):
        definitions["javascript"] = [Definition("first", True), Definition("second")]
        raise original

    monkeypatch.setattr(descriptor_loader, "_load_workflow_plugins", fail)
    with pytest.raises(DescriptorLoadError) as captured:
        load_workflow_plugins(None, None)
    assert captured.value is original
    assert closed == ["first", "second"]
    assert original.details == {"declaration": "original", "cleanup_errors": [
        {"target": "javascript", "error": "first cleanup failed"}]}
