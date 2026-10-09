"""Replay frozen F05 finding controls through one isolated selected product.

Prepare the input-only JSON once with stdlib AST literal_eval. Replay never
imports tests, pytest, their helpers, or the inspected business definitions.
"""
from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from textwrap import indent
import zipfile


TEST_NAMES = (
    "tests/targets/python/test_input_exception_states.py",
    "tests/targets/python/test_source_parameter_facts.py",
)
MUTATION_TOKEN = "__F05_MUTATION__"
BETWEEN_TOKEN = "__F05_BETWEEN_INDENTED__"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [plain(item) for item in value]
    return value


def function(tree, name):
    return next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)


def assignment(scope, name):
    return next(item.value for item in scope.body if isinstance(item, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in item.targets))


def parameters(scope, name):
    decorator = next(item for item in scope.decorator_list if isinstance(item, ast.Call)
                     and isinstance(item.func, ast.Attribute) and item.func.attr == "parametrize"
                     and ast.literal_eval(item.args[0]) == name)
    return ast.literal_eval(decorator.args[1])


def template(expression):
    """Read only literal string assembly used by the two captured controls."""
    if isinstance(expression, ast.Constant):
        value = ast.literal_eval(expression)
        if isinstance(value, str):
            return value
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        return template(expression.left) + template(expression.right)
    if isinstance(expression, ast.Name) and expression.id == "mutation":
        return MUTATION_TOKEN
    if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name)
            and expression.func.id == "_mutation" and len(expression.args) == 1
            and isinstance(expression.args[0], ast.Name) and expression.args[0].id == "via_helper"):
        return "MUTATION"
    if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name)
            and expression.func.id == "indent" and len(expression.args) == 2
            and isinstance(expression.args[0], ast.Name) and expression.args[0].id == "between"
            and ast.literal_eval(expression.args[1]) == "        "):
        return BETWEEN_TOKEN
    raise ValueError("unsupported frozen capture string assembly")


def prepare(repo, data_path):
    if data_path.exists():
        raise ValueError("frozen data exists; preserve it and choose a new output")
    paths = [repo / name for name in TEST_NAMES]
    before = {name: sha(path) for name, path in zip(TEST_NAMES, paths)}
    original, metadata = [ast.parse(path.read_text(), filename=str(path)) for path in paths]
    tables = {}
    for tree, names in ((original, ("ORIGINAL_CASES", "ARGUMENT_CASES", "ADJACENT_CASES")),
                        (metadata, ("EXCEPTION_CONTROLS", "DELETED_CALLEE_CONTROLS",
                                    "BOUND_EVALUATION_CONTROLS", "CAPTURED_DICTIONARY_CONTROLS"))):
        for name in names:
            tables[name] = ast.literal_eval(assignment(tree, name))
            for label, body, expected in tables[name]:
                if not isinstance(label, str) or not isinstance(body, str) or type(expected) is not bool:
                    raise ValueError("invalid literal finding control: " + name)
    cases = []
    original_prefix = ast.literal_eval(assignment(function(original, "_review"), "prefix"))
    metadata_prefix = ast.literal_eval(assignment(function(metadata, "_review_exception_control"), "prefix"))

    def add(group, label, body, expected, helper, placement, prefix, proof=None):
        if type(expected) is not bool:
            raise ValueError("a finding expectation must be the original literal bool")
        mutation = 'sink(alias)' if helper else 'alias.pop("seed", None)'
        text_body = body.replace("MUTATION", mutation) + "\nreturn {}\n"
        if placement == "module_helper":
            text = prefix + "def inspected(inputs, params):\n" + indent(text_body, "    ")
            text += "class Task:\n    def run_pure(self, inputs, params):\n        inspected(inputs, params)\n        return {}\n"
        elif placement == "method":
            text = prefix + "class Task:\n    def run_pure(self, inputs, params):\n" + indent(text_body, "        ")
        else:
            raise ValueError("unexpected frozen test placement")
        cases.append({"group": group, "case": label, "via_helper": helper,
                      "placement": placement, "expected": expected, "text": text,
                      "literal_body": body, "proof": proof})

    original_functions = (
        ("ORIGINAL_CASES", "test_original_exception_review_keeps_input_identity"),
        ("ARGUMENT_CASES", "test_call_arguments_capture_intermediate_exception_state"),
        ("ADJACENT_CASES", "test_nested_exception_regions_keep_execution_and_clearing_boundaries"),
    )
    for table_name, function_name in original_functions:
        test = function(original, function_name)
        for label, body, expected in tables[table_name]:
            if table_name != "ADJACENT_CASES":
                body = "alias = {}\ntry:\n" + indent(body, "    ") + "\nexcept Exception:\n    MUTATION"
            for helper in parameters(test, "via_helper"):
                for placement in parameters(test, "placement"):
                    add(table_name, label, body, expected, helper, placement, original_prefix)
    bare = function(original, "test_catchall_handler_clearing_is_a_precise_negative_control")
    assertion = next(item.test for item in bare.body if isinstance(item, ast.Assert))
    if not (isinstance(assertion, ast.Compare) and isinstance(assertion.left, ast.Name)
            and assertion.left.id == "findings" and len(assertion.ops) == 1
            and isinstance(assertion.ops[0], ast.Eq) and ast.literal_eval(assertion.comparators[0]) == ()):
        raise ValueError("bare control no longer has its explicit empty-findings expectation")
    bare_body = template(assignment(bare, "body"))
    for helper in parameters(bare, "via_helper"):
        for placement in parameters(bare, "placement"):
            add("BARE_CONTROLS", "catchall-handler-clear", bare_body, False, helper, placement, original_prefix)
    for table_name, function_name in (
        ("EXCEPTION_CONTROLS", "test_exception_controls_use_evaluation_and_binding_facts"),
        ("DELETED_CALLEE_CONTROLS", "test_deleted_and_rebound_callees_keep_exception_evaluation_order"),
        ("BOUND_EVALUATION_CONTROLS", "test_local_name_loads_use_actual_binding_before_argument_clear"),
    ):
        test = function(metadata, function_name)
        placements = parameters(test, "placement") if table_name == "DELETED_CALLEE_CONTROLS" else ("method",)
        for label, body, expected in tables[table_name]:
            for helper in parameters(test, "via_helper"):
                for placement in placements:
                    add(table_name, label, body, expected, helper, placement, metadata_prefix)
    captured = function(metadata, "test_nested_actual_call_keeps_captured_parameter_provenance")
    captured_prefix = template(assignment(captured, "text"))
    conditional = next(item for item in captured.body if isinstance(item, ast.If))
    captured_rebind = ast.literal_eval(conditional.body[0].value)
    captured_suffix = ast.literal_eval(next(item.value for item in captured.body if isinstance(item, ast.AugAssign)))
    for arbitrary, expected in parameters(captured, "arbitrary_params,expected"):
        if type(arbitrary) is not bool or type(expected) is not bool:
            raise ValueError("captured-before-definition expectation is no longer a literal bool")
        for helper in parameters(captured, "via_helper"):
            mutation = 'sink(alias)' if helper else 'alias.pop("seed", None)'
            text = captured_prefix.replace(MUTATION_TOKEN, mutation)
            text += captured_rebind if arbitrary else ""
            text += captured_suffix
            cases.append({"group": "CAPTURED_BEFORE_DEFINITION", "case": "arbitrary-object" if arbitrary else "runtime-dictionary",
                          "via_helper": helper, "placement": "method", "expected": expected, "text": text,
                          "literal_flags": [arbitrary, expected],
                          "proof": {"symbol": "queried", "dictionary_name": "params",
                                    "dictionary_expected": not arbitrary, "owned_expected": ["inputs"]}})
    stable = function(metadata, "test_captured_dictionary_proof_requires_stable_actual_binding")
    stable_template = template(assignment(stable, "text"))
    for label, between, expected in tables["CAPTURED_DICTIONARY_CONTROLS"]:
        for helper in parameters(stable, "via_helper"):
            mutation = 'sink(alias)' if helper else 'alias.pop("seed", None)'
            text = stable_template.replace(MUTATION_TOKEN, mutation).replace(BETWEEN_TOKEN, indent(between, "        "))
            cases.append({"group": "CAPTURED_DICTIONARY_CONTROLS", "case": label, "via_helper": helper,
                          "placement": "method", "expected": expected, "text": text, "literal_between": between,
                          "proof": {"symbol": "queried", "dictionary_name": "params",
                                    "dictionary_expected": not expected, "owned_expected": ["inputs"]}})
    counts = {name: sum(case["group"] == name for case in cases) for name in {case["group"] for case in cases}}
    wanted = {"ORIGINAL_CASES": 32, "ARGUMENT_CASES": 16, "ADJACENT_CASES": 60, "BARE_CONTROLS": 4,
              "EXCEPTION_CONTROLS": 8, "DELETED_CALLEE_CONTROLS": 24, "BOUND_EVALUATION_CONTROLS": 8,
              "CAPTURED_BEFORE_DEFINITION": 4, "CAPTURED_DICTIONARY_CONTROLS": 8}
    if counts != wanted or len(cases) != 164:
        raise ValueError("frozen test matrix no longer matches the requested 112+52 controls")
    for index, case in enumerate(cases):
        case["id"] = f"{index:03d}.{case['group']}.{case['case']}.{'helper' if case['via_helper'] else 'direct'}.{case['placement']}"
        compile(case["text"], "/virtual/" + case["id"] + ".py", "exec")
        case["text_sha256"] = hashlib.sha256(case["text"].encode()).hexdigest()
    after = {name: sha(path) for name, path in zip(TEST_NAMES, paths)}
    if before != after:
        raise ValueError("test sources changed during literal-only data preparation")
    data = {"kind": "frozen-stdlib-ast-literal-controls", "count": len(cases), "group_counts": counts,
            "test_source_sha256": before, "tests_unchanged_during_preparation": before == after,
            "repo_source_prefix": str(repo / "src"), "raw_literal_tables": tables,
            "bare_control_expected_source": "literal assertion findings == ()",
            "metadata_proof_only_cases_excluded": 18, "business_definitions_executed": False,
            "finding_bool_expectations_modified": False, "cases": cases}
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with data_path.open("xb") as stream:
        stream.write(json_bytes(data))
    print(json.dumps({"data": str(data_path), "sha256": sha(data_path), "count": len(cases), "group_counts": counts}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--source", type=Path)
    select.add_argument("--kernel", type=Path)
    parser.add_argument("--prepare-data", action="store_true")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--data", type=Path, default=Path(__file__).with_suffix(".data.json"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.prepare_data:
        if args.source or args.kernel or args.manifest or args.report:
            parser.error("data preparation has no product imports or replay outputs")
        return prepare((args.repo or Path(__file__).resolve().parent.parents[2]).resolve(strict=True), args.data.resolve())
    if args.manifest is None or args.report is None:
        parser.error("replay requires explicit --manifest and a fresh --report")
    if args.report.exists():
        parser.error("evidence exists; preserve it and select a new --report")
    data = json.loads(args.data.read_text())
    if data["count"] != 164 or len(data["cases"]) != data["count"]:
        raise ValueError("invalid frozen finding control data")
    script_hash, data_hash, manifest_hash = sha(Path(__file__)), sha(args.data), sha(args.manifest)
    manifest = json.loads(args.manifest.read_text())
    expected_files = manifest["files"]
    if manifest["product_file_count"] != 335 or len(expected_files) != 335:
        raise ValueError("explicit product manifest must cover all 335 files")
    distribution_version = None
    if args.source:
        product, kind = args.source.resolve(strict=True), "source_snapshot"
    elif args.kernel:
        product, kind = args.kernel.resolve(strict=True), "kernel_zip"
    else:
        distribution = importlib.metadata.distribution("vibeflow")
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        if not distribution.read_text("WHEEL") or direct.get("dir_info", {}).get("editable"):
            raise ValueError("installed product must be a noneditable wheel")
        product, kind = Path(distribution.locate_file("")).resolve(strict=True), "installed_wheel"
        distribution_version = distribution.version
    reject = Path(data["repo_source_prefix"]).resolve()
    if product == reject or product.is_relative_to(reject):
        raise ValueError("replay cannot select checkout repo/src")
    if any(name == "vibeflow" or name.startswith("vibeflow.") for name in sys.modules):
        raise ValueError("product modules were imported before selecting the isolated package")

    def product_files():
        if args.kernel:
            with zipfile.ZipFile(product) as archive:
                return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                        if name.startswith("vibeflow/") and not name.endswith("/")}
        package = product / "vibeflow"
        return {"vibeflow/" + path.relative_to(package).as_posix(): sha(path) for path in package.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")}

    before = product_files()
    if before != expected_files:
        raise ValueError("selected product bytes differ from the explicit complete manifest")
    kernel_hash = sha(product) if args.kernel else None
    sys.path[:] = [entry for entry in sys.path if not entry or Path(entry).resolve() != reject]
    sys.path.insert(0, str(product))
    import vibeflow
    from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
    from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
    from vibeflow.targets.python.quality.source_analysis.parameter_facts import source_parameter_facts
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
    from vibeflow.targets.python.sdk import node, ruleset
    from vibeflow.targets.shared.bindings import native_binding
    from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins

    catalog = load_builtin_plugins("python").catalogs
    handlers = {item.id: native_binding(catalog, "rule", item.id) for item in catalog.rules}
    selected = ruleset(id="probe.frozen_exception_controls", calls=[{
        "id": "effects", "rule_id": "vibeflow.no_side_effects", "params": {"effect_scope": "global_state"}}]).descriptor
    plan = complete_source_policy_plan(compile_ruleset(selected, rules={item.id: item for item in catalog.rules},
        rulesets={selected.id: selected}), handlers=handlers)
    rows = []
    for case in data["cases"]:
        row = {key: case[key] for key in ("id", "group", "case", "via_helper", "placement", "expected", "text_sha256")}
        try:
            if type(case["expected"]) is not bool or hashlib.sha256(case["text"].encode()).hexdigest() != case["text_sha256"]:
                raise ValueError("frozen case text or literal expectation is invalid")
            path = "/virtual/" + case["id"] + ".py"
            compile(case["text"], path, "exec")
            parsed = PythonSourceFile.parse(path, "frozen_exception_controls", case["text"])
            declaration = node(type_key="probe.frozen_exception", contract={}, rulesets=[selected.id],
                source={"kind": "file", "ref": path, "export": "Task"})
            resource = PythonSourceNode(declaration.descriptor, path, "Task")
            sources = build_python_source_context((resource,), (parsed,))
            ast_before = ast.dump(parsed._tree, include_attributes=True)
            if case["proof"] is not None:
                proof = case["proof"]
                owned, dictionaries, _ = source_parameter_facts(sources, resource)
                symbol = sources.symbol(path, proof["symbol"])
                actual_dict = proof["dictionary_name"] in dictionaries[symbol._node]
                actual_owned = sorted(owned[symbol.id])
                row["parameter_proof"] = {"dictionary_expected": proof["dictionary_expected"],
                    "dictionary_actual": actual_dict, "owned_expected": proof["owned_expected"], "owned_actual": actual_owned,
                    "pass": actual_dict == proof["dictionary_expected"] and actual_owned == proof["owned_expected"]}
            context = RuleContext(subject={"kind": "node", "id": "probe.frozen_exception", "type_key": "probe.frozen_exception"},
                target="python", facts={"source_context": sources, "node_catalog": (), "source_owners": (
                    {"kind": "node", "id": "probe.frozen_exception", "role": "entry", "path": path, "symbol": "Task"},)})
            result = execute_rule_plan(plan, context, handlers=handlers)
            effect_result = result.results["effects"]
            policy = plain(effect_result.records["effect_policy"].value)
            findings = [item for item in result.findings if item.code == "NODE.PURITY.INPUT_MUTATION"]
            row.update(actual=bool(findings), state=effect_result.state, effect_policy=policy,
                       ast_unchanged=ast.dump(parsed._tree, include_attributes=True) == ast_before,
                       findings=[{"code": item.code, "severity": item.severity, "message": item.message,
                                  "source_location": dict(item.source_location)} for item in findings])
            row["pass"] = (row["actual"] == case["expected"] and row["state"] == "completed"
                           and policy["effect_scope"] == "global_state" and row["ast_unchanged"]
                           and row.get("parameter_proof", {"pass": True})["pass"])
        except Exception as error:
            row.update(error=type(error).__name__ + ": " + str(error), **{"pass": False})
        rows.append(row)
    prefix = str(product) + "/vibeflow/"
    modules = {name: str(getattr(module, "__file__", "") or "") for name, module in sys.modules.items()
               if name == "vibeflow" or name.startswith("vibeflow.")}
    foreign = {name: origin for name, origin in modules.items()
               if not origin.startswith(prefix) or origin.startswith(str(reject) + "/")}
    after = product_files()
    kernel_after = sha(product) if args.kernel else None
    input_unchanged = script_hash == sha(Path(__file__)) and data_hash == sha(args.data) and manifest_hash == sha(args.manifest)
    result = {"kind": "standalone-frozen-finding-controls", "count": len(rows), "group_counts": data["group_counts"],
              "mismatches": [row["id"] for row in rows if not row["pass"]], "rows": rows,
              "product": {"kind": kind, "path": str(product), "origin": vibeflow.__file__,
                          "expected_origin_prefix": prefix, "distribution_version": distribution_version,
                          "kernel_sha256": kernel_hash, "kernel_sha256_after": kernel_after},
              "loaded_vibeflow_modules": modules, "foreign_modules": foreign,
              "package_isolation_pass": not foreign and str(vibeflow.__file__).startswith(prefix),
              "manifest": str(args.manifest.resolve()), "manifest_sha256": manifest_hash,
              "expected_product_file_count": 335, "all_file_types": True,
              "product_files_sha256_before": before, "product_files_sha256_after": after,
              "allbytes_match_manifest_before_after": before == expected_files == after,
              "product_files_unchanged": before == after and kernel_hash == kernel_after,
              "script_sha256": script_hash, "data": str(args.data.resolve()), "data_sha256": data_hash,
              "frozen_test_source_sha256": data["test_source_sha256"], "probe_inputs_unchanged": input_unchanged,
              "finding_bool_expectations_modified": False, "business_definitions_executed": False,
              "test_modules_imported": any(name == "pytest" or name == "tests" or name.startswith("tests.") for name in sys.modules)}
    result["pass"] = (len(rows) == 164 and not result["mismatches"] and result["package_isolation_pass"]
                      and result["allbytes_match_manifest_before_after"] and result["product_files_unchanged"]
                      and input_unchanged and not result["test_modules_imported"])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("count", "mismatches", "package_isolation_pass", "allbytes_match_manifest_before_after", "pass")}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
