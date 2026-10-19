"""Publish a JavaScript command's architecture facts without rendering graphics."""
from vibeflow.tooling.presentation.preview.exporter import publish_preview, workflow_identity, workflow_links
from vibeflow.tooling.presentation.viewer import install_for_record

def javascript_preview(result, *, preview_root=None, category="review", status="passed"):
    root=preview_root or result.workspace.root
    record=publish_preview(root=root, workflow=workflow_identity(result.config_path,result.workspace,target="javascript"),
        category=category,status=status,architecture=result.architecture,links=workflow_links(result.workspace),
        check_status="CONCERNS" if getattr(result,"warnings",()) else "PASS")
    install_for_record(record)
    return record
