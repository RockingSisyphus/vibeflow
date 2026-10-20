"""Connect a checked Python source or AOT invocation to a neutral host protocol."""
import json
from pathlib import Path

def run_python(args):
    from vibeflow.coordination.host import run_host
    from vibeflow.targets.python.runtime.lifecycle import CancellationSignal
    signal = CancellationSignal()
    initial = json.loads(Path(args.input).read_text()) if args.input else {}
    if args.bundle:
        from vibeflow.tooling.application.python.bundle import load_bundle
        bundle = load_bundle(args.bundle)
        workflow = bundle.workflow.workflow_id
    else:
        bundle = None
        workflow = str(Path(args.config).resolve())

    def execute(client):
        options = dict(initial={**initial, **client.inputs},
            entry=client.entry if client.entry is not None else args.entry,
            capabilities={"vibeflow.workflow": client.operations()}, run_root=args.run_root, signal=signal)
        if bundle is not None:
            result = bundle.run(**options)
        elif args.workspace:
            from vibeflow.tooling.project.workspace_loader import load_workspace_config
            from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
            result = run_workspace_checked(args.config, workspace=load_workspace_config(args.workspace),
                preview_root=args.preview_root, **options)
        else:
            from vibeflow.tooling.application.python.runner import run_checked
            from vibeflow.tooling.application.python.project.declarations import default_python_registry
            result = run_checked(args.config, registry=default_python_registry(), preview_root=args.preview_root, **options)
        return result.public_outputs

    return run_host(execute, workflow=workflow, stop=signal.request_stop, url=args.url, identifier=args.id)
