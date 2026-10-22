"""Publish portable architecture facts without any graphics dependency."""
from pathlib import Path
from datetime import datetime, timezone
import json
from .catalog import new_record, script_call
from vibeflow.tooling.architecture.documents import render_architecture_payload
from vibeflow.tooling.file_io import atomic_write

class PreviewExportError(RuntimeError):
    def __init__(self, record, error):
        super().__init__(str(error))
        self.record = record

from vibeflow.tooling.architecture.project import workflow_identity


def workflow_links(workspace):
    if workspace is None:
        return []
    from posixpath import normpath
    return [{**link, "from_root": root.id, "from_workflow": normpath(link["from_workflow"]),
             "to_workflow": normpath(link["to_workflow"])} for root in workspace.roots
            for link in root.project_config.get("preview", {}).get("workflow_links", [])]


def publish_project(root, workspace):
    """Export directory facts only; unreviewed workflows never execute here."""
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    from .catalog import utc_now
    path = workspace.root / "PROJECT_ARCHITECTURE.jsonc"
    from copy import deepcopy
    import os
    epoch=os.environ.get("SOURCE_DATE_EPOCH")
    payload={"version":4, "name":workspace.root.name,
        "updated_at":datetime.fromtimestamp(int(epoch), timezone.utc).isoformat() if epoch is not None else utc_now()}
    try:
        architecture = load_raw_config_document(path).data
        if architecture.get("format") != "vibeflow.project-architecture.v2":
            raise ValueError("旧版项目架构格式")
        roots=deepcopy(architecture["roots"])
        for owner in roots:
            for item in owner["workflows"]:
                source=workspace.root/item["project_path"]
                item["source_updated_at"]=datetime.fromtimestamp(int(epoch) if epoch is not None else source.stat().st_mtime, timezone.utc).isoformat() if source.is_file() else None
        payload.update(architecture=architecture, roots=roots, inventory_complete=architecture["inventory_complete"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        payload.update(roots=[], inventory_complete=False,
            error=f"无法使用 PROJECT_ARCHITECTURE.jsonc：{error}；运行 preview --workspace 重新生成。")
    atomic_write(Path(root) / "vibeflow-preview/project.js", script_call("project", payload))


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
            if target.get("architecture"):
                declared_links.extend(_operation_links(target["architecture"], target["workflow"]))
        payload = dict(version=4, id=record.metadata["id"], workflow=workflow,
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
    from vibeflow.tooling.architecture.relations import workflow_relations
    return workflow_relations(architecture, workflow)


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
