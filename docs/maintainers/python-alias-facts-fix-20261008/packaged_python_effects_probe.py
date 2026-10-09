"""Standalone installed-package effect probes. No test or checkout imports.

Examples (run from an isolated directory):
  /wheel-venv/bin/python /path/to/packaged_python_effects_probe.py \
    --report /evidence/wheel-effects.json --workdir /evidence/wheel-sources
  python /path/to/packaged_python_effects_probe.py --kernel /project/kernel/vibeflow-kernel.zip \
    --report /evidence/kernel-effects.json --workdir /evidence/kernel-sources
Wheel mode verifies installed metadata and every VibeFlow module against one
package directory. Kernel mode inserts the selected ZIP before product imports
and verifies every VibeFlow module against that ZIP, recording its SHA256.
Analyzed programs are written and parsed; none of their IO calls execute.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from textwrap import indent


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _allowed_origin(origin, package):
    if not origin:
        return False
    resolved = Path(origin).resolve()
    return resolved.is_relative_to(Path(package["package_root"]))


def _loaded_origins(package):
    modules, foreign = [], []
    for name, module in sorted(sys.modules.copy().items()):
        if name != "vibeflow" and not name.startswith("vibeflow."):
            continue
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        file = getattr(module, "__file__", None)
        locations = list(getattr(module, "__path__", ()))
        evidence = {"name":name, "origin":origin, "file":file, "search_locations":locations}
        paths = [value for value in (origin, file, *locations) if value]
        if not paths or any(not _allowed_origin(value, package) for value in paths):
            foreign.append(evidence)
        modules.append(evidence)
    return {"loaded_module_count":len(modules), "loaded_modules":modules, "foreign_modules":foreign}


def _select_package(args, package):
    script = Path(__file__).resolve()
    package.update({"kind":"kernel_zip" if args.kernel else "wheel", "origin":None,
                    "package_root":None, "kernel":None, "kernel_sha256":None,
                    "script_origin":str(script), "script_sha256":_sha256(script)})
    rejects = [args.reject_source_prefix.resolve()] if args.reject_source_prefix else []
    # The probe lives under dist/<evidence>/ in this task. When moved elsewhere,
    # callers may keep the explicit rejection flag as an additional check.
    local_source = script.parents[2] / "src" if len(script.parents) > 2 else None
    if local_source is not None and (local_source / "vibeflow").is_dir():
        rejects.append(local_source.resolve())
    package["rejected_source_prefixes"] = sorted({str(path) for path in rejects})
    if any(script.is_relative_to(prefix) for prefix in rejects):
        raise ValueError("probe script must not be read from a checkout source prefix")
    if args.kernel:
        kernel = args.kernel.resolve()
        package.update(kernel=str(kernel), package_root=str(kernel / "vibeflow"))
        package["kernel_sha256"] = _sha256(kernel)
        # Select exactly one occurrence of this archive before any product import.
        sys.path[:] = [str(kernel), *(entry for entry in sys.path if Path(entry or ".").resolve() != kernel)]
    else:
        distribution = importlib.metadata.distribution("vibeflow")
        if distribution.read_text("WHEEL") is None:
            raise ValueError("wheel mode requires installed VibeFlow wheel metadata")
        direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
        if direct_url.get("dir_info", {}).get("editable"):
            raise ValueError("wheel mode requires a wheel install rather than an editable checkout")
        package_root = Path(distribution.locate_file("vibeflow")).resolve()
        metadata_file = next((file for file in distribution.files or ()
                              if file.name == "METADATA" and file.parent.name.endswith(".dist-info")), None)
        package.update(package_root=str(package_root), version=distribution.version,
                       distribution_origin=str(distribution.locate_file(metadata_file).resolve()) if metadata_file else None)
        if args.package_root and args.package_root.resolve() != package_root:
            raise ValueError("installed wheel package root does not match --package-root")
    if any(Path(package["package_root"]).is_relative_to(prefix) for prefix in rejects):
        raise ValueError("selected package must not be read from a checkout source prefix")
    spec = importlib.util.find_spec("vibeflow")
    package["origin"] = getattr(spec, "origin", None)
    locations = list(getattr(spec, "submodule_search_locations", ()) or ())
    if not _allowed_origin(package["origin"], package) or any(not _allowed_origin(value, package) for value in locations):
        package["preimport_foreign_candidate"] = {"name":"vibeflow", "origin":package["origin"], "search_locations":locations}
        raise ValueError("pre-import VibeFlow origin is outside the selected package: " + str(package["origin"]))
    return package


def _load_product():
    global vibeflow, NodeContractDescriptor, NodeDescriptor
    global RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
    global PythonSource, complete_source_policy_plan, PythonSourceFile, PythonSourceNode, build_python_source_context
    global native_binding, load_builtin_plugins
    import vibeflow
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
    from vibeflow.targets.python.quality import PythonSource
    from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
    from vibeflow.targets.shared.bindings import native_binding
    from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins


def _write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key:value for key,value in report.items() if key not in {"observations", "loaded_modules"}}, ensure_ascii=False))


KINDS = ("python_source", "node", "base_lib", "plugin")
SCOPES = ("none", "terminal", "python_io", "global_state", "trusted")
IMPORT_KEYS = ("allowed_roots", "banned_roots", "allowed_modules", "banned_modules")


def context(kind, case, body, *, helper=None, helper_export="chosen", class_initializer=None, class_statements=None, class_base=None, class_decorator=None):
    case.mkdir(parents=True, exist_ok=True)
    prefix = "from helper import " + helper_export + " as chosen\n" if helper is not None else ""
    decorator = "@" + class_decorator + "\n" if class_decorator else ""
    header = "class Task" + ("(" + class_base + ")" if class_base else "") + ":\n"
    if kind == "node":
        statements = "\n".join(line.removeprefix("return ") if line.startswith("return ") else line
                               for line in body.splitlines()) + "\nreturn {}"
        field = "    CACHE = " + class_initializer + "\n" if class_initializer else ""
        if class_statements:
            field += indent(class_statements, "    ") + "\n"
        text = prefix + decorator + header + field + "    def run_pure(self, inputs, params):\n" + indent(statements, "        ") + "\n"
        descriptor = NodeDescriptor(type_key="probe.task", display_name="Task", description="Installed-package effect probe.",
                                    version="1", flow_kind="process", contract=NodeContractDescriptor())
        nodes = (PythonSourceNode(descriptor, str(case / "entry.py"), "Task"),)
    elif class_initializer or class_statements or class_base or class_decorator:
        field = "    CACHE = " + class_initializer + "\n" if class_initializer else ""
        if class_statements:
            field += indent(class_statements, "    ") + "\n"
        text = prefix + decorator + header + field + "    def task(self):\n" + indent(body, "        ") + "\n"
        nodes = ()
    else:
        text = prefix + "def task():\n" + indent(body, "    ") + "\n"
        nodes = ()
    path = case / "entry.py"
    path.write_text(text)
    entry = PythonSourceFile.parse(str(path), "entry", text)
    files = [entry]
    if helper is not None:
        helper_path = case / "helper.py"
        helper_path.write_text(helper)
        files.append(PythonSourceFile.parse(str(helper_path), "helper", helper))
    sources = build_python_source_context(nodes, files)
    closure = tuple(file.path for file in sources.import_closure(entry.path))
    if helper is not None and str(case / "helper.py") not in closure:
        raise AssertionError("real local import closure did not include helper.py")
    owners = tuple({"kind":kind, "id":"probe.task", "role":"entry" if file.path == entry.path else "support",
                    "path":file.path, "symbol":"Task" if kind == "node" and file.path == entry.path else ""} for file in files)
    facts = {"source_context":sources, "node_catalog":(), "source_owners":owners}
    if kind == "python_source":
        pairs = tuple((PythonSource(file.module, Path(file.path).name, file.path, file.text), file) for file in files)
        facts.update(python_source=pairs[0][0], source_file=entry, python_sources=pairs)
    elif kind == "base_lib":
        facts.update(base_lib_file=entry, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=entry, resource_symbol="")
    return RuleContext(subject={"kind":kind, "id":"probe.task", "type_key":"probe.task"}, facts=facts, target="python"), closure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--kernel", type=Path, help="Select this generated kernel ZIP before importing VibeFlow")
    parser.add_argument("--package-root", type=Path, help="Optional exact vibeflow package directory expected for the installed wheel")
    parser.add_argument("--reject-source-prefix", type=Path, help="Fail if vibeflow was loaded from this checkout prefix")
    args = parser.parse_args()
    package = {}
    try:
        _select_package(args, package)
        _load_product()
        initial = _loaded_origins(package)
        if initial["foreign_modules"]:
            raise ValueError("loaded VibeFlow modules are outside the selected package")
    except Exception as exc:
        report = {"package":package, "package_isolation_pass":False, "error":str(exc),
                  "count":0, "passed":0, "failed":0, "observations":[],
                  **(_loaded_origins(package) if package and package.get("package_root") else
                     {"loaded_module_count":0, "loaded_modules":[], "foreign_modules":[]})}
        _write_report(args.report, report)
        return 2
    work = (args.workdir or args.report.parent / "packaged-python-effect-sources").resolve()
    work.mkdir(parents=True, exist_ok=True)
    origin = str(Path(vibeflow.__file__).resolve())
    catalog = load_builtin_plugins("python").catalogs
    rules = {item.id:item for item in catalog.rules}
    handlers = {item.id:native_binding(catalog, "rule", item.id) for item in catalog.rules}
    rows = []

    def probe(label, kind, body, scope, allowed, *, helper=None, helper_export="chosen", class_initializer=None, class_statements=None, class_base=None, class_decorator=None, policy=None,
              rule_id="vibeflow.no_side_effects", required_path=None, expected_imports=None):
        params = {"effect_scope":scope}
        if policy is not None:
            params["policy"] = policy
        selected = RulesetDescriptor("probe.selected", calls=(RuleCall("check", rule_id=rule_id, params=params),))
        plan = complete_source_policy_plan(compile_ruleset(selected, rules=rules, rulesets={selected.id:selected}), handlers=handlers)
        supplied, closure = context(kind, work / (label + "-" + kind + "-" + scope), body,
                                    helper=helper, helper_export=helper_export, class_initializer=class_initializer, class_statements=class_statements, class_base=class_base, class_decorator=class_decorator)
        result = execute_rule_plan(plan, supplied, handlers=handlers)
        data = result.to_dict()
        effective = data["plan"]["calls"][0]["params"]
        completed = all(item.state == "completed" for item in result.results.values())
        checks = {"completed":completed, "diagnostic_expected":bool(result.findings) == (scope not in allowed),
                  "scope_effective":effective.get("effect_scope") == scope,
                  "imports_namespace":set(effective.get("policy", {})) == {"imports"},
                  "imports_shape":set(effective["policy"]["imports"]) == set(IMPORT_KEYS)}
        if rule_id == "vibeflow.no_side_effects":
            checks["scope_record"] = data["results"]["check"]["records"]["effect_policy"]["value"]["effect_scope"] == scope
        if required_path and result.findings:
            checks["actual_helper_location"] = all(Path(item.source_location["path"]).name == required_path for item in result.findings)
        if expected_imports is not None:
            checks["configured_imports"] = effective["policy"]["imports"] == expected_imports
        rows.append({"case":label,"kind":kind,"scope":scope,"rule_id":rule_id,"ok":all(checks.values()),
                     "checks":checks,"status":result.status,"effective_params":effective,
                     "records":data["results"]["check"]["records"],"import_closure":closure,
                     "findings":data["findings"]})

    cases = (
        ("file_io", 'return open("never-open").read()', {"python_io"}),
        ("terminal", 'print("probe")\nreturn 1', {"terminal", "python_io"}),
        ("ffi", "import ctypes\nreturn ctypes.CDLL(None)", set()),
        ("local_ffi_marker", "resource = object()\nresource.CDLL(None)\nreturn 1", set()),
        ("named_stdout", "from sys import stdout\nreturn stdout", {"terminal", "python_io"}),
        ("named_io", "from io import open as file_open\nreturn 1", {"python_io"}),
        ("named_http", "from http import client\nreturn 1", {"python_io"}),
        ("stdout_attribute", "import sys\nreturn sys.stdout", {"terminal", "python_io"}),
    )
    for label, body, allowed in cases:
        for kind in KINDS:
            for scope in SCOPES:
                probe(label, kind, body, scope, allowed)
    for label, body, allowed in (
        ("literal_getattr_stdout", "import sys\nreturn getattr(sys, 'stdout')", {"terminal", "python_io"}),
        ("literal_getattr_argv", "import sys\nreturn getattr(sys, 'argv')", set()),
        ("literal_vars_stdout", "import sys\nreturn vars(sys)['stdout']", {"terminal", "python_io"}),
        ("literal_vars_argv", "import sys\nreturn vars(sys)['argv']", set()),
        ("reflected_local_shadow", "import sys\nsys = object()\nreturn getattr(sys, 'stdout', None)", set(SCOPES)),
    ):
        for kind in KINDS:
            for scope in SCOPES:
                probe(label, kind, body, scope, allowed)
    # Preserve the original cases and append the receiver regressions found by
    # the formal CLI/full suite. Lexical locals alone grant no IO permission.
    for label, body, allowed in (
        ("unknown_local_receiver_close", "connection = params.get('connection')\nconnection.close()\nreturn 1", {"python_io"}),
        ("path_object_write_text", "from pathlib import Path\npath = Path('never-open')\npath.write_text('probe')\nreturn 1", {"python_io"}),
        ("real_file_close", "file = open('never-open', 'w')\nfile.close()\nreturn 1", {"python_io"}),
        ("stack_receiver_reassigned", "from contextlib import ExitStack\nstack = ExitStack()\nstack = params.get('connection')\nstack.close()\nreturn 1", {"python_io"}),
        ("stack_receiver_branch_reassigned", "from contextlib import ExitStack\nstack = ExitStack()\nif marker:\n    stack = params.get('connection')\nstack.close()\nreturn 1", {"python_io"}),
        ("stack_factory_shadowed", "from contextlib import ExitStack\nExitStack = params.get('factory')\nstack = ExitStack()\nstack.close()\nreturn 1", {"python_io"}),
        ("proved_exit_stack_cleanup", "from contextlib import ExitStack\nstack = ExitStack()\nstack.close()\nreturn 1", set(SCOPES)),
        ("argparse_local_host_argv", "import argparse\nparser = argparse.ArgumentParser()\nparser.parse_args()\nreturn 1", set()),
        ("argparse_local_explicit_argv", "import argparse\nparser = argparse.ArgumentParser()\nparser.parse_args([])\nreturn 1", {"terminal", "python_io"}),
    ):
        for kind in KINDS:
            for scope in SCOPES:
                probe(label, kind, body, scope, allowed)
    for target in ("sys.path", "sys.meta_path", "sys.modules", "sys.path_hooks", "os.environ"):
        module = target.split(".")[0]
        for kind in KINDS:
            for scope in SCOPES:
                probe("hard_state_" + target.replace(".", "_"), kind, "import " + module + "\n" + target + " = []\nreturn 1", scope, set())
    alias_cases = (
        ("assignment_alias", "import sys as process\np = process\np.path = []\nreturn 1"),
        ("from_alias", "from sys import path as p\np[:] = []\nreturn 1"),
        ("mixed_branch_alias", "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\np.path = []\nreturn 1"),
        ("branch_alias_call", "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\np.path.clear()\nreturn 1"),
        ("copy_joined_alias", "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\nq = p\nq.path = []\nreturn 1"),
    )
    for label, body in alias_cases:
        for kind in KINDS:
            for scope in SCOPES:
                probe(label, kind, body, scope, set())
    for kind in KINDS:
        for scope in SCOPES:
            probe("branch_stdout_reference", kind,
                  "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\nreturn p.stdout", scope, {"terminal", "python_io"})
            probe("alias_local_replacement", kind,
                  "import sys\np = sys\np = {'path': []}\np['path'] = []\nreturn 1", scope, set(SCOPES))
            probe("import_local_replacement", kind,
                  "import sys\nsys = {'path': []}\nsys['path'] = []\nreturn 1", scope, set(SCOPES))
    for kind in KINDS:
        probe("branch_both_replace_host_alias", kind,
              "import sys\nimport math\np = sys\nif marker:\n    p = math\nelse:\n    p = math\np.path = []\nreturn 1",
              "global_state", {"global_state"})
    for spelling in ("write", "close", "identity"):
        for effect in (False, True):
            helper = "def " + spelling + '(value):\n    return ' + ('open("never-open").read()' if effect else 'value') + "\n"
            # Import the actual function under a stable alias; resolution uses
            # the body and source edges, while its declared name varies.
            for kind in KINDS:
                for scope in ("none", "python_io"):
                    probe(("real_io_" if effect else "pure_") + spelling, kind, "return chosen(1)", scope,
                          {"python_io"} if effect else set(SCOPES),
                          helper=helper, helper_export=spelling, required_path="helper.py" if effect else None)
    for kind in KINDS:
        for scope in SCOPES:
            probe("class_initializer_io", kind, "return 1", scope, {"python_io"}, class_initializer='open("never-open")')
        probe("class_initializer_pure", kind, "return 1", "global_state", {"global_state"},
              helper="def chosen(value):\n    return {}\n", class_initializer="chosen(1)")
    for kind in KINDS:
        for scope in SCOPES:
            probe("class_body_with_io", kind, "return 1", scope, {"python_io"},
                  class_statements='with open("never-open") as value:\n    pass')
            probe("class_body_named_stdout", kind, "return 1", scope, {"terminal", "python_io"},
                  class_statements="from sys import stdout")
    for kind in KINDS:
        for scope in SCOPES:
            probe("class_base_argument_io", kind, "return 1", scope, {"python_io"},
                  helper="def chosen(value):\n    return object\n", class_base='chosen(open("never-open"))')
            probe("class_decorator_argument_io", kind, "return 1", scope, {"python_io"},
                  helper="def chosen(value):\n    return lambda cls: cls\n", class_decorator='chosen(open("never-open"))')
    probe("helper_function_scope_restores_aliases", "base_lib", "return chosen(1)", "global_state", {"global_state"},
          helper="import sys\nimport math\np = math\ndef first():\n    if marker:\n        p = sys\n    else:\n        p = math\n    return 1\ndef chosen(value):\n    p.path = []\n    return value\n")
    for kind in KINDS:
        for rule_id in ("vibeflow.no_side_effects", "vibeflow.import_side_effects"):
            defaults = {name:[] for name in IMPORT_KEYS}
            if rule_id == "vibeflow.no_side_effects":
                defaults.update(banned_roots=["importlib"], allowed_modules=["urllib.parse", "vibeflow"])
            probe("native_defaults_" + rule_id.rsplit(".",1)[-1], kind, "import importlib\nreturn 1", "none",
                  set(SCOPES) if rule_id == "vibeflow.import_side_effects" else set(), rule_id=rule_id, expected_imports=defaults)
            explicit = {**defaults,"banned_roots":[],"banned_modules":["example.policy"]}
            probe("explicit_module_ban_" + rule_id.rsplit(".",1)[-1], kind, "import example.policy\nreturn 1", "python_io", set(),
                  rule_id=rule_id, policy={"imports":{"banned_roots":[],"banned_modules":["example.policy"]}}, expected_imports=explicit)
    loaded = _loaded_origins(package)
    report = {"package":package, "package_isolation_pass":not loaded["foreign_modules"],
              "package_origin":origin,"python_executable":sys.executable,
              "handler_origin":handlers["vibeflow.no_side_effects"].__module__,
              "count":len(rows),"passed":sum(row["ok"] for row in rows),
              "failed":sum(not row["ok"] for row in rows),"observations":rows, **loaded}
    _write_report(args.report, report)
    for row in rows:
        if not row["ok"]:
            print(json.dumps({key:row[key] for key in ("case","kind","scope","checks","findings")}, ensure_ascii=False))
    return 2 if not report["package_isolation_pass"] else int(bool(report["failed"]))


if __name__ == "__main__":
    raise SystemExit(main())
