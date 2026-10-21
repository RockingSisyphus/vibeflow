"""Direct SDK objects and locator assertions describe one implementation."""

import json
import pytest

from vibeflow.tooling.project.resources import ResourcePreparationError, prepare_workflow_resources
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def project(tmp_path, options="", suffix=""):
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
    (tmp_path / "nodes").mkdir()
    (tmp_path / "nodes/steps.py").write_text(
        'from vibeflow.targets.python.sdk import node\n'
        f'@node(id="actual",node_type="vibeflow.node",flow_kind="terminal",contract={{}},rulesets=[]{options})\n'
        'class Actual:\n'
        '    implementation = "ordinary business attribute"\n'
        '    def run_pure(self,inputs,params):\n'
        '        return {}\n' + suffix + '\n')
    config = tmp_path / "workflow.jsonc"
    config.write_text(json.dumps({"rulesets":[],"pipeline":{"nodes":[{"id":"actual","definition_id":"actual","display_name":"Actual","description":"Identity fixture"}],"edges":[]}}))
    return load_workspace_config(tmp_path.parent / "vibeflow_config.jsonc"), config


@pytest.mark.parametrize("kind,reference,export", [("file","./nodes/steps.py","Actual"),
    ("module","nodes.steps","Actual"), ("file","nodes/steps.py","Alias")])
def test_same_source_metadata_and_loaded_alias_use_actual_symbol(tmp_path, kind, reference, export):
    source = {"language":"python", "targets":["python"], "completion":"immediate",
              "source":{"kind":kind,"ref":reference,"export":export},
              "implementation_files":[{"kind":"file","ref":str(tmp_path / "support.py")}]}
    (tmp_path / "support.py").write_text('def helper():\n    return 1\n')
    workspace, config = project(tmp_path, ',implementations='+repr([source]), 'Alias = Actual\n')
    loaded = prepare_workflow_resources(workspace, config)
    implementation = loaded.catalogs.nodes.require("actual").implementations[0]
    assert implementation.source.ref == str(tmp_path / "nodes/steps.py")
    assert implementation.source.export == "Actual"
    assert implementation.completion == "immediate"
    assert implementation.implementation_files[0].ref == str(tmp_path / "support.py")
    actual = loaded.resource_bindings[("node", "actual")]
    assert actual.implementation == "ordinary business attribute"


def test_different_source_reports_both_positions_without_importing_it(tmp_path):
    marker = tmp_path / "wrong-imported"
    (tmp_path / "wrong.py").write_text(f'open({str(marker)!r},"w").write("loaded")\nclass Wrong: pass\n')
    source = {"language":"python", "targets":["python"],
              "source":{"kind":"file","ref":"wrong.py","export":"Wrong"}}
    workspace, config = project(tmp_path, ',implementations='+repr([source]))
    with pytest.raises(ResourcePreparationError) as captured:
        prepare_workflow_resources(workspace, config)
    error = captured.value
    assert error.code == "RESOURCE.IMPLEMENTATION.CONFLICT"
    assert error.details["actual"]["path"] == str(tmp_path / "nodes/steps.py")
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
    from vibeflow.tooling.project.resources import prepare as resource_preparation
    closed = []

    class Definition:
        def __init__(self, name, fails=False):
            self.name, self.fails = name, fails

        def close(self):
            closed.append(self.name)
            if self.fails:
                raise RuntimeError("first cleanup failed")

    original = ResourcePreparationError("PLUGIN.DECLARATION.INVALID", "root failure",
                                   details={"declaration": "original"})

    def fail(*args, definitions, **kwargs):
        definitions["javascript"] = [Definition("first", True), Definition("second")]
        raise original

    monkeypatch.setattr(resource_preparation, "_prepare_workflow_resources", fail)
    with pytest.raises(ResourcePreparationError) as captured:
        prepare_workflow_resources(None, None)
    assert captured.value is original
    assert closed == ["first", "second"]
    assert original.details == {"declaration": "original", "cleanup_errors": [
        {"target": "javascript", "error": "first cleanup failed"}]}
