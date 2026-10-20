"""Publish checked JavaScript facts for review and build operations."""
from vibeflow.tooling.presentation.preview.exporter import publish_preview, workflow_identity, workflow_links
from vibeflow.tooling.presentation.viewer import install_for_record
from .architecture import build_prepared_architecture


def _publish(result, architecture, *, preview_root, category, status):
    from vibeflow.tooling.presentation.preview.targets import prepare_targets
    architecture, targets = prepare_targets(architecture, config=result.config_path, workspace=result.workspace, load_own_target=_load_own_target)
    record=publish_preview(root=preview_root or result.workspace.root,
        workflow=workflow_identity(result.config_path,result.workspace,target="javascript"),
        category=category,status=status,architecture=architecture,links=workflow_links(result.workspace),
        check_status="CONCERNS" if result.warnings else "PASS", target_graphs=targets)
    install_for_record(record)
    return record


def javascript_preview(result, *, preview_root=None, category="review", status="passed"):
    return _publish(result,result.architecture,preview_root=preview_root,category=category,status=status)


def publish_build_preview(prepared, *, preview_root=None, status="building"):
    return _publish(prepared,build_prepared_architecture(prepared),preview_root=preview_root,category="build",status=status)


def _load_own_target(path, workspace):
    from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
    return audit_javascript_project(JavascriptAuditRequest(workspace=workspace, config=path)).architecture
