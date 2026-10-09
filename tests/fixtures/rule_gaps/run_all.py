#!/usr/bin/env python3
"""Current Rule API acceptance cases, separate from historical parity counts."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.test_parallel import DEFAULT_WORKERS, WORKER_ENVIRONMENT, add_worker_argument
from tests.fixtures.rule_gaps.resources import FAMILIES, validate_counts
GROUPS = ("python", "javascript", "graph", "tooling", "composition", "resources")
spec = importlib.util.spec_from_file_location("parity_results", HERE.parent / "rule_parity/results.py")
_results = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_results)


def assess(rows):
    duplicates = [key for key, count in Counter(row["id"] for row in rows).items() if count != 1]
    if duplicates:
        raise ValueError("duplicate case IDs: " + repr(duplicates))
    return [{**row, "mismatches": _results.mismatch(row)} for row in rows]


def environment(toolchain=None, renderer=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    env.setdefault("npm_config_cache", "/tmp/vibeflow-npm-cache")
    if toolchain:
        env["VIBEFLOW_TEST_TOOLCHAIN_ROOT"] = str(toolchain)
    if renderer:
        env["VIBEFLOW_MERMAID_RENDERER_ROOT"] = str(renderer)
    return env


def install(work, name, source):
    destination = work / name
    destination.mkdir()
    for filename in ("package.json", "package-lock.json"):
        shutil.copy2(source / filename, destination / filename)
    with (destination / "install.log").open("w") as log:
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=destination,
                       env=environment(), stdout=log, stderr=subprocess.STDOUT, check=True)
    return destination


def observe(group, work, toolchain, renderer, resource_family=None, *, workers=DEFAULT_WORKERS):
    directory = work / group
    directory.mkdir(exist_ok=True)
    prefix = resource_family + "-" if resource_family else ""
    output = directory / (prefix + "observations.json")
    cmd = [sys.executable, str(HERE / "worker.py"), "--group", group,
           "--work", str(directory / "projects"), "--output", str(output)]
    if toolchain:
        cmd.extend(("--toolchain", str(toolchain)))
    env = {**environment(toolchain, renderer), WORKER_ENVIRONMENT: str(workers)}
    if resource_family:
        env["VIBEFLOW_RESOURCE_CASE_GROUP"] = resource_family
    process_log = directory / (prefix + "process.log")
    with process_log.open("w") as log:
        process = subprocess.run(cmd, cwd=directory, env=env,
                                 stdout=log, stderr=subprocess.STDOUT, check=False)
    if process.returncode or not output.exists():
        raise RuntimeError(f"{group} observation process failed; see {process_log}")
    rows = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{group} must return a nonempty observation list")
    required = {"id", "title", "family", "classification", "expected", "actual"}
    if any(not isinstance(row, dict) or not required <= row.keys()
           or not isinstance(row["expected"], dict) or not isinstance(row["actual"], dict) for row in rows):
        raise ValueError(f"{group} returned incomplete observations")
    return rows


def run(work, groups, report, *, toolchain=None, renderer=None, workers=DEFAULT_WORKERS):
    work.mkdir(parents=True, exist_ok=True)
    needs_js = any(group != "python" for group in groups)
    if needs_js and toolchain is None:
        toolchain = install(work, "javascript-toolchain", ROOT / "sandbox/javascript/minimal/project")
    if any(group in {"javascript", "composition", "resources"} for group in groups) and renderer is None:
        renderer = install(work, "mermaid-renderer", ROOT / "tools/mermaid-renderer")
    rows, errors = [], []
    tasks = [(group, family) for group in groups for family in (FAMILIES if group == "resources" else (None,))]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(observe, group, work, toolchain, renderer, family, workers=workers):
                group + ("/" + family if family else "") for group, family in tasks}
        for future in as_completed(jobs):
            group = jobs[future]
            try:
                observed = future.result()
                rows.extend(observed)
                print(f"{group}: {len(observed)} observations", flush=True)
            except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
                errors.append({"group": group, "error": str(exc)})
                print(f"{group}: {exc}", flush=True)
    if "resources" in groups and not errors:
        validate_counts(rows)
    cases = assess(rows)
    cases.sort(key=lambda value: value["id"])
    summary = {"cases": len(cases), "matched": sum(not row["mismatches"] for row in cases),
               "unmatched": sum(bool(row["mismatches"]) for row in cases), "process_errors": len(errors),
               "families": dict(Counter(row["family"] for row in cases))}
    result = {"current": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "current_includes_working_files": True, "groups": list(groups), "workers": workers, "summary": summary,
              "cases": cases, "errors": errors}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    for row in cases:
        if row["mismatches"]:
            print(row["id"] + ": " + "; ".join(row["mismatches"]), flush=True)
    print("report: " + str(report), flush=True)
    return 2 if errors else int(bool(summary["unmatched"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument("--group", choices=GROUPS, action="append")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--report", type=Path, default=Path("/tmp/vibeflow-rule-gaps.json"))
    parser.add_argument("--toolchain", type=Path, help="reuse the project-locked TypeScript/esbuild installation")
    parser.add_argument("--renderer", type=Path, help="reuse the project-locked Mermaid/Puppeteer installation")
    args = parser.parse_args(argv)
    groups = tuple(dict.fromkeys(args.group or GROUPS))
    try:
        options = {"toolchain": args.toolchain.resolve() if args.toolchain else None,
                   "renderer": args.renderer.resolve() if args.renderer else None,
                   "workers": args.workers}
        if args.work:
            if args.work.exists():
                parser.error("--work must be a new directory")
            return run(args.work.resolve(), groups, args.report.resolve(), **options)
        with tempfile.TemporaryDirectory(prefix="vibeflow-rule-gaps-") as temporary:
            return run(Path(temporary), groups, args.report.resolve(), **options)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("sandbox execution error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
