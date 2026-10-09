"""Real CLI output, startup failure, heartbeat and final monitoring records."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from sandbox.python.runtime_observation.project import write_project

REPOSITORY = Path(__file__).resolve().parents[3]


BODY = '''        info = [{"metrics": {"loss": 0.125}}, {"message": "正在训练第10轮"}]
        update_run_info(info)
        info[0]["metrics"]["loss"] = 999
        print("business-stdout", flush=True)
        print("business-stderr", file=sys.stderr, flush=True)
        os.write(1, b"native-stdout\\n")
        subprocess.run([sys.executable, "-c", "print('child-stdout')"], check=True)
        thread = threading.Thread(target=lambda: print("thread-stdout", flush=True))
        thread.start()
        thread.join()
        time.sleep(.25)
'''


def observe(work, case_id):
    root = work / case_id
    write_project(root, "integer", 1)
    source = root / "plugin.py"
    code = source.read_text().replace('rulesets=["vibeflow.process"]', 'rulesets=["vibeflow.python_io"]')
    code = 'import os\nimport subprocess\nimport sys\nimport time\nimport threading\nfrom vibeflow.targets.python.sdk import update_run_info\n' + code
    code = code.replace('        value = params["cleanup_record_roots"]', BODY + (
        '        raise RuntimeError("sandbox training failed")\n' if case_id == "runtime_failure" else '') + '        value = params["cleanup_record_roots"]')
    source.write_text(code)
    status = work / "monitor.json"
    run_dir = work / "runs" / case_id
    argv = [sys.executable, "-B", "-m", "vibeflow", "run", "--config", str(root / "workflow.jsonc"),
            "--workspace", str(root / "vibeflow_config.jsonc"), "--run-root", str(work / "runs"),
            "--run-id", case_id, "--status-interval", ".03", "--status-file", str(status)]
    if case_id == "startup_failure":
        argv[argv.index("--workspace") + 1] = str(root / "missing.jsonc")
    env = {**os.environ, "PYTHONPATH": str(REPOSITORY / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    output = root / "stdout.txt"
    error = root / "stderr.txt"
    records = []
    with output.open("w") as stdout, error.open("w") as stderr:
        process = subprocess.Popen(argv, cwd=work, env=env, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            if status.exists():
                records.append(json.loads(status.read_text()))
            time.sleep(.005)
        code = process.wait()
    final = json.loads(status.read_text())
    business = (run_dir / "business.log").read_text()
    kernel = (run_dir / "vibeflow.log").read_text()
    expected_state = "succeeded" if case_id == "success" else "failed"
    checks = {"exit": code == (0 if case_id == "success" else 1),
              "final_state": final["state"] == expected_state,
              "error": final["error"] is None if case_id == "success" else isinstance(final["error"], str),
              "kernel_separation": "business-stdout" not in kernel}
    if case_id != "startup_failure":
        checks.update(console=all(value in business for value in (
            "business-stdout", "business-stderr", "native-stdout", "child-stdout", "thread-stdout")),
            terminal="business-stdout" in output.read_text() and "business-stderr" in error.read_text(),
            final_info=bool(final["info"]) and final["info"][0]["metrics"]["loss"] == .125,
            heartbeat=len({record["updated_at"] for record in records if record["state"] == "running"}) >= 2,
            report_separation='"checked_ids"' not in business)
    else:
        checks["reset_info"] = final["info"] == []
    return {"id": case_id, "matched": all(checks.values()), "checks": checks, "exit_code": code,
            "final": final, "states": sorted({record["state"] for record in records}),
            "run_dir": str(run_dir), "stderr": error.read_text()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    cases = [observe(work, name) for name in ("success", "runtime_failure", "startup_failure")]
    report = {"schema": "vibeflow.runtime-observation.v1", "cases": cases, "matched": all(case["matched"] for case in cases)}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
