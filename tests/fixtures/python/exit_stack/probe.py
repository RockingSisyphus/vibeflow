"""Formal CLI observations for stack cleanup and unchanged project-adaptation errors."""

import argparse
import json
from pathlib import Path

from tests.fixtures.python.source_false_positives.probe import VALUE, write_case
from tests.fixtures.python.sdk_defaults.validate_probe import execute


CASES = (
    ("node_empty", "from contextlib import ExitStack", '        stack = ExitStack()\n        stack.close()\n' + VALUE, "", True),
    ("node_alias", "from contextlib import ExitStack as Cleanup", '        stack = Cleanup()\n        alias = stack\n        alias.close()\n' + VALUE, "", True),
    ("node_qualified", "import contextlib as contexts", '        stack = contexts.ExitStack()\n        stack.close()\n' + VALUE, "", True),
    ("node_inline", "from contextlib import ExitStack", '        ExitStack().close()\n' + VALUE, "", True),
    ("node_with", "from contextlib import ExitStack", '        with ExitStack() as stack:\n            stack.close()\n' + VALUE, "", True),
    ("node_constructor_alias", "from contextlib import ExitStack", '        Cleanup = ExitStack\n        stack = Cleanup()\n        stack.close()\n' + VALUE, "", True),
    ("node_bound_close", "from contextlib import ExitStack", '        stack = ExitStack()\n        cleanup = stack.close\n        cleanup()\n' + VALUE, "", True),
    ("node_nested_close", "from contextlib import ExitStack", '        stack = ExitStack()\n        inner = ExitStack()\n        stack.callback(inner.close)\n        stack.close()\n' + VALUE, "", True),
    ("node_state_scope", "from contextlib import ExitStack\nimport random", '        stack = ExitStack()\n        stack.callback(random.seed, 1)\n        stack.close()\n' + VALUE, "", True),
    ("node_callback_print", "from contextlib import ExitStack", '        stack = ExitStack()\n        stack.callback(print, "deferred output")\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_callback_open", "from contextlib import ExitStack", '        stack = ExitStack()\n        stack.callback(open, "artifact.txt", "w")\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_callback_open_implicit", "from contextlib import ExitStack", '        with ExitStack() as stack:\n            stack.callback(open, "artifact.txt", "w")\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_partial_open", "from contextlib import ExitStack\nfrom functools import partial", '        with ExitStack() as stack:\n            stack.callback(partial(open, "artifact.txt", "w"))\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_push_print", "from contextlib import ExitStack", '        with ExitStack() as stack:\n            stack.push(print)\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_callback_seed_pure", "from contextlib import ExitStack\nimport random", '        stack = ExitStack()\n        stack.callback(random.seed, 1)\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_bound_callback", "from contextlib import ExitStack", '        stack = ExitStack()\n        register = stack.callback\n        register(open, "artifact.txt", "w")\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_connection", "", '        connection = params.get("connection")\n        connection.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_reassigned", "from contextlib import ExitStack", '        stack = ExitStack()\n        stack = params.get("connection")\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_shadow", "from contextlib import ExitStack", '        ExitStack = params.get("factory")\n        stack = ExitStack()\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_branch_reassigned", "from contextlib import ExitStack", '        stack = ExitStack()\n        if params["cleanup_record_roots"]:\n            stack = params.get("connection")\n        stack.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("node_file", "", '        file = open("artifact.txt", "w")\n        file.close()\n' + VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("library_empty", "from contextlib import ExitStack", '    stack = ExitStack()\n    stack.close()\n    return 1', "", True),
    ("library_state_scope", "from contextlib import ExitStack\nimport random", '    stack = ExitStack()\n    stack.callback(random.seed, 1)\n    stack.close()\n    return 1', "", True),
    ("library_state_pure", "from contextlib import ExitStack\nimport random", '    random.seed(1)\n    stack = ExitStack()\n    stack.close()\n    return 1', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("library_callback_open", "from contextlib import ExitStack", '    stack = ExitStack()\n    stack.callback(open, "artifact.txt", "w")\n    stack.close()\n    return 1', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("library_callback_open_implicit", "from contextlib import ExitStack", '    with ExitStack() as stack:\n        stack.callback(open, "artifact.txt", "w")\n    return 1', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("library_callback_source_safe", "from contextlib import ExitStack", '    with ExitStack() as stack:\n        stack.callback(close)\n    return 1', "", True),
    ("library_callback_source_bad", "from contextlib import ExitStack", '    with ExitStack() as stack:\n        stack.callback(close)\n    return 1', "BASE_LIB.SIDE_EFFECT_CALL", False),
    ("class_field", "from contextlib import ExitStack", VALUE, "", True),
    ("class_field_reassigned", "from contextlib import ExitStack", VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("class_field_same_name", "from contextlib import ExitStack", VALUE, "NODE.EFFECT.CALL_FORBIDDEN", False),
    ("missing_output_branch", "", '        if params["cleanup_record_roots"]:\n            return {}\n' + VALUE, "NODE.PURITY.MISSING_OUTPUT", False),
    ("file_over_limit", "", VALUE, "BASE_LIB.SOURCE.MAX_LINES", False),
    ("readonly_deepcopy", "", VALUE, "RULE.EXECUTION", False),
)


def prepare(root, case):
    write_case(root, case)
    if case[0].startswith("library_callback_source_"):
        helper = root / "helper.py"
        body = '    return 1' if case[4] else '    open("artifact.txt", "w")'
        helper.write_text(helper.read_text() + '\n\ndef close():\n' + body + '\n')
    path = root / "plugin.py"
    code = path.read_text()
    if case[0].endswith("state_scope"):
        code = code.replace('rulesets=["vibeflow.process"]', 'rulesets=["vibeflow.global_state"]')
        if case[0].startswith("library_"):
            helper = root / "helper.py"
            library_rules = '''\nfrom vibeflow.targets.python.sdk import ruleset, RuleCall
state_library = ruleset(id="probe.state_library", calls=[
    RuleCall(id="effects", rule_id="vibeflow.no_side_effects", params={"effect_scope":"global_state"}),
    RuleCall(id="quality", rule_id="vibeflow.maintainability"),
    RuleCall(id="imports", rule_id="vibeflow.import_side_effects", params={"effect_scope":"global_state"}),
], entrypoints={"static":["effects","quality"],"run":["effects","quality"],"import":["imports"]})
'''
            helper.write_text(helper.read_text().replace('rulesets=["vibeflow.base_lib"]', 'rulesets=["probe.state_library"]') + library_rules)
            code = 'from helper import state_library\n' + code
            code = code.replace('inspection, helper]', 'inspection, helper, state_library]')
    if case[0].startswith("class_field"):
        implementation = '''class Defaults:
    def __init__(self):
        self.stack = None
    def _prepare(self, inputs, params):
        self.stack = ExitStack()
    def run_pure(self, inputs, params):
        self._prepare(inputs, params)
        self.stack.close()
'''+VALUE+'\n'
        if case[0] in {"class_field_reassigned", "class_field_same_name"}:
            implementation = implementation.replace('        self.stack.close()', '        self.stack = params.get("connection")\n        self.stack.close()')
        if case[0] == "class_field_same_name":
            implementation += '\n    def close(self):\n        return 1\n'
        start = code.index('class Defaults:')
        end = code.index('@node(type_key="probe.end"', start)
        code = code[:start] + implementation + '\n' + code[end:]
    if case[0] == "readonly_deepcopy":
        custom = '''\nfrom copy import deepcopy
from vibeflow.targets.python.sdk import rule, ruleset, RuleCall
from vibeflow.core.rules import RuleResult
@rule(id="probe.deepcopy")
def check(context, inputs, params):
    deepcopy(dict(context.subject["descriptor"].contract.params_defaults))
    return RuleResult()
inspection_rules = ruleset(id="probe.deepcopy", calls=[RuleCall(id="check",rule_id="probe.deepcopy")])
'''
        code = code.replace('"cleanup_record_roots": 1', '"cleanup_record_roots": {"nested": []}').replace("'integer'", "'object'")
        code = code.replace('rulesets=["vibeflow.process"]', 'rulesets=["probe.deepcopy"]')
        code = code.replace('plugin = Plugin(', custom + '\nplugin = Plugin(')
        code = code.replace('resources=[Start, Defaults, End, inspection]', 'resources=[Start, Defaults, End, inspection, check, inspection_rules]')
    path.write_text(code)


def observe(work, *, run=True):
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for case in CASES:
        root = work / case[0]
        prepare(root, case)
        validation = execute(root, "validate", work)
        errors = validation.get("diagnostics", [])
        target = [item for item in errors if item["code"] == case[3]]
        if "callback" in case[0] or case[0] in {"node_partial_open", "node_push_print"}:
            expected_name = "print" if "print" in case[0] else "random.seed" if "seed" in case[0] else "open"
            target = [item for item in target if expected_name in item["message"]]
        matched = validation["exit_code"] == 0 if case[4] else validation["exit_code"] == 1 and bool(target)
        if case[0] == "readonly_deepcopy":
            matched = matched and any("mappingproxy" in item["message"] for item in target)
        item = {"id":case[0],"expected_allowed":case[4],"expected_code":case[3],"validate":validation,"matched":matched}
        if run and case[0] in {"node_empty", "node_alias", "class_field", "library_state_scope"}:
            runtime = execute(root, "run", work) if validation["exit_code"] == 0 else {"exit_code":None}
            item["run"] = runtime
            item["matched"] = matched and runtime["exit_code"] == 0
        item["matched"] = item["matched"] and not (work / "artifact.txt").exists()
        results.append(item)
    return {"schema":"vibeflow.exit-stack-observation.v1", "cases":results,"matched":all(item["matched"] for item in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    parser.add_argument("--validate-only",action="store_true")
    args = parser.parse_args()
    report = observe(args.work.resolve(),run=not args.validate_only)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({"matched":report["matched"],"mismatches":[item["id"] for item in report["cases"] if not item["matched"]]}))
    return 0 if report["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
