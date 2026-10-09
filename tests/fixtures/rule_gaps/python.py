"""Current-kernel checks for source selection and planned helper boundaries."""

from __future__ import annotations

import importlib.util
from pathlib import Path


PURE_NODE = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n'
PURE_BOUNDARY = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {}\n'
IMPORT_MARKER = 'open(__MARKER__, "w").write("node imported")\n'
PURE_HELPER = 'def transform(value):\n    return value + 1\n'
UNSAFE_HELPER = ('def transform(value):\n'
                 '    open(__MARKER__, "w").write("helper ran")\n'
                 '    return value + 1\n')
HELPER_NODE = ('from helper import transform\nclass DemoNode:\n'
               '    def run_pure(self, inputs, params):\n'
               '        return {"demo.out": transform(1)}\n')
HELPER_BOUNDARY = ('from helper import transform\nclass DemoNode:\n'
                   '    def run_pure(self, inputs, params):\n'
                   '        transform(1)\n        return {}\n')
PURE_STUB = 'def run_stub(inputs, params):\n    return {"demo.out": 2}\n'
HELPER_STUB = ('from stubs.helper import transform\n'
               'def run_stub(inputs, params):\n    return {"demo.out": transform(1)}\n')


def _expected(accept, *, marker="", code=None, metrics=None):
    result = {"should_accept": accept, "codes": [],
              "metrics": {"marker": marker, "exit_code": 0 if accept else 1,
                          "runtime_completed": accept, **(metrics or {})}}
    if code:
        result["codes"] = [{"code": code, "severity": "error"}]
        result["located_codes"] = [code]
    if accept:
        result["metrics"]["runtime_exec_order"] = ["start", "demo", "end"]
        result["metrics"]["runtime_output_keys"] = ["demo.out"]
    return result


def _case(name, title, family, expected, **options):
    return {"id": "python.gaps." + name, "title": title, "family": family,
            "classification": "new_feature", "expected": expected, **options}


def case_specs():
    independent = {"physical_imports": [],
                   "node_paths": {"parity.node": "node.py", "parity.start": "start.py", "parity.end": "end.py"},
                   "helper_owners": []}
    both_owners = ["parity.node", "parity.start"]
    shared = {"source": HELPER_NODE, "start_source": HELPER_BOUNDARY,
              "rulesets": ["vibeflow.process"], "start_rulesets": ["vibeflow.process"]}
    return [
        _case("independent_empty", "Independent unchecked module may initialize and run", "node-import-isolation",
              _expected(True, marker="node imported", metrics=independent), source=IMPORT_MARKER + PURE_NODE),
        _case("independent_selected_sibling", "A selected Node import rule cannot constrain an unrelated unchecked module", "node-import-isolation",
              _expected(True, marker="node imported", metrics=independent), source=IMPORT_MARKER + PURE_NODE,
              start_rulesets=["vibeflow.process"],
              notes="Known gap: current import rule scans all workflow files and attributes node.py to start.py, although the files have no imports or shared ownership."),
        _case("independent_selected_own", "The same module initialization is rejected by its own selected rule", "node-import-isolation",
              _expected(False, code="NODE.IMPORT.SIDE_EFFECT", metrics={**independent,
                        "error_owner_types": ["parity.node"], "error_source_files": ["node.py"]}),
              source=IMPORT_MARKER + PURE_NODE, rulesets=["vibeflow.process"]),
        _case("shared_pure", "Two selected Nodes may call a shared pure helper", "helper-ownership",
              _expected(True, metrics={"helper_owners": both_owners}), helper_source=PURE_HELPER, **shared),
        _case("shared_unsafe", "Shared helper effects are rejected and associated with both actual callers", "helper-ownership",
              _expected(False, code="NODE.EFFECT.CALL_FORBIDDEN", metrics={"helper_owners": both_owners,
                        "error_owner_types": both_owners, "error_source_files": ["helper.py"]}),
              helper_source=UNSAFE_HELPER, **shared),
        _case("shared_one_selected", "One selected caller still checks a helper shared with an unchecked caller", "helper-ownership",
              _expected(False, code="NODE.EFFECT.CALL_FORBIDDEN", metrics={"helper_owners": both_owners,
                        "error_owner_types": ["parity.start"], "error_source_files": ["helper.py"]}),
              source=HELPER_NODE, start_source=HELPER_BOUNDARY, helper_source=UNSAFE_HELPER,
              start_rulesets=["vibeflow.process"]),
        _case("unshared_unchecked_helper", "An unchecked caller's helper is outside an unrelated selected Node's ownership", "helper-ownership",
              _expected(True, marker="helper ran", metrics={"helper_owners": ["parity.node"]}),
              source=HELPER_NODE, helper_source=UNSAFE_HELPER, start_rulesets=["vibeflow.process"]),
        _case("planned_main_pure", "A pure planned stub main file executes under the explicit development option", "planned-helper-closure",
              _expected(True), stub_source=PURE_STUB, classification="preserved"),
        _case("planned_main_unsafe", "A planned stub main-file initialization is rejected before its marker", "planned-helper-closure",
              _expected(False, code="GRAPH.PLANNED.STUB_TOP_LEVEL", metrics={"error_source_files": ["stubs/work.py"]}),
              stub_source=IMPORT_MARKER + PURE_STUB, classification="preserved"),
        _case("planned_helper_pure", "A planned stub may import and execute a pure local helper", "planned-helper-closure",
              _expected(True), stub_source=HELPER_STUB, stub_helper_source=PURE_HELPER, classification="baseline_limitation"),
        _case("planned_helper_unsafe", "A planned stub helper initialization must be rejected before its marker", "planned-helper-closure",
              _expected(False, code="GRAPH.PLANNED.STUB_TOP_LEVEL", metrics={"error_source_files": ["stubs/helper.py"]}),
              stub_source=HELPER_STUB, stub_helper_source=IMPORT_MARKER + PURE_HELPER,
              classification="baseline_limitation",
              notes="Known old/new limitation: only the main stub file is checked. The helper marker must remain empty; the current behavior is recorded as a failing expectation."),
    ]


def run_cases(work_root: Path, variant: str = "current", toolchain_root: Path | None = None) -> list[dict]:
    if variant != "current":
        raise ValueError("rule_gaps Python cases only evaluate the current kernel")
    location = Path(__file__).with_name("python_support.py")
    specification = importlib.util.spec_from_file_location("rule_gaps_python_support", location)
    support = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(support)
    return [support.observe(work_root, spec) for spec in case_specs()]
