"""Validate a two-root ownership matrix without executing business Nodes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).resolve().parent / "ownership"


def run(work, *, toolchain, launcher=None):
    shutil.copytree(FIXTURE, work / "fixture")
    fixture = work / "fixture"
    for root in ("library", "caller"):
        (fixture / root / "node_modules").symlink_to(
            toolchain.resolve() / "node_modules", target_is_directory=True)
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if launcher:
        environment.pop("PYTHONPATH", None)
        command = [sys.executable, "-B", str(launcher.resolve())]
    else:
        environment["PYTHONPATH"] = str(ROOT / "src")
        command = [sys.executable, "-B", "-m", "vibeflow"]
    observations = []
    for case in json.loads((fixture / "cases.json").read_text()):
        name = case["root"] + "-" + case["mode"]
        args = [*command, "validate", "--workspace", str(fixture / "vibeflow_config.jsonc"),
                "--config", str(fixture / case["config"]), "--json"]
        completed = subprocess.run(args, cwd=work, env=environment, text=True, capture_output=True)
        (work / (name + ".stdout.json")).write_text(completed.stdout)
        (work / (name + ".stderr.txt")).write_text(completed.stderr)
        payload = json.loads(completed.stdout)
        findings = payload.get("diagnostics", payload.get("findings", []))
        # Public reports can put the findings inside their health report.
        if not findings:
            findings = payload.get("health_report", {}).get("errors", [])
        owners = [item for item in findings if item.get("code") == "VF_IMPORT_OWNER"]
        codes = sorted({item.get("code", "") for item in findings})
        matched = (bool(owners) and completed.returncode != 0) if case["expect_owner_error"] else (
            completed.returncode == 0 and payload.get("status") in {"PASS", "CONCERNS"} and not owners)
        observations.append({**case, "status":payload.get("status"), "exit_code":completed.returncode,
                             "codes":codes, "owner_errors":owners, "matched":matched})
        print(name, payload.get("status"), "owner_errors=" + str(len(owners)),
              "matched=" + str(matched), flush=True)
    inspected = subprocess.run([*command, "inspect-resources", "--workspace", str(fixture / "vibeflow_config.jsonc"),
        "--config", str(fixture / "caller/configs/direct.jsonc"), "--kind", "base_lib",
        "--id", "ownership.math", "--json"], cwd=work, env=environment, text=True, capture_output=True)
    (work / "inspect-base-lib.json").write_text(inspected.stdout)
    (work / "inspect-base-lib.stderr.txt").write_text(inspected.stderr)
    assert inspected.returncode == 0, inspected.stderr or inspected.stdout
    report = {"status":"PASS" if all(item["matched"] for item in observations) else "FAIL",
              "scope":"static ownership validation; no workflow execution",
              "observations":observations}
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, help="optional extracted distribution run.py")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-task-ownership-") as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        result = run(work, toolchain=args.toolchain_root, launcher=args.launcher)
        print("Ownership matrix:", result["status"], "report:", work / "report.json")
        raise SystemExit(0 if result["status"] == "PASS" else 1)
