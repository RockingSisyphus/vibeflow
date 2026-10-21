"""Project metadata errors at command boundaries, independent of either Target."""
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.workspace_loader import load_project_workspace, load_workspace_config


def workspace_or_report(path, *, registered_source=False):
    try:
        return load_project_workspace(path) if registered_source else load_workspace_config(path)
    except WorkspaceConfigError as error:
        return HealthReport(status="ERROR", errors=(HealthFinding(rule_id=error.rule_id,
            severity="error", object_type="workspace", object_id=str(path),
            source_location=dict(error.source_location), failure_layer=error.failure_layer,
            message=error.message, suggested_fix_type="fix_config"),))
