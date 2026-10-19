"""Publish the Python command's already prepared architecture facts."""
from pathlib import Path
from vibeflow.tooling.presentation.preview.exporter import publish_preview, workflow_identity, workflow_links, preview_workspace
from vibeflow.tooling.presentation.viewer import install_for_record

def python_preview(prepared, *, config, workspace=None, preview_root=None, category="review", status="passed", check_status=None):
    workspace = preview_workspace(config, workspace)
    root = Path(preview_root or (workspace.root if workspace else Path(config).resolve().parent))
    record = publish_preview(root=root, workflow=workflow_identity(config, workspace), category=category,
        status=status, architecture=prepared.architecture(), links=workflow_links(workspace), check_status=check_status)
    install_for_record(record)
    return record
