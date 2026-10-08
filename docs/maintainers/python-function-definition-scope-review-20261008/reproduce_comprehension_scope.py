"""Static-only comprehension-scope and input-ownership review probes.

Use PYTHONPATH=src or python -I ... --kernel <ZIP>. Inspected code is parsed,
never imported or executed. Nonzero exit reports semantic mismatches. Cases
include earlier false positives and valid local-object controls, so compare
per-case results between products rather than treating every mismatch as new.
"""

import argparse
import json
from pathlib import Path
import sys
from textwrap import indent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.kernel:
        sys.path.insert(0, str(args.kernel.resolve()))
    import vibeflow
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality import PythonSource
    from vibeflow.targets.python.quality.rules.effects import no_side_effects
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context

    cases = []
    for scope in ("none", "terminal", "python_io", "global_state", "trusted"):
        for label, expression in [
            ("control_no_comprehension", "sys.argv"),
            ("control_different_target", "(sys.argv, [item for item in ()])"),
            ("list_target_shadows_lambda", "(sys.argv, [sys for sys in ()])"),
            ("set_target_shadows_lambda", "(sys.argv, {sys for sys in ()})"),
            ("dict_target_shadows_lambda", "(sys.argv, {sys: sys for sys in ()})"),
            ("generator_target_shadows_lambda", "(sys.argv, (sys for sys in ()))"),
            ("outer_iterable", "[sys for sys in sys.argv]"),
        ]:
            cases.append((label, scope, "def helper():\n    return (lambda: " + expression + ")()\n", True))
    cases.extend(("comprehension_body_local_control", scope,
                  "def helper():\n    return (lambda: [sys.argv for sys in ()])()\n", False)
                 for scope in ("none", "terminal", "python_io", "global_state", "trusted"))
    rows = []
    for label, scope, body, expected in cases:
        for kind in ("python_source", "node", "base_lib", "plugin"):
            nodes = ()
            text = "import sys\n" + body
            if kind == "node":
                text = "import sys\nclass Task:\n" + indent(body.replace("def helper(", "def _helper(self, "), "    ")
                text += "    def run_pure(self, inputs, params):\n        return {}\n"
                descriptor = NodeDescriptor("probe.task", "Scope probe", "Checks function-default scope.", "1", "process", contract=NodeContractDescriptor())
                nodes = (PythonSourceNode(descriptor, "/virtual/entry.py", "Task"),)
            source = PythonSourceFile.parse("/virtual/entry.py", "entry", text)
            sources = build_python_source_context(nodes, (source,))
            facts = {"source_context": sources, "node_catalog": (), "resource_symbol": "",
                     "source_owners": ({"kind": kind, "id": "probe.task", "role": "entry", "path": source.path, "symbol": "Task" if kind == "node" else ""},),
                     "base_lib_file": source, "resource_source_file": source,
                     "python_source": PythonSource("entry", "entry.py", source.path, text), "source_file": source}
            result = no_side_effects(RuleContext(subject={"kind": kind, "id": "probe.task", "type_key": "probe.task"}, target="python", facts=facts), {}, {"effect_scope": scope})
            rows.append({"case": label, "scope": scope, "kind": kind, "source": text,
                         "expected_findings": expected, "actual_findings": bool(result.findings), "state": result.state,
                         "matched": result.state == "completed" and bool(result.findings) == expected,
                         "findings": [item.to_dict() for item in result.findings]})
    for placement in ("method", "helper"):
        for label, expression in [
            ("input_control", "inputs.pop('seed', None)"),
            ("input_different_target", "(inputs.pop('seed', None), [item for item in ()])"),
            ("input_list_same_target", "(inputs.pop('seed', None), [inputs for inputs in ()])"),
            ("input_set_same_target", "(inputs.pop('seed', None), {inputs for inputs in ()})"),
            ("input_dict_same_target", "(inputs.pop('seed', None), {inputs: inputs for inputs in ()})"),
            ("input_generator_same_target", "(inputs.pop('seed', None), (inputs for inputs in ()))"),
        ]:
            statements = "fn = lambda: " + expression + "\nfn()\n"
            text = "class Task:\n    def run_pure(self, inputs, params):\n" + indent(statements + "return {}\n", "        ")
            if placement == "helper":
                text = "def helper(inputs):\n" + indent(statements, "    ") + "\nclass Task:\n    def run_pure(self, inputs, params):\n        helper(inputs)\n        return {}\n"
            descriptor = NodeDescriptor("probe.task", "Scope probe", "Checks comprehension/input scope.", "1", "process", contract=NodeContractDescriptor())
            source = PythonSourceFile.parse("/virtual/owned.py", "owned", text)
            sources = build_python_source_context((PythonSourceNode(descriptor, source.path, "Task"),), (source,))
            facts = {"source_context": sources, "node_catalog": (), "source_owners": ()}
            result = no_side_effects(RuleContext(subject={"kind": "node", "type_key": "probe.task"}, target="python", facts=facts), {}, {"effect_scope": "global_state"})
            actual = any("mutate inputs" in finding.message for finding in result.findings)
            rows.append({"case": label, "placement": placement, "scope": "global_state", "kind": "node", "source": text,
                         "expected_findings": True, "actual_findings": actual, "state": result.state,
                         "matched": result.state == "completed" and actual,
                         "findings": [item.to_dict() for item in result.findings]})
    for label, expression in [("pure_close_control", "(close(), [item for item in ()])"),
                              ("pure_close_same_target", "(close(), [close for close in ()])")]:
        for kind in ("python_source", "node", "base_lib", "plugin"):
            text = "from helper import close\ndef task():\n    return (lambda: " + expression + ")()\n"
            text += "class Task:\n    def run_pure(self, inputs, params):\n        task()\n        return {}\n"
            entry = PythonSourceFile.parse("/virtual/entry.py", "entry", text)
            helper = PythonSourceFile.parse("/virtual/helper.py", "helper", "def close():\n    return 1\n")
            descriptor = NodeDescriptor("probe.task", "Scope probe", "Checks real helper call scope.", "1", "process", contract=NodeContractDescriptor())
            nodes = (PythonSourceNode(descriptor, entry.path, "Task"),) if kind == "node" else ()
            sources = build_python_source_context(nodes, (entry, helper))
            facts = {"source_context": sources, "node_catalog": (), "resource_symbol": "",
                     "source_owners": tuple({"kind": kind, "id": "probe.task", "role": "entry" if source is entry else "support", "path": source.path, "symbol": ""} for source in (entry, helper)),
                     "base_lib_file": entry, "resource_source_file": entry,
                     "python_sources": tuple((PythonSource(source.module, source.module + ".py", source.path, source.text), source) for source in (entry, helper))}
            result = no_side_effects(RuleContext(subject={"kind": kind, "id": "probe.task", "type_key": "probe.task"}, target="python", facts=facts), {}, {"effect_scope": "none"})
            rows.append({"case": label, "scope": "none", "kind": kind, "source": text,
                         "expected_findings": False, "actual_findings": bool(result.findings), "state": result.state,
                         "matched": result.state == "completed" and not result.findings,
                         "findings": [item.to_dict() for item in result.findings]})
    report = {"product_origin": vibeflow.__file__, "cases": rows, "count": len(rows),
              "mismatches": sum(not row["matched"] for row in rows)}
    if args.kernel:
        assert str(vibeflow.__file__).startswith(str(args.kernel.resolve()) + "/"), vibeflow.__file__
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    return 1 if report["mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
