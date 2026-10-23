"""Explicit top-level CLI dispatch owns event-loop creation."""
import asyncio
from vibeflow.tooling.project.config_loader import load_workspace_config_document


def dispatch_workspace(config_path, *, workspace, **options):
    document=load_workspace_config_document(config_path,workspace=workspace)
    if document.data.get('pipeline',{}).get('entry_mode','sync')=='async':
        from ..async_workspace import run_workspace_checked_async
        return asyncio.run(run_workspace_checked_async(config_path,workspace=workspace,**options))
    from ..workspace_service import run_workspace_checked
    return run_workspace_checked(config_path,workspace=workspace,**options)
