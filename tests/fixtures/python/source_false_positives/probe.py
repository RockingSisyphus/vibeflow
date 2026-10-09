"""Independent SDK workflows for source-check false positives and real violations."""

import argparse
import json
from pathlib import Path

from tests.fixtures.python.sdk_defaults.validate_probe import execute, write_project


VALUE = '        return {"result": {"value": 1}}'
CASES = (
    ("node_local_requests", "", '        requests = []\n        requests.append(1)\n' + VALUE, "", True),
    ("node_local_pathlib", "", '        pathlib = []\n        pathlib.append(1)\n' + VALUE, "", True),
    ("node_local_requests_get", "", '        requests = {"key": 1}\n        value = requests.get("key")\n' + VALUE, "", True),
    ("node_local_alias", "from urllib import parse as requests", '        requests = []\n        requests.append(1)\n' + VALUE, "", True),
    ("node_pure_path", "from pathlib import PurePath", '        value = str(PurePath("root") / "run")\n' + VALUE, "", True),
    ("node_pure_path_alias", "from pathlib import PurePath as Pure", '        value = str(Pure("root") / "run")\n' + VALUE, "", True),
    ("node_pure_posix", "from pathlib import PurePosixPath", '        value = str(PurePosixPath("root") / "run")\n' + VALUE, "", True),
    ("node_pure_windows", "from pathlib import PureWindowsPath", '        value = str(PureWindowsPath("root") / "run")\n' + VALUE, "", True),
    ("node_real_path", "from pathlib import Path", '        value = Path("root").read_text()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_network", "import requests", '        value = requests.get("https://example.invalid")\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_pure_shadow_open", "from pathlib import PurePath", '        PurePath = open\n        PurePath("artifact.txt", "w")\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("library_local_requests", "", '    requests = []\n    requests.append(1)\n    return 1', "", True),
    ("library_local_requests_get", "", '    requests = {"key": 1}\n    return requests.get("key")', "", True),
    ("library_local_alias", "from urllib import parse as requests", '    requests = []\n    requests.append(1)\n    return 1', "", True),
    ("library_pure_path", "from pathlib import PurePath", '    return str(PurePath("root") / "run")', "", True),
    ("library_network", "import requests", '    return requests.get("https://example.invalid")', "BASE_LIB.BANNED_IMPORT", False),
    ("library_alias_open", "", '    operation = open\n    return operation("artifact.txt", "w")', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("library_named_reset", "", '    return 1', "", True),
    ("library_named_close", "", '    return 1', "", True),
    ("library_named_reset_state", "import random", '    random.seed(1)\n    return 1', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("library_named_close_io", "", '    return open("artifact.txt", "w")', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("inherited_local", "", VALUE, "", True),
    ("inherited_import", "", VALUE, "", True),
    ("inherited_override", "", VALUE, "", True),
    ("inherited_diamond", "", VALUE, "", True),
    ("inherited_print", "", '        print("business")\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("inherited_bad_signature", "", VALUE, "NODE.CONTRACT.RUN_PURE_SIGNATURE", False),
    ("inherited_async", "", VALUE, "NODE.CONTRACT.ASYNC_RUN_PURE", False),
    ("missing_method", "", VALUE, "NODE.CONTRACT.MISSING_RUN_PURE", False),
    ("decision_flow_output", "", VALUE, "", True),
    ("decision_plain_output", "", VALUE, "", True),
    ("missing_output_branch", "", '        if params["cleanup_record_roots"]:\n            return {}\n' + VALUE, "", True),
    ("file_over_limit", "", VALUE, "BASE_LIB.SOURCE.MAX_LINES", False),
)


def write_case(root, case):
    case_id, imports, body, _, _ = case
    write_project(root, "integer", 1)
    source = root / "plugin.py"
    code = source.read_text()
    original = code
    start = code.index('    def run_pure', code.index('class Defaults:'))
    end = code.index('\n@node(type_key="probe.end"', start)
    code = code[:start] + '    def run_pure(self, inputs, params):\n' + body + '\n' + code[end:]
    if case_id.startswith("library_"):
        (root / "helper.py").write_text(imports + '\nfrom vibeflow.targets.python.sdk import base_lib\n'
            '@base_lib(id="probe.helper", rulesets=["vibeflow.base_lib"])\ndef helper():\n' + body + '\n')
        code = original[:start] + '    def run_pure(self, inputs, params):\n        value = helper()\n' + VALUE + '\n' + original[end:]
        code = 'from helper import helper\n' + code
        code = code.replace('rulesets=["vibeflow.process"])', 'rulesets=["vibeflow.process"], base_libs=["probe.helper"])')
        code = code.replace('resources=[Start, Defaults, End, inspection]', 'resources=[Start, Defaults, End, inspection, helper]')
        if case_id.startswith("library_named_"):
            name = "reset_loader_for_epoch" if "reset" in case_id else "close"
            helper_source = root / "helper.py"
            helper_source.write_text(helper_source.read_text().replace('def helper():', f'def {name}():'))
            code = code.replace('from helper import helper', f'from helper import {name} as helper')
    elif case_id.startswith("inherited_"):
        signature = 'async def' if case_id == "inherited_async" else 'def'
        arguments = 'self, inputs' if case_id == "inherited_bad_signature" else 'self, inputs, params'
        parent = f'class Parent:\n    {signature} run_pure({arguments}):\n' + body + '\n'
        own_start = code.index('    def run_pure', code.index('class Defaults:'))
        own_end = code.index('\n@node(type_key="probe.end"', own_start)
        code = code[:own_start] + '    pass\n' + code[own_end:]
        base = "Parent"
        if case_id == "inherited_diamond":
            parent += 'class Left(Parent):\n    pass\nclass Right(Parent):\n    pass\n'
            base = "Left, Right"
        if case_id == "inherited_override":
            parent = parent.replace(VALUE, '        print("must not execute or audit overridden method")\n' + VALUE)
            code = code.replace('class Defaults:\n    pass', 'class Defaults:\n    def run_pure(self, inputs, params):\n' + VALUE)
        if case_id in {"inherited_import", "inherited_print"}:
            (root / "helper.py").write_text('from vibeflow.targets.python.sdk import base_lib\n'
                '@base_lib(id="probe.helper", rulesets=[])\n' + parent)
            code = 'from helper import Parent\n' + code
            code = code.replace('rulesets=["vibeflow.process"])', 'rulesets=["vibeflow.process"], base_libs=["probe.helper"])')
            code = code.replace('resources=[Start, Defaults, End, inspection]', 'resources=[Start, Defaults, End, inspection, Parent]')
        else:
            code = parent + code
        code = code.replace('class Defaults:', f'class Defaults({base}):')
    elif case_id == "missing_method":
        code = original[:start] + '    pass\n' + original[end:]
    elif case_id.startswith("decision_"):
        code = code.replace('@node(type_key="probe.defaults", contract=', '@node(type_key="probe.defaults", flow_kind="decision", contract=')
        key = 'flow.backend' if case_id == 'decision_flow_output' else 'result'
        if case_id == "decision_flow_output":
            code = code.replace('"result"', '"flow.backend"')
        workflow_path = root / 'workflow.jsonc'
        workflow = json.loads(workflow_path.read_text())
        workflow['pipeline']['edges'][1] = {'from': 'inspect', 'to': 'end', 'when': key + ' == true'}
        workflow_path.write_text(json.dumps(workflow))
    elif case_id == "file_over_limit":
        code += '\n' + '# source line\n' * 501
    if not case_id.startswith("library_"):
        code = imports + '\n' + code
    source.write_text(code)


def observe(work, *, run=True):
    work.mkdir(parents=True, exist_ok=True)
    observations = []
    for case in CASES:
        case_id, _, _, expected_code, allowed = case
        root = work / case_id
        write_case(root, case)
        validation = execute(root, "validate", work)
        errors = validation.get("diagnostics", [])
        matched = validation["exit_code"] == 0 if allowed else (validation["exit_code"] == 1
            and any(item["code"] == expected_code and item["severity"] == "error"
                    and item.get("source_location", {}).get("line", 0) > 0 for item in errors))
        observed = {"id": case_id, "expected_allowed": allowed, "expected_code": expected_code,
                    "matched": matched, "validate": validation}
        if run and case_id in {"node_local_requests", "node_pure_path", "inherited_import", "inherited_diamond"}:
            runtime = execute(root, "run", work) if validation["exit_code"] == 0 else {"exit_code": None}
            observed["run"] = runtime
            observed["matched"] = matched and runtime["exit_code"] == 0 and "probe.defaults" in runtime.get("executed_node_types", ())
        observations.append(observed)
    return {"schema": "vibeflow.source-false-positives.v1", "cases": observations,
            "matched": all(item["matched"] for item in observations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--kernel", type=Path, help="Optional source root containing src/vibeflow")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.kernel:
        from tests.fixtures.python.sdk_defaults import validate_probe
        validate_probe.REPOSITORY = args.kernel.resolve()
    report = observe(args.work.resolve(), run=not args.validate_only)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({"matched": report["matched"], "mismatches": [item["id"] for item in report["cases"] if not item["matched"]]}))
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
