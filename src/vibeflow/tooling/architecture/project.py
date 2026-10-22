"""Deterministic project index from the operation's existing inventory."""
from pathlib import Path
from os.path import relpath
from vibeflow.core.rules.models import plain
from vibeflow.core.project_layout import DIRECTORY_PURPOSES, ROOT_DIRECTORY_PURPOSES
from vibeflow.core.graph_calls import graph_call_subjects
from vibeflow.core.workflows.references import node_workflow_actions, action_references, workflow_node_params
from .documents import render_architecture_payload
from vibeflow.tooling.file_io import atomic_write


def workflow_identity(config, workspace, *, target="python", name=None):
    config = Path(config).resolve()
    owner = workspace.root_for_path(config)
    if owner is None:
        raise ValueError(f"workflow is not in a registered root: {config}")
    path = config.relative_to(owner.path).as_posix()
    return {"root_id": owner.id, "path": path, "id": owner.id + ":" + path,
            "name": name or config.stem, "target": target}


def project_architecture(inventory, *, resources=(), directory_purposes=(), root_directory_purposes=None, workflows=None):
    workspace = inventory.workspace
    purposes = {**DIRECTORY_PURPOSES, **{row["path"]: row["purpose"] for row in directory_purposes}}
    root_purposes = root_directory_purposes or {}
    relative = lambda path: Path(relpath(path, workspace.root)).as_posix()
    def directory_role(name):
        contained = [root.id for root in workspace.roots if relative(root.path) == name or relative(root.path).startswith(name + "/")]
        exact = any(relative(root.path) == name for root in workspace.roots)
        return {"role":"root" if exact else "root_container" if contained else "directory", "root_ids":contained}
    def root_purpose(name):
        exact=next((root for root in workspace.roots if relative(root.path)==name), None)
        return (exact.purpose or "Registered workflow root") if exact else "Registered root container" if directory_role(name)["root_ids"] else ""
    directories = []
    for entry in inventory.entries["project"]:
        if entry["kind"] != "directory":
            continue
        name=entry["path"]
        contained = [root.id for root in workspace.roots if relative(root.path) == name or relative(root.path).startswith(name + "/")]
        directories.append({"path": name, "purpose": purposes.get(name, root_purpose(name)),
            "declared": name in purposes or bool(contained), **directory_role(name)})
    roots = []
    for root in workspace.roots:
        specs = {spec.workflow_path.resolve(): spec for spec in root.architecture_documents}
        found = {item.path: item for item in inventory.for_root(root.id)}
        errors = {issue.path: issue for issue in inventory.issues if issue.root_id == root.id}
        rows = []
        for path in sorted(found.keys() | {path for path in errors if path.suffix in {".json", ".jsonc"}}):
            document = found.get(path)
            data = document.data if document else {}
            pipeline = data.get("pipeline", {})
            item = workflow_identity(path, workspace, target=root.project_target,
                name=data.get("display_name") or data.get("name") or path.stem)
            spec = specs.get(path.resolve())
            item.update(description=data.get("description", ""), project_path=relative(path), exists=path.is_file(),
                entries=plain(pipeline.get("entries", {})), default_entry=pipeline.get("default_entry", ""),
                architecture=relative(spec.document_path) if spec else None,
                architecture_exists=spec.document_path.is_file() if spec else False, relations=[])
            if path in errors:
                item["error"] = errors[path].message
            prepared = (workflows or {}).get(path.resolve())
            if prepared:
                for subject in graph_call_subjects(prepared.graph, global_config=data.get("global_config", {})):
                    for node in subject.graph.nodes:
                        descriptor = prepared.catalogs.nodes.get(node.definition_id)
                        ops = [operation for req in getattr(descriptor, "capabilities", ()) if req.id == "vibeflow.workflow" for operation in req.operations]
                        if not ops:
                            continue
                        try:
                            params = workflow_node_params(node, descriptor, subject)
                            actions = node_workflow_actions([{"capability":"vibeflow.workflow", "operation":op} for op in ops], params, root=root.id)
                            for action in actions:
                                for ref in action_references(action):
                                    item["relations"].append({"call_path": list((*subject.call_path, node.id)), "operation":action["operation"],
                                        "workflow":ref, "expected":action["operation"] in {"send", "receive"}})
                        except ValueError as error:
                            item.setdefault("diagnostics", []).append({"call_path":list((*subject.call_path,node.id)), "message":str(error)})
            rows.append(item)
        mapping = {**ROOT_DIRECTORY_PURPOSES, **{row["path"]:row["purpose"] for row in root_purposes.get(root.id, ())}}
        roots.append({"id": root.id, "path": relative(root.path), "role":"root", "purpose":root.purpose,
            "target":root.project_target,
            "directories":[{"path":name, "project_path":relative(root.path/name), "purpose":mapping.get(name, root_purpose(relative(root.path/name))),
                            **directory_role(relative(root.path/name))}
                           for name in (entry["path"] for entry in inventory.entries["roots"][root.id] if entry["kind"]=="directory")], "workflows":rows})
    resources = plain(resources)
    for resource in resources:
        resource["path"] = relative(resource["path"])
        resource["owner"]["path"] = relative(resource["owner"]["path"])
    from vibeflow.tooling.presentation.portable_paths import portable_paths
    resources=portable_paths(resources, roots={"@project":workspace.root}, primary_root=workspace.root)
    return {"format":"vibeflow.project-architecture.v2", "purpose":workspace.purpose,
        "inventory_complete":inventory.complete, "directories":directories, "roots":roots, "resources":resources,
        "diagnostics":[{"root":issue.root_id,"path":relative(issue.path),"code":issue.code,"message":issue.message} for issue in inventory.issues]}


def write_project_architecture(inventory, **facts):
    path = inventory.workspace.root / "PROJECT_ARCHITECTURE.jsonc"
    atomic_write(path, render_architecture_payload(project_architecture(inventory, **facts)))
    return path
