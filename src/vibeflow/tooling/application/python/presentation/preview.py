"""Publish the Python command's already prepared architecture facts."""
from pathlib import Path
from vibeflow.tooling.presentation.preview.exporter import publish_preview, workflow_identity, workflow_links
from vibeflow.tooling.application.presentation_targets import preview_workspace
from vibeflow.tooling.presentation.viewer import install_for_record

def python_preview(prepared, *, config, workspace=None, preview_root=None, category="review", status="passed", check_status=None):
    workspace = preview_workspace(config, workspace)
    root = Path(preview_root or (workspace.root if workspace else Path(config).resolve().parent))
    from vibeflow.tooling.application.presentation_targets import prepare_targets
    architecture, targets = prepare_targets(prepared.architecture(), config=config, workspace=workspace, load_own_target=_load_own_target)
    record = publish_preview(root=root, workflow=workflow_identity(config, workspace), category=category,
        status=status, architecture=architecture, links=workflow_links(workspace), check_status=check_status, target_graphs=targets)
    install_for_record(record)
    return record


def _load_own_target(path, workspace):
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
    result = load_workspace_graph_for_export(path, workspace=workspace, validate_health=True, _include_presentation=True)
    if result[4] is not None or result[6] is None:
        raise ValueError("target facts unavailable: " + str(result[4].to_dict() if result[4] else result[5].to_dict()))
    return result[6].architecture()
