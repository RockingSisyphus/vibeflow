"""Formal CLI controls for type specialization and real module reflection."""

import argparse
import json
from pathlib import Path

from sandbox.python.sdk_defaults.validate_probe import execute, write_project


CASES = (
    ("plain", "", "inputs", "", True),
    ("iterable", "from typing import Iterable", "inputs: Iterable[object]", "", True),
    ("alias", "from typing import Iterable as Items", "inputs: Items[object]", "", True),
    ("qualified", "import typing as t", "inputs: t.Iterable[object]", "", True),
    ("collections", "from collections.abc import Iterable", "inputs: Iterable[object]", "", True),
    ("nested", "from typing import Iterable, Mapping", "inputs: Iterable[Mapping[str, object]]", "", True),
    ("return", "from typing import Mapping", "inputs", " -> Mapping[str, object]", True),
    ("future", "from __future__ import annotations\nfrom typing import Iterable", "inputs: Iterable[object]", "", True),
    ("namespace", "import typing", "inputs", "", False),
    ("module_dict", "import typing", "inputs", "", False),
    ("shadow", "import typing\nfrom typing import Iterable", "inputs", "", False),
    ("helper", "", "inputs", "", True),
    ("helper_namespace", "", "inputs", "", False),
    ("annotation_call", "from typing import Iterable", "inputs", "", False),
)


def observe(work):
    cases = []
    for case_id, imports, inputs, returns, allowed in CASES:
        root = work / case_id
        write_project(root, "integer", 1)
        source = root / "plugin.py"
        original = source.read_text()
        code = imports + "\n" + original.replace("run_pure(self, inputs, params):", f"run_pure(self, {inputs}, params){returns}:")
        statements = {
            "namespace": '        key = params["cleanup_record_roots"]\n        value = typing[key]',
            "module_dict": '        key = params["cleanup_record_roots"]\n        value = typing.__dict__[key]',
            "shadow": '        Iterable = typing.__dict__\n        key = params["cleanup_record_roots"]\n        value = Iterable[key]',
            "annotation_call": '        value: Iterable[eval("object")] = []',
        }
        if case_id in statements:
            code = code.replace('        value = params["cleanup_record_roots"]', statements[case_id])
        if case_id.startswith("helper"):
            (root / "helper.py").write_text("""from typing import Iterable
import typing
from vibeflow.targets.python.sdk import base_lib

@base_lib(id="probe.helper", rulesets=["vibeflow.base_lib"])
def helper(inputs: Iterable[object]):
""" + ('    key = "Iterable"\n    namespace = typing.__dict__[key]\n' if not allowed else '') + '    return 1\n')
            code = 'from helper import helper\n' + code
            code = code.replace('rulesets=["vibeflow.process"])', 'rulesets=["vibeflow.process"], base_libs=["probe.helper"])')
            code = code.replace('        value = params["cleanup_record_roots"]', '        value = helper(inputs)')
            code = code.replace('resources=[Start, Defaults, End, inspection]', 'resources=[Start, Defaults, End, inspection, helper]')
        source.write_text(code)
        result = execute(root, "validate", work)
        errors = result.get("diagnostics", [])
        matched = result["exit_code"] == 0 if allowed else (
            result["exit_code"] == 1 and any(item["code"].endswith("PURITY.BANNED_CALL") for item in errors))
        cases.append({"id": case_id, "allowed": allowed, "matched": matched,
                      "exit_code": result["exit_code"], "errors": errors})
    return {"schema": "vibeflow.typing-annotation-observation.v1", "cases": cases,
            "matched": all(case["matched"] for case in cases)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = observe(args.work.resolve())
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"matched": report["matched"], "cases": len(report["cases"])}))
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
