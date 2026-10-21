import json

import pytest

from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.workspace_loader import load_project_workspace, load_workspace_config


def project(tmp_path, paths):
    for value in paths:
        root = (tmp_path / value).resolve()
        root.mkdir(parents=True, exist_ok=True)
        (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    config = tmp_path / "vibeflow_config.jsonc"
    config.write_text(json.dumps({"roots": [{"id": f"root{index}", "path": value}
                                            for index, value in enumerate(paths)]}))
    return config


def test_loads_actual_containing_project_instead_of_synthesizing_root(tmp_path):
    config = project(tmp_path, ["桌面 app", "backend"])
    workspace = load_project_workspace(tmp_path / "backend" / "vibeflow_project.jsonc")
    assert workspace.path == config
    assert [root.id for root in workspace.roots] == ["root0", "root1"]
    assert workspace.root_for_path(tmp_path / "backend" / "workflow.jsonc").id == "root1"


@pytest.mark.parametrize("paths,code", [
    ([], "WORKSPACE.ROOTS"),
    (["."], "WORKSPACE.ROOT.SEPARATE_DIRECTORY"),
    (["../outside"], "WORKSPACE.ROOT.SEPARATE_DIRECTORY"),
    (["app", "app/child"], "WORKSPACE.ROOT.OVERLAP"),
])
def test_rejects_ambiguous_or_missing_root_ownership(tmp_path, paths, code):
    config = project(tmp_path, paths)
    if not paths:
        with pytest.raises(WorkspaceConfigError) as error:
            load_workspace_config(config)
        assert error.value.rule_id == code
        return
    from vibeflow.tooling.project.preparation import ProjectPreparation
    workspace = load_workspace_config(config)
    assert code in {item.rule_id for item in ProjectPreparation(workspace).review().findings}
    (tmp_path / "project_rules.jsonc").write_text('{"rulesets":[]}')
    assert code not in {item.rule_id for item in ProjectPreparation(workspace).review().findings}


def test_standalone_and_unregistered_roots_are_not_accepted(tmp_path):
    root = tmp_path / "standalone"
    root.mkdir()
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    with pytest.raises(WorkspaceConfigError, match="standalone roots|registered root"):
        load_project_workspace(root)
    project(tmp_path, ["app"])
    with pytest.raises(WorkspaceConfigError, match="registered root"):
        load_project_workspace(root)
