#!/usr/bin/env python3
"""Run adaptation regressions without turning historical bugs into expectations."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.fixtures.adaptation_regressions.common import write_json
from tools.test_parallel import add_worker_argument

GROUPS = ("core_sdk", "python_runtime", "javascript", "structure")


def run_group(group, args):
    module = importlib.import_module("tests.fixtures.adaptation_regressions." + group)
    work = args.work / group
    work.mkdir(parents=True, exist_ok=True)
    return module.observe(work, args.kernel, args.toolchain, args.renderer)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument("--group", choices=GROUPS, action="append")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, default=ROOT / "src")
    parser.add_argument("--toolchain", type=Path)
    parser.add_argument("--renderer", type=Path)
    args = parser.parse_args(argv)
    args.work = args.work.resolve()
    args.kernel = args.kernel.resolve()
    sys.path.insert(0, str(args.kernel))
    if args.work.exists():
        parser.error("--work must be a new directory")
    args.work.mkdir(parents=True)
    rows, errors = [], []
    groups = tuple(dict.fromkeys(args.group or GROUPS))
    manifest = json.loads(Path(__file__).with_name("cases.json").read_text())
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_group, group, args): group for group in groups}
        for future in as_completed(futures):
            group = futures[future]
            try:
                observed = future.result()
                if not isinstance(observed, list) or not observed:
                    raise ValueError("group returned no observations")
                missing = set(manifest[group]) - {item["id"] for item in observed}
                extra = {item["id"] for item in observed} - set(manifest[group])
                if missing or extra:
                    errors.append({"group": group, "error": "case manifest mismatch",
                                   "missing": sorted(missing), "extra": sorted(extra)})
                rows.extend(observed)
                print(f"{group}: {len(observed)} observations", flush=True)
            except Exception as error:
                errors.append({"group": group, "error": repr(error)})
                print(f"{group}: {error!r}", flush=True)
    duplicates = [key for key, count in Counter(item["id"] for item in rows).items() if count != 1]
    if duplicates:
        errors.append({"group": "runner", "error": "duplicate IDs: " + repr(duplicates)})
    result = {"schema": "vibeflow.adaptation-regressions.v1", "kernel": str(args.kernel),
        "groups": groups, "workers": args.workers, "cases": sorted(rows, key=lambda item: item["id"]),
        "errors": errors, "summary": {"cases": len(rows),
            "matched": sum(item["matched"] for item in rows),
            "unmatched": sum(not item["matched"] for item in rows), "process_errors": len(errors)}}
    write_json(args.report.resolve(), result)
    print(result["summary"], flush=True)
    for item in rows:
        if not item["matched"]:
            print(item["id"] + ": " + "; ".join(item["failures"]), flush=True)
    return 2 if errors else int(bool(result["summary"]["unmatched"]))


if __name__ == "__main__":
    raise SystemExit(main())
