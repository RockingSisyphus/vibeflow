"""Publish portable architecture facts without any graphics dependency."""
from pathlib import Path
from datetime import datetime, timezone
import json
from .catalog import atomic_write, new_record, script_call
from ..architecture_facts import render_architecture_payload

class PreviewExportError(RuntimeError):
    def __init__(self, record, error):
        super().__init__(str(error))
        self.record = record

def workflow_identity(config, workspace, *, target="python", name=None):
    config = Path(config).resolve()
    owner = workspace.root_for_path(config)
    if owner is None:
        raise ValueError(f"workflow is not in a registered root: {config}")
    base,root_id = owner.path,owner.id
    relative = config.relative_to(base).as_posix()
    return {"root_id": root_id, "path": relative, "id": root_id + ":" + relative,
            "name": name or config.stem, "target": target}




def workflow_links(workspace):
    if workspace is None:
        return []
    from posixpath import normpath
    return [{**link, "from_root": root.id, "from_workflow": normpath(link["from_workflow"]),
             "to_workflow": normpath(link["to_workflow"])} for root in workspace.roots
            for link in root.project_config.get("preview", {}).get("workflow_links", [])]


def publish_project(root, workspace):
    """Export directory facts only; unreviewed workflows never execute here."""
    from vibeflow.tooling.project.inventory import inventory_root
    from os.path import relpath
    import os
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    roots, complete = [], True
    for owner in workspace.roots:
        found, issues = inventory_root(owner)
        complete = complete and not issues
        documents = {item.path: "" for item in found}
        documents.update({item.path: item.message for item in issues})
        workflows = []
        for path, error in sorted(documents.items()):
            item = workflow_identity(path, workspace, target=owner.project_target)
            item["source_updated_at"] = datetime.fromtimestamp(int(epoch) if epoch is not None else path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None
            if error:
                item["error"] = error
            workflows.append(item)
        roots.append({"id": owner.id, "path": Path(relpath(owner.path, workspace.root)).as_posix(),
                      "target": owner.project_target, "workflows": workflows})
    atomic_write(Path(root) / "vibeflow-preview/project.js", script_call("project", {
        "name": workspace.root.name, "roots": roots, "inventory_complete": complete}))


def publish_preview(*, root, workflow, category, status, architecture, links=(), check_status=None, target_graphs=None, workspace=None):
    root = Path(root).resolve()
    if workspace is not None:
        publish_project(root, workspace)
    record = new_record(root, workflow, category, status)
    if check_status is not None:
        record.metadata["check_status"] = check_status
    try:
        record.update("reviewing" if category=="review" else status)
        atomic_write(record.directory / "architecture.jsonc", render_architecture_payload(architecture))
        views = [{"id":"flow", "label":"流程", "renderer":"flow"}]
        views.extend({"id":key,"label":label,"renderer":"resources","kinds":kinds}
            for key,label,kinds in (("base_lib","BaseLib",["base_lib"]),
            ("plugin","Plugin",["plugin_declaration"])))
        views.append({"id":"links","label":"workflow 关联","renderer":"links"})
        declared_links = list(links) + _operation_links(architecture, workflow)
        for target in (target_graphs or {}).values():
            declared_links.extend(_operation_links(target["architecture"], target["workflow"]))
        payload = dict(version=3, id=record.metadata["id"], workflow=workflow,
                       architecture=architecture, links=declared_links, views=views, artifacts={})
        if target_graphs:
            payload["workflow_graphs"] = target_graphs
        atomic_write(record.directory / "snapshot.js", script_call("snapshot", payload))
        record.metadata["views"] = [v["id"] for v in views]
        record.update(status)
        return record
    except Exception as exc:
        record.metadata["preview_error"] = str(exc)
        record.update("failed" if category == "review" else status)
        raise PreviewExportError(record, exc) from exc


def _operation_links(architecture, workflow):
    from posixpath import normpath
    from urllib.parse import quote
    declarations = architecture.get("workflow", {}).get("workflow_targets", {})
    result = []
    for path, policy in architecture.get("call_policies", {}).items():
        for action in policy.get("actions", ()):
            target = declarations.get(action.get("target"))
            if not target or action.get("capability") != "vibeflow.workflow":
                continue
            result.append({"from_root": workflow["root_id"], "from_workflow": workflow["path"],
                "from_call_path": "/".join(quote(part, safe="'()*!") for part in json.loads(path)),
                "to_root": target.get("root") or workflow["root_id"], "to_workflow": normpath(target["workflow"]),
                "kind": "call" if action.get("operation") == "call" else "reference",
                "label": action.get("operation", "") + (" · wait" if action.get("wait") else "")})
    return result


def attach_svg(record, source):
    """Attach an explicitly requested, already rendered review file."""
    path=record.directory / "snapshot.js"
    text=path.read_text(encoding="utf-8")
    payload=json.loads(text[len("VibeFlowPreview.snapshot("):-3])
    atomic_write(record.directory / "review.svg", Path(source).read_text(encoding="utf-8"))
    payload["artifacts"]["svg"]="review.svg"
    atomic_write(path, script_call("snapshot", payload))
    record.metadata["artifacts"] = dict(payload["artifacts"])
    record.update(record.metadata["status"])
