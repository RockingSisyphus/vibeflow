"""Bounded validation of an existing workspace without running its business Nodes."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, required=True, help="source directory or released kernel ZIP")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output = report_path.with_suffix(".stdout.json")
    error = report_path.with_suffix(".stderr.txt")
    workspace = args.workspace.resolve()
    command = [sys.executable, "-B", "-m", "vibeflow", "validate", "--workspace", str(workspace),
               "--config", str(args.config.resolve()), "--json"]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                   "PYTHONPATH": os.pathsep.join((str(args.kernel.resolve()), str(workspace.parent)))}
    started = perf_counter()
    result = {"schema": "vibeflow.readonly-project-validation.v1", "command": command,
              "kernel": str(args.kernel.resolve()), "stdout": str(output), "stderr": str(error)}
    try:
        with output.open("w") as stdout, error.open("w") as stderr:
            process = subprocess.run(command, cwd=report_path.parent, env=environment,
                                     stdout=stdout, stderr=stderr, timeout=args.timeout)
        result["exit_code"] = process.returncode
        payload = json.loads(output.read_text())
        result.update(completed=True, status=payload.get("status"),
                      errors=len(payload.get("errors", [])), warnings=len(payload.get("warnings", [])),
                      error_codes=dict(Counter(item["code"] for item in payload.get("errors", []))),
                      warning_codes=dict(Counter(item["code"] for item in payload.get("warnings", []))))
    except subprocess.TimeoutExpired:
        result.update(completed=False, timed_out=True)
    except (OSError, ValueError) as exc:
        result.update(completed=False, observation_error=str(exc))
    result["seconds"] = perf_counter() - started
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # A health failure is still a completed observation; preserve its actual
    # CLI exit and status above instead of calling this a project PASS.
    return 0 if result["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
