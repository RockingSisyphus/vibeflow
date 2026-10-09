#!/usr/bin/env python3
"""Fresh-process, single-worker timings of fixed adaptation cases."""

import argparse
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tests.fixtures.adaptation_regressions.common import run_probe, write_json
from tests.fixtures.adaptation_regressions.js_analysis import _COUNT_PROBE
from tests.fixtures.adaptation_regressions.js_fixtures import project, cli_args
from tests.fixtures.adaptation_regressions.python_runtime import OBSERVER, arguments
from tests.fixtures.python.review_performance.fixtures import write_project


RECORD = """
import json
from time import perf_counter
from vibeflow.core.rules import RuleRecord
value=1
for _ in range(12): value=(value,value)
started=perf_counter()
for _ in range(25): result=RuleRecord('case.graph',value)
seconds=perf_counter()-started
seen=set();pending=[result.value]
while pending:
    item=pending.pop()
    if isinstance(item,tuple) and id(item) not in seen:
        seen.add(id(item));pending.extend(item)
print(json.dumps({'freeze_seconds':seconds,'output_objects':len(seen),'shared':result.value[0] is result.value[1]}))
"""


def measure(kernel, work, toolchain, repetitions):
    observations = []
    for repetition in range(repetitions):
        selected = work / str(repetition)
        selected.mkdir(parents=True)
        record = run_probe(selected, RECORD, kernel, name="record")
        python_root = selected / "python"
        write_project(python_root, nodes=8, libraries=4, lines=350)
        python = run_probe(python_root, OBSERVER, kernel,
            args=["count", "--", *arguments(python_root, "inspect-config")], name="inspect")
        javascript_root = project(selected / "javascript", toolchain)
        javascript = run_probe(javascript_root, _COUNT_PROBE, kernel,
            args=cli_args(javascript_root, "validate"), name="validate", toolchain=toolchain)
        if any(item["exit_code"] for item in (record, python, javascript)):
            raise RuntimeError("timing observer failed: " + str(selected))
        observations.append({"repetition": repetition + 1,
            "record": {"process_seconds": record["seconds"], **record["payload"]},
            "python": {"process_seconds": python["seconds"], **python["payload"]},
            "javascript": {"process_seconds": javascript["seconds"], **javascript["payload"]}})
    return {"kernel": str(kernel), "observations": observations,
        "medians": {"record_freeze_seconds": median(item["record"]["freeze_seconds"] for item in observations),
            "python_process_seconds": median(item["python"]["process_seconds"] for item in observations),
            "javascript_process_seconds": median(item["javascript"]["process_seconds"] for item in observations)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, default=ROOT / "src")
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.work.exists() or args.repetitions < 1:
        parser.error("use a new work directory and at least one repetition")
    observations = {}
    for name, kernel in (("before", args.baseline), ("after", args.kernel)):
        observations[name] = measure(kernel.resolve(), args.work / name, args.toolchain, args.repetitions)
        write_json(args.report, {"schema": "vibeflow.adaptation-timings.v1", "workers": 1,
            "repetitions": args.repetitions, **observations})
    print(json.dumps({key: value["medians"] for key, value in observations.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
