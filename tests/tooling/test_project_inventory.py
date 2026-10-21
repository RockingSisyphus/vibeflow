import json
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


def test_root_entry_workflow_is_found_without_classifying_input_json_as_workflow(tmp_path):
    (tmp_path / "main.jsonc").write_text('{"pipeline":{"nodes":[]}}')
    (tmp_path / "input.json").write_text('{"value":3}')
    root = SimpleNamespace(id="app", path=tmp_path, architecture_documents=())
    inventory = inventory_project(SimpleNamespace(root=tmp_path, roots=(root,)))
    assert [item.path.name for item in inventory.workflows] == ["main.jsonc"]
    assert inventory.complete
