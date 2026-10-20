"""Explicit communication service and standard Python host commands."""
import argparse
import json
import os
from pathlib import Path
from threading import Event


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibeflow coordination")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="serve local JSON mailboxes; hosts own cleanup")
    serve.add_argument("--config", required=True, help="JSON/JSONC file containing workflow_targets")
    serve.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("run-python", help="connect one checked source or prepared AOT instance")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle")
    source.add_argument("--config")
    run.add_argument("--workspace")
    run.add_argument("--input")
    run.add_argument("--entry")
    run.add_argument("--url", default=os.environ.get("VIBEFLOW_COORDINATION_URL"))
    run.add_argument("--id", default=os.environ.get("VIBEFLOW_INSTANCE_ID"))
    run.add_argument("--run-root")
    run.add_argument("--preview-root")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args)
        if not args.url:
            parser.error("--url or VIBEFLOW_COORDINATION_URL is required; start the service explicitly")
        from vibeflow.tooling.application.python.coordination import run_python
        outputs = run_python(args)
        print(json.dumps({"outputs": outputs}, ensure_ascii=False), flush=True)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(json.dumps({"error": str(error), "code": getattr(error, "code", type(error).__name__)}, ensure_ascii=False), flush=True)
        return 1


def _serve(args):
    from vibeflow.core.workflows.targets import parse_targets
    from vibeflow.coordination import WorkflowServer
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    path = Path(args.config).resolve()
    document = load_raw_config_document(path)
    targets = {name: {**value.to_dict(), "cwd": str((path.parent / value.cwd).resolve())}
               for name, value in parse_targets(document.data.get("workflow_targets", {})).items()}
    with WorkflowServer(targets=targets, port=args.port) as server:
        print(json.dumps({"url": server.url, "targets": list(targets)}, ensure_ascii=False), flush=True)
        Event().wait()
    return 0

