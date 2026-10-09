#!/usr/bin/env python3
"""Run identical sandbox scenarios against f169429 and the working checkout."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

# Running this standalone sandbox should not generate repository artifacts.
sys.dont_write_bytecode = True
if __package__:
    from .results import compare, summarize, mismatch
else:
    from results import compare, summarize, mismatch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.test_parallel import DEFAULT_WORKERS, add_worker_argument
TARGETS = ("core", "tooling", "python", "javascript")


def _environment(kernel, toolchain=None):
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(kernel / "src"), PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    if toolchain:
        environment["VIBEFLOW_TEST_TOOLCHAIN_ROOT"] = str(toolchain)
    environment.setdefault("npm_config_cache", "/tmp/vibeflow-npm-cache")
    return environment


def _snapshot(work, revision):
    kernel = work / "baseline"
    kernel.mkdir()
    archive = work / "baseline.tar"
    with archive.open("wb") as output:
        subprocess.run(["git", "archive", revision, "src", "pyproject.toml",
                        "sandbox/javascript/minimal/project/package.json",
                        "sandbox/javascript/minimal/project/package-lock.json"],
                       cwd=ROOT, stdout=output, check=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(kernel, filter="data")
    return kernel


def _toolchain(work, baseline):
    destination = work / "javascript-toolchain"
    destination.mkdir()
    sources = [kernel / "sandbox/javascript/minimal/project" for kernel in (baseline, ROOT)]
    # Both selected versions currently have the same lock. If they diverge,
    # install each version's lock rather than silently changing the baseline.
    names = ("package.json", "package-lock.json")
    shared = all((sources[0] / name).read_bytes() == (sources[1] / name).read_bytes() for name in names)
    result = {}
    for variant, source in zip(("baseline", "current"), sources):
        if variant == "current" and shared:
            result[variant] = result["baseline"]
            continue
        target = destination / variant
        target.mkdir()
        for name in names:
            shutil.copy2(source / name, target / name)
        with (target / "install.log").open("w") as log:
            subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=target,
                           stdout=log, stderr=subprocess.STDOUT,
                           env=_environment(baseline), check=True)
        result[variant] = target
    return result


def _observe(target, variant, kernel, work, toolchain):
    location = work / f"{target}-{variant}"
    location.mkdir()
    output = location / "observations.json"
    command = [sys.executable, str(HERE / "worker.py"), "--cases", str(HERE / target / "cases.py"),
               "--variant", variant, "--work", str(location / "projects"), "--output", str(output)]
    if toolchain:
        command.extend(("--toolchain", str(toolchain)))
    with (location / "process.log").open("w") as log:
        process = subprocess.run(command, cwd=location, env=_environment(kernel, toolchain),
                                 stdout=log, stderr=subprocess.STDOUT, check=False)
    if process.returncode or not output.exists():
        raise RuntimeError(f"{target}/{variant} observation failed; see {location / 'process.log'}")
    return json.loads(output.read_text(encoding="utf-8"))


def run(work, targets, revision, report, *, workers=DEFAULT_WORKERS):
    work.mkdir(parents=True, exist_ok=True)
    baseline = _snapshot(work, revision)
    baseline_commit = subprocess.check_output(["git", "rev-parse", revision], cwd=ROOT, text=True).strip()
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    toolchains = _toolchain(work, baseline) if "javascript" in targets else {}
    observations = {}
    print(f"baseline {baseline_commit[:12]}; current {current_commit[:12]} plus working files", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_observe, target, variant, kernel, work, toolchains.get(variant)): (target, variant)
                for target in targets for variant, kernel in (("baseline", baseline), ("current", ROOT))}
        for future in as_completed(jobs):
            key = jobs[future]
            observations[key] = future.result()
            print(f"{key[0]}/{key[1]}: {len(observations[key])} observations", flush=True)
    findings = []
    for target in targets:
        findings.extend(compare(observations[target, "baseline"], observations[target, "current"]))
    result = {"baseline": baseline_commit, "current": current_commit, "current_includes_working_files": True,
              "targets": list(targets), "workers": workers, "summary": summarize(findings), "cases": findings}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2), flush=True)
    for row in findings:
        if row["outcome"] != "matched":
            reasons = row["baseline_mismatches"] or row["current_mismatches"]
            print(row["outcome"] + ": " + row["id"] + ": " + "; ".join(reasons), flush=True)
    print("report: " + str(report), flush=True)
    return int(any(row["outcome"] != "matched" for row in findings))


def run_current(work, targets, report, toolchain=None, *, workers=DEFAULT_WORKERS):
    """Check the current checkout; frozen observations remain audit evidence."""
    work.mkdir(parents=True, exist_ok=True)
    reference = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    if "javascript" in targets and toolchain is None:
        toolchain = _toolchain(work, ROOT)["current"]
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_observe, target, "current", ROOT, work, toolchain): target for target in targets}
        for future in as_completed(jobs):
            target = jobs[future]
            try:
                observed = future.result()
                if not isinstance(observed, list) or not observed:
                    raise ValueError("missing observations")
                required = {"id", "expected", "actual"}
                if any(not isinstance(item, dict) or not required <= item.keys() for item in observed):
                    raise ValueError("invalid observation shape")
                ids = [item["id"] for item in observed]
                if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
                    raise ValueError("invalid or duplicate case IDs")
                historical = {item["id"]: item for item in reference["observations"][target]["baseline"]}
                previous = {item["id"]: item for item in reference["observations"][target]["current"]}
                for item in observed:
                    rows.append({**item, "mismatches": mismatch(item),
                                 "baseline": historical.get(item["id"]), "original_current": previous.get(item["id"])})
                missing = (historical.keys() | previous.keys()) - {item["id"] for item in observed}
                if missing:
                    raise ValueError("lost case IDs: " + repr(sorted(missing)))
                print(f"{target}: {len(observed)} observations", flush=True)
            except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
                errors.append({"target": target, "error": str(error)})
    rows.sort(key=lambda row: row["id"])
    summary = {"cases": len(rows), "matched": sum(not row["mismatches"] for row in rows),
               "unmatched": sum(bool(row["mismatches"]) for row in rows), "process_errors": len(errors)}
    result = {"baseline": reference["baseline"], "original_current": reference["original_current"],
              "current_includes_working_files": True, "mode": "current", "targets": list(targets),
              "workers": workers, "summary": summary, "cases": rows, "errors": errors}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    for row in rows:
        if row["mismatches"]:
            print(row["id"] + ": " + "; ".join(row["mismatches"]), flush=True)
    for error in errors:
        print(str(error), flush=True)
    return 2 if errors else int(bool(summary["unmatched"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument("--target", choices=TARGETS, action="append", help="repeatable; default all")
    parser.add_argument("--baseline", default="f169429")
    parser.add_argument("--current-only", action="store_true", help="use frozen historical observations; run only the working checkout")
    parser.add_argument("--toolchain", type=Path, help="reuse a locked JavaScript toolchain for current-only checks")
    parser.add_argument("--report", type=Path, default=Path("/tmp/vibeflow-rule-parity.json"))
    parser.add_argument("--work", type=Path, help="new caller-owned directory; retain source fixtures and logs")
    args = parser.parse_args(argv)
    targets = tuple(dict.fromkeys(args.target or TARGETS))
    try:
        if args.work:
            if args.work.exists():
                parser.error("--work must be a new directory")
            return (run_current(args.work.resolve(), targets, args.report.resolve(), args.toolchain, workers=args.workers)
                    if args.current_only else run(args.work.resolve(), targets, args.baseline, args.report.resolve(), workers=args.workers))
        with tempfile.TemporaryDirectory(prefix="vibeflow-rule-parity-") as scratch:
            return (run_current(Path(scratch), targets, args.report.resolve(), args.toolchain, workers=args.workers)
                    if args.current_only else run(Path(scratch), targets, args.baseline, args.report.resolve(), workers=args.workers))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print("sandbox execution error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
