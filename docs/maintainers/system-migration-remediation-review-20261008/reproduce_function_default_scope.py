"""Static-only review probe: function defaults use their enclosing scope.

Run with PYTHONPATH=src, or python -I ... --kernel <vibeflow-kernel.zip>.
No inspected source is imported or executed. Nonzero exit reports mismatches.
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

    cases = [
        ("shadowed_stdout_default", "none", "def helper(sys=sys.stdout):\n    return sys\n", True),
        ("renamed_stdout_default", "none", "def helper(stream=sys.stdout):\n    return stream\n", True),
        ("renamed_argv_default", "none", "def helper(arguments=sys.argv):\n    return arguments\n", True),
        ("body_local_only", "none", "def helper(sys):\n    return sys.stdout\n", False),
        ("body_import_shadows_default", "none", "def helper(stream=sys.stdout):\n    import sys\n    return stream\n", True),
    ]
    cases.extend(("shadowed_argv_default", scope, "def helper(sys=sys.argv):\n    return sys\n", True)
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
