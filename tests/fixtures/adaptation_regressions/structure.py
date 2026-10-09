"""Registered source relationships use resource ownership, not directory names."""

from pathlib import Path

from tests.fixtures.adaptation_regressions.common import row, run_cli, write_json


CONTRACT = {"provides": [{"key": "result", "type": "number", "display_name": "Result"}],
            "output_semantics": {"result": ["The calculated result."]}}


def write(root, relative, source):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def fixture(root, kind="node", *, registered=True, conventional=False):
    root.mkdir(parents=True)
    write_json(root / "vibeflow_project.jsonc", {"project_target": "python"})
    write_json(root / "vibeflow_config.jsonc", {"roots": [{"id": "p", "path": "."}]})
    directory = "base_lib" if conventional else "parts"
    write(root, directory + "/util.py", "def value():\n    return 7\n")
    leaf_import = f"from {directory}.util import value\n"
    definitions = ["from vibeflow.targets.python.sdk import Plugin,node,base_lib,lifecycle,SourceLocator"]
    resources = ["leaf"]
    support = f",implementation_files=['../{directory}/util.py']" if registered else ""
    base_refs = ""
    if kind == "base_lib":
        write(root, "libraries/entry.py", leaf_import + "def result():\n    return value()\n")
        leaf_import = "from libraries.entry import result as value\n"
        definitions.append("library=base_lib(id='audit.library',rulesets=['vibeflow.base_lib'],"
            "source=SourceLocator('file','libraries/entry.py','result')" + support + ")")
        resources.append("library")
        support = ""
        base_refs = ",base_libs=['audit.library']"
    if kind == "declaration":
        write(root, "nodes/leaf.py", "from vibeflow.targets.python.sdk import node\n"
            + f"@node(type_key='audit.leaf',contract={CONTRACT!r},rulesets=[])\n"
            + "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':7}\n")
        definitions.append("from nodes.leaf import Leaf\nleaf=Leaf")
    else:
        write(root, "nodes/leaf.py", leaf_import
            + "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':value()}\n")
        definitions.append(f"leaf=node(type_key='audit.leaf',contract={CONTRACT!r},rulesets=['vibeflow.process'],"
            "source=SourceLocator('file','nodes/leaf.py','Leaf')" + support + base_refs + ")")
    definitions.append("plugin=Plugin(id='audit.resources',resources=[" + ",".join(resources)
        + "],declaration_rulesets=['vibeflow.plugin_declaration'])")
    write(root, "plugins/entry.py", "\n".join(definitions) + "\n")
    (root / "configs").mkdir()
    write_json(root / "configs/workflow.jsonc", {"plugins": [{"source": {"kind": "file", "ref": "plugins/entry.py"}}],
        "rulesets": [], "pipeline": {"nodes": [{"id": "leaf", "type_used": "audit.leaf",
        "display_name": "Leaf", "description": "Read the declared implementation."}]}})


def findings(payload):
    if not isinstance(payload, dict):
        return []
    result = []
    for key in ("errors", "warnings", "findings"):
        result.extend(payload.get(key, ()))
    for key in ("source_quality", "health", "validation"):
        if isinstance(payload.get(key), dict):
            result.extend(findings(payload[key]))
    for item in payload.get("reports", ()):
        result.extend(findings(item))
    return result


def observe(work: Path, kernel: Path, toolchain=None, renderer=None):
    observations = []
    variants = (("node-support", "node", True, False),
                ("node-support-conventional", "node", True, True),
                ("node-unregistered", "node", False, False),
                ("library-support", "base_lib", True, False),
                ("library-unregistered", "base_lib", False, False),
                ("declaration-contribution", "declaration", True, False))
    for identifier, kind, registered, conventional in variants:
        project = work / identifier
        fixture(project, kind, registered=registered, conventional=conventional)
        for command in ("validate", "quality-check"):
            args = [command, "--json"]
            args += (["--config", str(project / "configs/workflow.jsonc")] if command == "validate"
                     else ["--workspace", str(project / "vibeflow_config.jsonc")])
            observed = run_cli(project, args, kernel, name=command)
            diagnostics = findings(observed["payload"])
            codes = sorted({str(item.get("code", item.get("rule_id", ""))) for item in diagnostics
                            if item.get("severity") == "error"})
            actual = {"exit_code": observed["exit_code"], "codes": codes,
                      "diagnostics": diagnostics, "stdout_path": observed["stdout_path"]}
            expected = {"exit_code": 0 if registered else 1}
            failures = []
            if actual["exit_code"] != expected["exit_code"]:
                failures.append(f"expected exit {expected['exit_code']}, got {actual['exit_code']}: {codes}")
            if registered and codes:
                failures.append("registered relationship was rejected: " + repr(codes))
            if not registered and not any(code in {"VF_IMPORT_OWNER", "VF_IMPORT_LAYER",
                    "QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT",
                    "QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT"} for code in codes):
                failures.append("missing the targeted ownership diagnostic")
            observations.append(row("A05.python." + identifier + "." + command, "A05",
                "Declared Python source relationship: " + identifier, expected, actual, failures, project))
    from tests.fixtures.adaptation_regressions.structure_extra import observe as observe_extra
    observations.extend(observe_extra(work / "extra",kernel,toolchain,renderer))
    return observations
