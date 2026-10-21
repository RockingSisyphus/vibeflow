"""Exercise default values through isolated, real Python CLI workflows."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


REPOSITORY = Path(__file__).resolve().parents[4]
CASES = (
    ("empty_array", "array", []),
    ("array", "array", ["a"]),
    ("empty_object", "object", {}),
    ("object", "object", {"a": 1}),
    ("nested_array", "array", [{"a": [1, {"b": []}]}]),
    ("nested_object", "object", {"a": [{"b": []}]}),
    ("string", "string", "a"),
    ("integer", "integer", 1),
    ("boolean", "boolean", True),
)

from sandbox.python.runtime_observation.project import write_project


def execute(root, command, work):
    argv = [sys.executable, "-B", "-m", "vibeflow", command,
            "--workspace", str(root.parent / "vibeflow_config.jsonc"), "--config", str(root / "workflow.jsonc")]
    if command == "validate":
        argv.append("--json")
    else:
        argv.extend(["--input", str(root / "input.json"), "--run-root", str(work / "runs"),
                     "--run-id", f"{root.name}-{uuid4().hex[:8]}"])
    environment = {**os.environ, "PYTHONPATH": str(REPOSITORY / "src"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    result = subprocess.run(argv, cwd=work, env=environment, capture_output=True, text=True, check=False)
    (root / f"{command}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (root / f"{command}.stderr.txt").write_text(result.stderr, encoding="utf-8")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = None
    observed = {"command": argv, "exit_code": result.returncode,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "payload": payload, "stderr": result.stderr}
    if payload:
        observed["diagnostics"] = payload.get("errors", [])
    if command == "run" and result.returncode == 0 and payload:
        trace = Path(payload["run_dir"]) / "runtime_trace.jsonl"
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        observed["executed_node_types"] = [event["type"] for event in events if event.get("kind") == "node"]
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    cases = []
    for case_id, schema_type, value in CASES:
        root = work / case_id
        write_project(root, schema_type, value)
        validation = execute(root, "validate", work)
        runtime = execute(root, "run", work) if validation["exit_code"] == 0 else {"status": "BLOCKED_BY_VALIDATION"}
        cases.append({"id": case_id, "expected_validation": "PASS", "original": value,
                      "project": str(root), "validate": validation, "runtime": runtime})
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY,
                              capture_output=True, text=True, check=True).stdout.strip()
    report = {"schema": "vibeflow.sdk-defaults-cli-observation.v1", "revision": revision,
              "exit_code_meaning": "0 means observations completed; inspect validate/runtime status",
              "cases": cases}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.report), "cases": [
        {"id": case["id"], "validate": case["validate"]["status"],
         "codes": [item["code"] for item in case["validate"].get("diagnostics", [])],
         "runtime": case["runtime"]["status"]}
        for case in cases]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
