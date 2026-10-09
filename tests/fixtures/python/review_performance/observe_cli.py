"""Run one formal CLI with counters; write observations after it finishes."""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
from time import perf_counter

from tests.fixtures.python.review_performance.counters import Observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preload", help="Sandbox-only: bind this selected Node before the CLI")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    args.report.parent.mkdir(parents=True, exist_ok=True)
    from vibeflow.tooling.application.cli import main as cli_main
    if args.preload:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        from vibeflow.tooling.application.python.project.declarations import declared_python_registry
        workspace = load_workspace_config(arguments[arguments.index('--workspace') + 1])
        config = Path(arguments[arguments.index('--config') + 1])
        declared_python_registry(workspace, config).get(args.preload)
    started = perf_counter()
    failure = None
    with Observations() as observations:
        with args.report.with_suffix(".stdout.txt").open("w") as stdout:
            with args.report.with_suffix(".stderr.txt").open("w") as stderr:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    try:
                        code = cli_main(arguments)
                    except Exception as error:
                        failure = repr(error)
                        code = 2
    report = {"schema":"vibeflow.review-performance.cli.v1", "arguments":arguments,
              "exit_code":code,"error":failure,"seconds":perf_counter()-started,
              **observations.to_dict()}
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    if observations.mermaid:
        (args.report.parent/'graph.mmd').write_text('\n'.join(observations.mermaid)+'\n')
    print(json.dumps({"exit_code":code,"report":str(args.report),"seconds":report["seconds"]}))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
