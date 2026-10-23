"""Connect a checked Python source or AOT invocation to a neutral host protocol."""
import json
from pathlib import Path

async def run_python(args):
    from vibeflow.coordination.host import run_host
    from vibeflow.targets.python.runtime.lifecycle import CancellationSignal
    signal = CancellationSignal()
    initial = json.loads(Path(args.input).read_text(encoding="utf-8")) if args.input else {}
    if args.bundle:
        from vibeflow.tooling.application.python.bundle import load_bundle
        bundle = load_bundle(args.bundle)
        workflow = bundle.data["workflow_reference"]
    else:
        bundle = None
        from vibeflow.tooling.project.workspace_loader import load_workspace_config, load_project_workspace
        workspace = load_workspace_config(Path(args.workspace)) if args.workspace else load_project_workspace(Path(args.config))
        root = workspace.root_for_path(Path(args.config))
        workflow = {"root":root.id, "path":Path(args.config).resolve().relative_to(root.path).as_posix()}

    async def execute(client):
        options = dict(initial={**initial, **client.inputs},
            entry=client.entry if client.entry is not None else args.entry,
            capabilities={"vibeflow.workflow": client.operations()}, run_root=args.run_root, signal=signal)
        options["workflow_instance_id"] = client.id
        if bundle is not None:
            result = await bundle.run_async(**options) if bundle.workflow.entry_mode == 'async' else bundle.run(**options)
        elif args.workspace:
            from vibeflow.tooling.project.workspace_loader import load_workspace_config
            from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
            workspace=load_workspace_config(args.workspace)
            from vibeflow.tooling.project.config_loader import load_workspace_config_document
            if load_workspace_config_document(Path(args.config),workspace=workspace).data.get('pipeline',{}).get('entry_mode','sync') == 'async':
                from vibeflow.tooling.application.python.async_workspace import run_workspace_checked_async
                result = await run_workspace_checked_async(args.config,workspace=workspace,preview_root=args.preview_root,**options)
            else:
                result = run_workspace_checked(args.config,workspace=workspace,preview_root=args.preview_root,**options)
        else:
            from vibeflow.tooling.application.python.runner import run_checked
            from vibeflow.tooling.project.config_loader import load_config_document
            if load_config_document(Path(args.config)).data.get('pipeline',{}).get('entry_mode','sync') == 'async':
                from vibeflow.tooling.application.python.runner import run_checked_async
                result=await run_checked_async(args.config,preview_root=args.preview_root,**options)
            else:result=run_checked(args.config,preview_root=args.preview_root,**options)
        return result.public_outputs

    return await run_host(execute, workflow=workflow, stop=signal.request_stop, url=args.url, identifier=args.id)
