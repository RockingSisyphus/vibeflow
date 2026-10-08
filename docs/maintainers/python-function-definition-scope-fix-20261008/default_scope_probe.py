#!/usr/bin/env python3
"""Independent default-argument scope observations through actual public paths.

Node/BaseLib/Plugin use the official Python validate CLI. Ordinary source uses
the public Core Rule compiler/executor with the product's native quality
binding. No source tests or private visitor are imported. Use one --source
snapshot or --kernel ZIP, or omit both for an installed wheel. Use a fresh
--work directory for each run.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.resources
import json
from pathlib import Path
import subprocess
import sys
import traceback


SCOPES = ("none", "terminal", "python_io")
KINDS = ("node", "base_lib", "plugin", "python_source")
POLICY = {"imports": {"allowed_roots": [], "banned_roots": [],
                       "allowed_modules": [], "banned_modules": []}}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _definition(attribute, alias, name="helper", *, parameter="sys", context=False, decorator=""):
    imported = "import sys\n" if alias == "sys" else "import sys as stream\n"
    parameters = "context, " if context else ""
    return imported + decorator + f"def {name}({parameters}{parameter}={alias}.{attribute}):\n    return 1\n"


def _attribute_location(path):
    text = path.read_text()
    target = next(n for n in ast.walk(ast.parse(text))
                  if isinstance(n, ast.Attribute) and n.attr in {"stdout", "argv"})
    return {"path": str(path), "line": target.lineno, "column": target.col_offset + 1}


def _project(path, kind, scope, attribute, alias, parameter):
    path.mkdir(parents=True)
    _write(path / "vibeflow_config.jsonc", {"roots": [{"id": "default-scope", "path": "."}]})
    _write(path / "vibeflow_project.jsonc", {"project_target": "python"})
    _write(path / "workflow.jsonc", {
        "plugins": [{"source": {"kind": "file", "ref": "plugin.py"}}],
        "rulesets": [], "pipeline": {
            "inputs": [], "outputs": [],
            "nodes": [
                {"id": "start", "type_used": "probe.start", "display_name": "Start", "description": "Starts the probe."},
                {"id": "task", "type_used": "probe.task", "display_name": "Task", "description": "Checks the actual resource source."},
                {"id": "end", "type_used": "probe.start", "display_name": "End", "description": "Ends the probe."}],
            "edges": [["start", "task"], ["task", "end"]]}})
    selected = ("selected = ruleset(id='probe.default_effects', calls=["
                + repr({"id": "effects", "rule_id": "vibeflow.no_side_effects",
                        "params": {"effect_scope": scope, "policy": POLICY}})
                + "], entrypoints={'static':['effects']})\n")
    node_header = "from vibeflow.targets.python.sdk import node\n"
    start = ("\n@node(type_key='probe.start', flow_kind='terminal', rulesets=[], contract={})\n"
             "class Start:\n    def run_pure(self, inputs, params):\n        return {}\n")
    task = ("\n@node(type_key='probe.task', rulesets="
            + ("['probe.default_effects']" if kind == "node" else "[]")
            + (", base_libs=['probe.library']" if kind == "base_lib" else "")
            + ", contract={})\nclass Task:\n    def run_pure(self, inputs, params):\n")
    if kind == "node":
        node_text = node_header + _definition(attribute, alias, parameter=parameter) + task + "        helper()\n        return {}\n" + start
        offender = path / "node_resource.py"
    elif kind == "base_lib":
        node_text = node_header + "from library import calculate\n" + task + "        calculate()\n        return {}\n" + start
        library = ("from vibeflow.targets.python.sdk import base_lib\n"
                   + _definition(attribute, alias, "calculate", parameter=parameter,
                                 decorator="@base_lib(id='probe.library', rulesets=['probe.default_effects'])\n"))
        offender = path / "library.py"
        offender.write_text(library)
    else:
        node_text = node_header + task + "        return {}\n" + start
        runtime = ("import sys\n" if alias == "sys" else "import sys as stream\n")
        runtime += (f"def create_runtime(context, {parameter}={alias}.{attribute}):\n"
                    "    return Runtime()\n\nclass Runtime:\n    pass\n")
        offender = path / "runtime_resource.py"
        offender.write_text(runtime)
    (path / "node_resource.py").write_text(node_text)
    imports = "from vibeflow.targets.python.sdk import Plugin, ruleset\nfrom node_resource import Start, Task\n"
    resources = "[Start, Task, selected]"
    options = ""
    if kind == "base_lib":
        imports += "from library import calculate\n"
        resources = "[Start, Task, calculate, selected]"
    if kind == "plugin":
        imports += "from runtime_resource import create_runtime\n"
        options = ", runtime=create_runtime, rulesets=['probe.default_effects']"
    (path / "plugin.py").write_text(imports + selected
        + f"plugin = Plugin(id='probe', resources={resources}{options}, declaration_rulesets=[])\n")
    return offender


def _diagnostics(payload):
    findings = []
    def walk(value):
        if isinstance(value, dict):
            if value.get("definition_id") == "vibeflow.no_side_effects" and (
                "source_location" in value or "source" in value
            ) and value not in findings:
                findings.append(value)
            for key, item in value.items():
                if key not in {"source_code", "definitions", "resources", "expected"}:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)
    return findings


def _effective_calls(payload):
    calls = []
    def walk(value):
        if isinstance(value, dict):
            if value.get("rule_id") == "vibeflow.no_side_effects" and "params" in value:
                calls.append(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)
    return calls


def _run(args, report):
    wheel = None
    if args.kernel:
        product = args.kernel.resolve(strict=True)
    elif args.source:
        product = args.source.resolve(strict=True)
    else:
        wheel = importlib.metadata.distribution("vibeflow")
        if wheel.read_text("WHEEL") is None:
            raise ValueError("Wheel mode requires installed WHEEL metadata")
        direct = json.loads(wheel.read_text("direct_url.json") or "{}")
        if direct.get("dir_info", {}).get("editable"):
            raise ValueError("Wheel mode requires a non-editable product install")
        product = Path(wheel.locate_file("")).resolve(strict=True)
    sys.path.insert(0, str(product))
    import vibeflow
    from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
    from vibeflow.targets.python.quality import PythonSource
    from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context
    from vibeflow.targets.shared.bindings import native_binding
    from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
    expected_root = str(product / "vibeflow") + "/"
    assert str(vibeflow.__file__).startswith(expected_root), vibeflow.__file__
    report["product"] = {"kind": "kernel_zip" if args.kernel else "wheel" if wheel else "source_snapshot",
                         "path": str(product), "origin": str(vibeflow.__file__)}
    if args.kernel:
        report["product"]["sha256"] = hashlib.sha256(product.read_bytes()).hexdigest()
    if wheel:
        report["product"]["version"] = wheel.version
        report["product"]["wheel_metadata"] = wheel.read_text("WHEEL")
    analysis_resource = importlib.resources.files("vibeflow.targets.python.quality")
    def analysis_hashes():
        return {name: hashlib.sha256(analysis_resource.joinpath(name).read_bytes()).hexdigest()
                for name in ("source_analysis/bindings.py", "source_analysis/visitors.py",
                             "source_analysis/input_tracking.py", "rules/base_lib_effects.py", "rules/effects.py", "source_context.py")}
    report["source_analysis_sha256"] = analysis_hashes()
    catalog = load_builtin_plugins("python").catalogs
    rules = {item.id: item for item in catalog.rules}
    handlers = {item.id: native_binding(catalog, "rule", item.id) for item in catalog.rules}
    rows = report["observations"]
    for kind in KINDS:
        for attribute in ("stdout", "argv"):
            for scope in SCOPES:
                for alias, parameter in (("sys", "sys"), ("stream", "sys"), ("sys", "stream")):
                    name = ".".join((kind, attribute, scope, alias, parameter))
                    case = args.work.resolve() / name
                    should_diagnose = attribute == "argv" or scope == "none"
                    if kind != "python_source":
                        offender = _project(case, kind, scope, attribute, alias, parameter)
                        argv = ["validate", "--workspace", str(case / "vibeflow_config.jsonc"),
                                "--config", str(case / "workflow.jsonc"), "--json"]
                        bootstrap = ("import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
                                     "from vibeflow.tooling.application.python.cli import main;"
                                     "code=main(json.loads(sys.argv[2]));"
                                     "modules={name:str(getattr(module,'__file__','')) for name,module in sys.modules.items() if name=='vibeflow' or name.startswith('vibeflow.')};"
                                     "expected=str(Path(sys.argv[1])/'vibeflow')+'/';"
                                     "foreign={name:path for name,path in modules.items() if path and not path.startswith(expected)};"
                                     "Path(sys.argv[3]).write_text(json.dumps({'origin':modules['vibeflow'],'loaded_module_count':len(modules),'foreign_product_modules':foreign}));"
                                     "raise SystemExit(code)")
                        process = subprocess.run([sys.executable, "-I", "-B", "-c", bootstrap,
                                                  str(product), json.dumps(argv), str(case / "product-origin.json")],
                                                 cwd=case, text=True, capture_output=True, timeout=30)
                        (case / "stdout.txt").write_text(process.stdout)
                        (case / "stderr.txt").write_text(process.stderr)
                        try:
                            payload = json.loads(process.stdout)
                        except json.JSONDecodeError:
                            raise RuntimeError(f"CLI had no JSON payload for {name}: {process.stdout} / {process.stderr}")
                        _write(case / "cli.json", payload)
                        findings = _diagnostics(payload)
                        entrypoint = "vibeflow.tooling.application.python.cli.main(validate)"
                        status = payload.get("status")
                        exit_code = process.returncode
                        calls = _effective_calls(payload)
                        assert all(call["params"]["effect_scope"] == scope for call in calls), calls
                        # Python validate serializes Node/BaseLib plans in
                        # effective_policy, but does not serialize Plugin plans.
                        # Preserve that absence instead of inventing a trace.
                        effective = calls[0]["params"] if calls else None
                        cli_product = json.loads((case / "product-origin.json").read_text())
                        assert not cli_product["foreign_product_modules"], cli_product
                    else:
                        case.mkdir(parents=True)
                        offender = case / "ordinary.py"
                        offender.write_text(_definition(attribute, alias, parameter=parameter))
                        source = PythonSource("ordinary", "ordinary.py", str(offender), offender.read_text())
                        file = PythonSourceFile.parse(str(offender), "ordinary", source.text)
                        context = RuleContext(subject={"kind": "python_source", "id": "ordinary.py"},
                            facts={"python_source": source, "source_file": file,
                                   "python_sources": ((source, file),),
                                   "source_context": build_python_source_context((), (file,))},
                            target="python")
                        selected = RulesetDescriptor("probe.default_effects", calls=(
                            RuleCall("effects", rule_id="vibeflow.no_side_effects",
                                     params={"effect_scope": scope, "policy": POLICY}),))
                        plan = complete_source_policy_plan(
                            compile_ruleset(selected, rules=rules, rulesets={selected.id: selected}),
                            handlers=handlers)
                        result = execute_rule_plan(plan, context, handlers=handlers)
                        payload = result.to_dict()
                        _write(case / "quality.json", payload)
                        findings = payload["findings"]
                        entrypoint = "public Core compile_ruleset/execute_rule_plan native PythonSource binding"
                        status, exit_code = result.status, None
                        effective = payload["plan"]["calls"][0]["params"]
                        cli_product = None
                    location = _attribute_location(offender)
                    # Findings at exactly the default expression are the evidence;
                    # unrelated interface/import findings cannot hide the scope bug.
                    matching = [f for f in findings if f.get("source_location") == location]
                    expected_status = ("CONCERNS" if kind == "python_source" else "FAIL") if should_diagnose else "PASS"
                    status_match = status == expected_status and (exit_code is None or exit_code == (1 if should_diagnose else 0))
                    rows.append({"case": name, "kind": kind, "attribute": attribute,
                                 "default_parameter": parameter, "global_import_alias": alias,
                                 "scope": scope, "rule_id": "vibeflow.no_side_effects",
                                 "authored_params": {"effect_scope": scope, "policy": POLICY},
                                 "effective_params": effective, "entrypoint": entrypoint,
                                 "expected_diagnostic": should_diagnose,
                                 "actual_default_diagnostic": bool(matching),
                                 "semantic_match": bool(matching) == should_diagnose and status_match,
                                 "expected_status": expected_status, "public_status_match": status_match,
                                 "status": status, "exit_code": exit_code,
                                 "expected_location": location, "findings": findings,
                                 "matching_default_findings": matching})
                    rows[-1]["cli_product"] = cli_product
    modules = {name: str(getattr(module, "__file__", "")) for name, module in sys.modules.items()
               if name == "vibeflow" or name.startswith("vibeflow.")}
    foreign = {name: path for name, path in modules.items() if path and not path.startswith(expected_root)}
    report["source_analysis_sha256_after"] = analysis_hashes()
    assert report["source_analysis_sha256"] == report["source_analysis_sha256_after"], "Selected product changed during probe"
    report["loaded_product_module_count"] = len(modules)
    report["foreign_product_modules"] = foreign
    assert not foreign, foreign
    pairs, parameter_pairs = [], []
    for kind in KINDS:
        for attribute in ("stdout", "argv"):
            for scope in SCOPES:
                variants = [r for r in rows if r["kind"] == kind and r["attribute"] == attribute and r["scope"] == scope]
                same = next(r for r in variants if r["global_import_alias"] == "sys" and r["default_parameter"] == "sys")
                renamed = next(r for r in variants if r["global_import_alias"] == "stream" and r["default_parameter"] == "sys")
                pairs.append({"kind": kind, "attribute": attribute, "scope": scope,
                              "same_parameter_name_diagnosed": same["actual_default_diagnostic"],
                              "renamed_import_diagnosed": renamed["actual_default_diagnostic"],
                              "equal_judgment": same["actual_default_diagnostic"] == renamed["actual_default_diagnostic"]})
                renamed_parameter = next(r for r in variants if r["global_import_alias"] == "sys" and r["default_parameter"] == "stream")
                parameter_pairs.append({"kind": kind, "attribute": attribute, "scope": scope,
                                        "same_parameter_name_diagnosed": same["actual_default_diagnostic"],
                                        "renamed_parameter_diagnosed": renamed_parameter["actual_default_diagnostic"],
                                        "equal_judgment": same["actual_default_diagnostic"] == renamed_parameter["actual_default_diagnostic"]})
    report["alias_comparisons"] = pairs
    report["parameter_comparisons"] = parameter_pairs
    report["summary"] = {"cases": len(rows), "semantic_matches": sum(r["semantic_match"] for r in rows),
                         "semantic_mismatches": sum(not r["semantic_match"] for r in rows),
                         "unequal_alias_pairs": sum(not p["equal_judgment"] for p in pairs),
                         "unequal_parameter_pairs": sum(not p["equal_judgment"] for p in parameter_pairs),
                         "original_matrix_cases": sum(r["default_parameter"] == "sys" for r in rows),
                         "renamed_parameter_cases": sum(r["default_parameter"] == "stream" for r in rows)}
    report["expected_state_observed"] = (report["summary"]["semantic_mismatches"] == 0
                                         if args.expect == "fixed"
                                         else report["summary"]["unequal_alias_pairs"] > 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    product = parser.add_mutually_exclusive_group()
    product.add_argument("--source", type=Path, help="Unique checkout source snapshot root containing vibeflow/.")
    product.add_argument("--kernel", type=Path, help="Unique generated kernel ZIP.")
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--expect", choices=("vulnerable", "fixed"), required=True)
    args = parser.parse_args()
    report = {"expected_state": args.expect, "observations": [], "probe_error": None}
    report["probe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        _run(args, report)
    except Exception:
        report["probe_error"] = traceback.format_exc()
        report["expected_state_observed"] = False
    _write(args.report.resolve(), report)
    print(json.dumps({key: report.get(key) for key in
                      ("expected_state", "expected_state_observed", "summary", "probe_error")}, ensure_ascii=False))
    return 0 if report["expected_state_observed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
