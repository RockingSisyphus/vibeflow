"""Checked source entry; project preparation and execution have one owner."""
from pathlib import Path
from vibeflow.tooling.application.python.run_observation import observed_checked_run


@observed_checked_run
def run_checked(config_path, *, initial=None, run_root=None, run_id=None,
                runtime_options=None, capabilities=None, workflow_instance_id=None, delegate_cli=False,
                _prepared_run_dir=None, preview_root=None, entry=None, signal=None):
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    path = Path(config_path).resolve()
    return run_workspace_checked(path, workspace=load_project_workspace(path),
        initial=initial, run_root=run_root, run_id=run_id, runtime_options=runtime_options,
        capabilities=capabilities, workflow_instance_id=workflow_instance_id,
        delegate_cli=delegate_cli, _prepared_run_dir=_prepared_run_dir,
        preview_root=preview_root, entry=entry, signal=signal)
