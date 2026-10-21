import json
import pytest
from types import SimpleNamespace

from vibeflow.tooling.project.inventory import inventory_project


def test_inventory_reports_broken_candidates_without_losing_other_roots(tmp_path):
    roots = []
    for identifier in ("desktop", "backend"):
        directory = tmp_path / identifier / "configs"
        directory.mkdir(parents=True)
        (directory / "workflow.json").write_text(json.dumps({"pipeline": {"nodes": []}}))
        (directory / "definition.jsonc").write_text('{"type_key":"part","pipeline":{}}')
        roots.append(SimpleNamespace(id=identifier, path=directory.parent, architecture_documents=()))
    broken = roots[0].path / "configs" / "broken.jsonc"
    broken.write_text('{"pipeline":')
    inventory = inventory_project(SimpleNamespace(root=tmp_path, roots=tuple(roots)))
    assert [item.root_id for item in inventory.workflows] == ["desktop", "backend"]
    assert len(inventory.issues) == 1
    assert inventory.issues[0].path == broken
    assert inventory.issues[0].code == "CONFIG.JSON"
    assert not inventory.complete


def test_registered_workflow_outside_configs_is_discovered_once(tmp_path):
    path = tmp_path / "entry.jsonc"
    path.write_text('{"pipeline":{}}')
    root = SimpleNamespace(id="app", path=tmp_path,
                           architecture_documents=(SimpleNamespace(workflow_path=path, document_path=tmp_path / "ARCHITECTURE.jsonc"),))
    inventory = inventory_project(SimpleNamespace(root=tmp_path, roots=(root,)))
    assert [item.path for item in inventory.for_root("app")] == [path]
    assert inventory.complete


@pytest.mark.parametrize("content", ['{"value":3}', '{"metadata":{"pipeline":{}}}', '[{"pipeline":42}]'])
def test_root_entry_workflow_is_found_without_classifying_input_json_as_workflow(tmp_path, content):
    (tmp_path / "main.jsonc").write_text('{"pipeline":{"nodes":[]}}')
    (tmp_path / "input.json").write_text(content)
    root = SimpleNamespace(id="app", path=tmp_path, architecture_documents=())
    inventory = inventory_project(SimpleNamespace(root=tmp_path, roots=(root,)))
    assert [item.path.name for item in inventory.workflows] == ["main.jsonc"]
    assert inventory.complete


@pytest.mark.parametrize("location", ["main.jsonc", "configs/main.jsonc", "entries/main.jsonc"])
@pytest.mark.parametrize("content", ['{"pipeline":', '{"pipeline":42}', '{"pipeline":{"nodes":[]}}'])
def test_workflow_intent_is_checked_at_all_supported_locations(tmp_path, location, content):
    from tests.tooling.test_project_preparation import project
    from vibeflow.tooling.project.preparation import ProjectPreparation
    workspace = project(tmp_path, ["desktop", "backend"])
    root = workspace.roots[0].path
    path = root / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    valid = content.endswith('[]}}')
    if valid:
        path.write_text((root / "configs/workflow.jsonc").read_text())
    (root / "input.json").write_text('{"value":3}')
    if location.startswith("entries"):
        (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python",
            "architecture":{"documents":[{"workflow":location,"document":"ARCHITECTURE.jsonc"}]}}))
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        workspace = load_workspace_config(workspace.path)
    review = ProjectPreparation(workspace).review(write_architecture=True)
    assert review.inventory.complete == valid
    assert bool([item for item in review.inventory.issues if item.path == path]) != valid
    assert len(review.inventory.for_root("backend")) == 1
    document = json.loads("\n".join(review.architecture_path.read_text().splitlines()[2:]))
    assert document["inventory_complete"] == valid


@pytest.mark.parametrize("content", [
    '{"type_key":"mistaken","pipeline":42}',
    '{"type_key":"mistaken","pipeline":{}}',
])
def test_registered_nodeset_cannot_disappear_from_quality_check(tmp_path, capsys, content):
    from tests.tooling.test_project_dependency_scope import project, write
    from vibeflow.tooling.application.cli import main
    project(tmp_path, "python")
    path = tmp_path / "app/entry.jsonc"
    write(path, content)
    write(tmp_path / "app/vibeflow_project.jsonc", {"project_target":"python",
        "architecture":{"documents":[{"workflow":"entry.jsonc","document":"ARCHITECTURE.jsonc"}]}})
    assert main(["quality-check", "--path", str(tmp_path), "--json"]) != 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] != "PASS"
    assert any(item["rule_id"] == "PROJECT.INVENTORY.DOCUMENT" for item in report["errors"])
