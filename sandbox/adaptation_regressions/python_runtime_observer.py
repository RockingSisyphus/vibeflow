"""Private instrumentation around unchanged formal Python CLI entry points."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def counted(arguments):
    from sandbox.python.review_performance.counters import Observations
    from vibeflow.tooling.application.cli import main
    from vibeflow.targets.python.runtime.engine import PipelineRuntime
    stdout, stderr = StringIO(), StringIO()
    error = None
    runtime = []
    original = PipelineRuntime.run
    def run(instance, *args, **kwargs):
        result = original(instance, *args, **kwargs)
        value = result.get("result")
        runtime.append({"providers":dict(instance.compiled.providers),
                        "result":value["value"] if value is not None else None})
        return result
    with Observations() as observation, patch.object(PipelineRuntime,"run",run), redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = main(arguments)
        except Exception as exc:
            code, error = 2, repr(exc)
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError:
        payload = None
    return {"exit_code":code, "error":error, "payload":payload,
            "stdout":stdout.getvalue(), "stderr":stderr.getvalue(), "runtime":runtime, **observation.to_dict()}


def source_query():
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.project.config_loader import load_config_document
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry, collect_workflow_source_context
    from vibeflow.targets.python.project.check_session import begin_python_check, current_python_check, end_python_check
    from vibeflow.targets.python.project.compiler import GraphCompiler
    from vibeflow.tooling.project.graph_config import parse_graph_config
    root = Path.cwd()
    workspace = load_workspace_config(root / "vibeflow_config.jsonc")
    registry = declared_python_registry(workspace, root / "workflow.jsonc")
    data = load_config_document(root / "workflow.jsonc").data
    graph = parse_graph_config(data, project_root=root, source_path=root / "workflow.jsonc")
    begin_python_check(registry)
    try:
        original = collect_workflow_source_context(registry, graph)
        states = dict(registry.source_load_states)
        queried = registry.source_context_loader("audit.b")
        after_query = {"snapshot_unchanged":registry.source_context_snapshot is original,
            "session_unchanged":current_python_check(registry).sources is original,
            "states_unchanged":dict(registry.source_load_states) == states,
            "query_types":[item.type_key for item in queried.nodes]}
        # Start the compile check from a freshly published actual workflow scope;
        # a failed query check must not conceal an independent compile failure.
        original = collect_workflow_source_context(registry, graph)
        states = dict(registry.source_load_states)
        GraphCompiler().compile(graph, registry=registry)
        after_compile = {"snapshot_unchanged":registry.source_context_snapshot is original,
            "session_unchanged":current_python_check(registry).sources is original,
            "states_unchanged":dict(registry.source_load_states) == states}
        error = None
        try:
            registry.get("audit.a")
        except Exception as exc:
            error = {"message":str(exc), "findings":[item.to_dict() for item in getattr(exc,"findings",())]}
        return {"query":after_query, "compile":after_compile, "binding_error":error,
            "actual_calls":[[item.owner,item.node_id,item.type_key] for item in original.calls],
            "a_imported":(root / "a.imported").exists(), "b_imported":(root / "b.imported").exists(),
            "business_ran":(root / "a.ran").exists(),
            "a_state_after_binding":registry.source_load_states.get(str(root / "a.py"))}
    finally:
        end_python_check(registry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("count", "source-query"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    print(json.dumps(counted(arguments) if args.mode == "count" else source_query(), indent=2))
