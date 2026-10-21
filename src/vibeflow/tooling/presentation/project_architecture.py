"""Project architecture from the same inventory used by governance."""

from pathlib import Path
from os.path import relpath
from vibeflow.core.rules.models import plain
from vibeflow.tooling.presentation.architecture_facts import render_architecture_payload
from vibeflow.tooling.presentation.preview.catalog import atomic_write


from vibeflow.core.project_layout import DIRECTORY_PURPOSES, ROOT_DIRECTORY_PURPOSES


def project_architecture(inventory, *, resources=(), directory_purposes=(), root_directory_purposes=None):
    workspace = inventory.workspace
    purposes = {**DIRECTORY_PURPOSES, **{item["path"]: item["purpose"] for item in directory_purposes}}
    root_paths = {Path(relpath(root.path, workspace.root)).parts[0] for root in workspace.roots
                  if root.path != workspace.root and root.path.is_relative_to(workspace.root)}
    root_directory_purposes = root_directory_purposes or {}
    resources = plain(resources)
    for resource in resources:
        resource["path"] = (Path(resource["path"]).relative_to(workspace.root).as_posix()
            if Path(resource["path"]).is_relative_to(workspace.root) else resource["path"])
        resource["owner"]["path"] = Path(relpath(resource["owner"]["path"], workspace.root)).as_posix()
    return {"format": "vibeflow.project-architecture.v1", "purpose": workspace.purpose,
        "inventory_complete": inventory.complete,
        "directories": [{"path": name, "purpose": purposes.get(name, "Registered root container" if name in root_paths else ""),
                         "declared": name in purposes or name in root_paths}
                        for name in inventory.directories["project"]],
        "roots": [{"id": root.id, "path": Path(relpath(root.path, workspace.root)).as_posix(),
                   "purpose": root.purpose, "target": root.project_target,
                   "directories": [{"path": name, "purpose": {**ROOT_DIRECTORY_PURPOSES,
                       **{item["path"]: item["purpose"] for item in root_directory_purposes.get(root.id, ())}}.get(name, "")}
                       for name in inventory.directories["roots"][root.id]],
                   "workflows": [item.path.relative_to(root.path).as_posix() for item in inventory.for_root(root.id)]}
                  for root in workspace.roots],
        "resources": plain(resources),
        "diagnostics": [{"root": item.root_id, "path": Path(relpath(item.path, workspace.root)).as_posix(),
                         "code": item.code, "message": item.message} for item in inventory.issues]}


def write_project_architecture(inventory, **facts):
    path = inventory.workspace.root / "PROJECT_ARCHITECTURE.jsonc"
    atomic_write(path, render_architecture_payload(project_architecture(inventory, **facts)))
    return path
