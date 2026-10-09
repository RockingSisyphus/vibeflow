"""Replay frozen source or products from a completed fresh official full gate.

The unchanged16 static/CLI reviews accompany the existing F01-F04 matrices.
The source core executes701 regression checks plus36 raw observations; an
explicit controls probe adds164 checks. Three final products include those
controls and execute5373 regression checks plus108 raw observations. A nonzero
probe exit is recorded and does not prevent collection of the remaining groups.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selected = parser.add_mutually_exclusive_group(required=True)
    selected.add_argument("--source", type=Path)
    selected.add_argument("--gate", type=Path)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="this run's explicit frozen product manifest")
    parser.add_argument("--exception-controls", type=Path,
                        help="standalone164 controls; included by default for final products")
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    repo = evidence.parents[2]
    prior = repo / "docs/maintainers/python-alias-facts-fix-20261008"
    f01 = repo / "docs/maintainers/python-function-definition-scope-fix-20261008"
    f02 = repo / "docs/maintainers/python-comprehension-scope-fix-20261008"
    args.report_dir = args.report_dir.resolve()
    args.work_root = args.work_root.resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["TMPDIR"] = "/home/rockingsisyphus/.cache/vf-p2/t"
    if Path(tempfile.gettempdir()).resolve() != Path(os.environ["TMPDIR"]).resolve():
        parser.error("selected external TMPDIR is unusable; refusing fallback")
    if args.work_root.exists():
        parser.error("work root already exists; preserve it and select a fresh run")
    profiles = ("source",) if args.source else ("wheel", "collaborative", "autonomous")
    counts = {"F05-static16": 16, "F05-cli16": 16, "formal128": 128, "raw36": 36,
              "writeback103": 103, "evaluation12": 12, "nested_clear3": 3,
              "writeback_exits3": 3, "writeback_exits5": 5, "F01-original40": 40,
              "F02-original180": 180, "F01-formal72": 72, "F02-formal89": 89, "declared34": 34}
    if args.gate:
        counts.update(effects873=873, inputs20=20, javascript33=33)
        if args.exception_controls is None:
            args.exception_controls = evidence / "probe_exception_controls.py"
    if args.exception_controls:
        args.exception_controls = args.exception_controls.resolve(strict=True)
        counts["F05-controls164"] = 164
    for profile in profiles:
        for group in counts:
            if any((args.report_dir / (f"{args.tag}-{profile}-{group}" + suffix)).exists()
                   for suffix in (".json", "-origin.json")):
                parser.error("report already exists; preserve it and select a fresh tag")
    exit_report = args.report_dir / f"{args.tag}-probe-exits.json"
    if exit_report.exists():
        parser.error("exit report already exists")
    args.work_root.mkdir(parents=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    def run_profile(profile: str) -> list:
        interpreter = str(args.gate.resolve() / "wheel-venv/bin/python") if profile == "wheel" else sys.executable
        selection = []
        if profile == "source":
            selection = ["--source", str(args.source.resolve(strict=True))]
        elif profile != "wheel":
            folder = "distribution" if profile == "collaborative" else "distribution-autonomous"
            selection = ["--kernel", str((args.gate.resolve() / folder / "kernel/vibeflow-kernel.zip").resolve(strict=True))]
        profile_work = args.work_root / profile
        profile_work.mkdir()
        entries = []
        for group, count in counts.items():
            prefix = f"{args.tag}-{profile}-{group}"
            report = args.report_dir / (prefix + ".json")
            origin = args.report_dir / (prefix + "-origin.json")
            work = profile_work / group
            if group == "F05-controls164":
                command = [str(args.exception_controls), *selection,
                           "--manifest", str(args.manifest.resolve(strict=True)), "--report", str(report)]
            elif group.startswith("F05-"):
                command = [str(evidence / "replay_exception_review.py"), *selection,
                           "--review", "static" if group == "F05-static16" else "cli",
                           "--manifest", str(args.manifest.resolve(strict=True)),
                           "--expect", "fixed", "--report", str(report), "--origin-report", str(origin)]
                if group == "F05-cli16":
                    command += ["--work", str(work)]
            elif group == "formal128":
                command = [str(prior / "alias_facts_probe.py"), *selection, "--expect", "fixed", "--work", str(work), "--report", str(report)]
            elif group == "raw36":
                command = [str(prior / "replay_original_alias_review.py"), *selection, "--report", str(report), "--origin-report", str(origin)]
            elif group == "writeback103":
                command = [str(prior / "packaged_writeback103_probe.py"), *selection, "--report", str(report)]
            elif group in ("evaluation12", "nested_clear3", "writeback_exits3", "writeback_exits5"):
                command = [str(prior / "replay_input_evaluation_review.py"), *selection, "--review", group,
                           "--expect", "fixed", "--report", str(report)]
            elif group in ("F01-original40", "F02-original180"):
                command = [str(prior / "replay_historical_scope.py"), *selection, "--review", group[:3],
                           "--report", str(report), "--origin-report", str(origin)]
            elif group in ("F01-formal72", "F02-formal89"):
                script = f01 / "default_scope_probe.py" if group == "F01-formal72" else f02 / "comprehension_cli_probe.py"
                command = [str(script), *selection, "--expect", "fixed", "--work", str(work), "--report", str(report)]
            elif group == "declared34":
                command = [str(f02 / "declared_binding_probe.py"), *selection, "--expect", "fixed", "--report", str(report)]
            elif group == "effects873":
                command = [str(prior / "packaged_python_effects_probe.py"), *selection, "--reject-source-prefix", str(repo / "src"),
                           "--workdir", str(work), "--report", str(report)]
            elif group == "inputs20":
                command = [str(prior / "packaged_inputs_probe.py"), *selection, "--work", str(work), "--report", str(report)]
            else:
                command = [str(prior / "packaged_js_probe.py"), *selection, "--toolchain-root", str(args.gate.resolve() / "pytest/javascript-toolchain"),
                           "--work-root", str(work), "--report", str(report)]
            log = profile_work / (group + ".log")
            with log.open("xb") as output:
                proc = subprocess.run([interpreter, "-I", "-B", *command], stdout=output, stderr=subprocess.STDOUT,
                                      cwd=repo, env=os.environ.copy())
            entry = {"profile": profile, "group": group, "cases": count,
                     "raw_observations_only": group == "raw36", "exit": proc.returncode,
                     "report": str(report), "log": str(log), "command": [interpreter, "-I", "-B", *command]}
            entries.append(entry)
            with (profile_work / "progress.json").open("w") as output:
                json.dump(entries, output, indent=2)
                output.write("\n")
            print(f"{profile} {group} exit={proc.returncode}", flush=True)
        return entries

    with ThreadPoolExecutor(max_workers=len(profiles)) as pool:
        entries = [entry for group in pool.map(run_profile, profiles) for entry in group]
    result = {"tag": args.tag, "source": str(args.source.resolve()) if args.source else None,
              "gate": str(args.gate.resolve()) if args.gate else None, "entries": entries,
              "manifest": str(args.manifest.resolve()),
              "exception_controls": str(args.exception_controls) if args.exception_controls else None,
              "regression_checks": sum(row["cases"] for row in entries if not row["raw_observations_only"]),
              "raw_observations": sum(row["cases"] for row in entries if row["raw_observations_only"]),
              "pass": all(row["exit"] == 0 for row in entries)}
    with exit_report.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
