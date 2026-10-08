"""Ordinary source consumes the same selected effect policy as native resources."""

import ast
from textwrap import indent

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
from vibeflow.targets.python.quality import PythonSource
from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
from vibeflow.targets.shared.bindings import native_binding
from vibeflow.tooling.application.python.project.quality_scan import scan_code_quality
from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins


def _context(kind, body):
    if kind == "node":
        body = "\n".join(line.removeprefix("return ") if line.startswith("return ") else line
                         for line in body.splitlines()) + "\nreturn {}"
        text = "class Task:\n    def run_pure(self, inputs, params):\n" + indent(body, "        ") + "\n"
        descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="One effect probe.",
            version="1", flow_kind="process", contract=NodeContractDescriptor())
        nodes = (PythonSourceNode(descriptor, "/virtual/example.py", "Task"),)
    else:
        text = "def task():\n" + indent(body, "    ") + "\n"
        nodes = ()
    parsed = PythonSourceFile("/virtual/example.py", "example", text, _tree=ast.parse(text))
    sources = build_python_source_context(nodes, (parsed,))
    facts = {"source_context":sources, "node_catalog":(), "source_owners":()}
    if kind == "python_source":
        facts.update(python_source=PythonSource("example", "example.py", parsed.path, text), source_file=parsed)
    elif kind == "base_lib":
        facts.update(base_lib_file=parsed, resource_symbol="")
    if kind == "plugin":
        facts.update(resource_source_file=parsed, resource_symbol="")
    return RuleContext(subject={"kind":kind, "type_key":"example.task"}, facts=facts, target="python")


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body,allowed", [
    ('return open("data.txt").read()', {"python_io"}),
    ('print("hello")\nreturn {}', {"terminal", "python_io"}),
    ('import requests\nreturn requests.get("https://example.invalid")', {"python_io"}),
    ('import sqlite3\nreturn sqlite3.connect("data.db")', {"python_io"}),
    ('import ctypes\nreturn ctypes.CDLL(None)', set()),
    ('return eval("1 + 1")', set()),
    ('import torch\ntorch.manual_seed(0)\nreturn {}', {"global_state"}),
])
def test_effect_scopes_have_the_same_contract_for_source_node_and_library(scope, body, allowed):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope, "policy":{}})
        assert result.state == "completed"
        assert bool(result.findings) == (scope not in allowed), (kind, scope, result.findings)
        assert result.records["effect_policy"].value["effect_scope"] == scope
        if kind == "python_source":
            assert all(item.severity == "warning" and item.object_type == "file" for item in result.findings)


@pytest.mark.parametrize("policy,denied", [
    ({"imports":{"banned_roots":["example"]}}, True),
    ({"imports":{"banned_roots":["example"], "allowed_roots":["example"]}}, False),
    ({"imports":{"allowed_modules":["example"], "banned_modules":["example.policy"]}}, True),
])
def test_policy_import_overrides_apply_to_all_source_subjects(policy, denied):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, "import example.policy\nreturn {}"), {},
            {"effect_scope":"none", "policy":policy})
        assert bool(result.findings) == denied, (kind, result.findings)


@pytest.mark.parametrize("scope,deny_import,deny_call", [
    ("none", False, True), ("python_io", True, False), ("terminal", True, True),
])
def test_selected_catalog_rule_reports_effective_policy_and_matching_effects(scope, deny_import, deny_call):
    catalog = load_builtin_plugins("python").catalogs
    rules = {item.id:item for item in catalog.rules}
    handlers = {item.id:native_binding(catalog, "rule", item.id) for item in catalog.rules}
    policy = {"imports":{"banned_modules":["example.policy"] if deny_import else []}}
    selected = RulesetDescriptor("example.effect_review", calls=(RuleCall("effects",
        rule_id="vibeflow.no_side_effects", params={"effect_scope":scope, "policy":policy}),))
    plan = complete_source_policy_plan(compile_ruleset(selected, rules=rules, rulesets={selected.id:selected}),
                                      handlers=handlers)
    result = execute_rule_plan(plan, _context("python_source", 'import example.policy\nreturn open("data.txt").read()'),
                               handlers=handlers)
    recorded = result.to_dict()["plan"]["calls"][0]["params"]
    assert recorded["effect_scope"] == scope
    assert recorded["policy"]["imports"]["banned_modules"] == policy["imports"]["banned_modules"]
    assert set(recorded["policy"]) == {"imports"}
    codes = {item.code for item in result.findings}
    assert ("QUALITY.SIDE_EFFECT.IMPORT" in codes) == deny_import
    assert ("QUALITY.SIDE_EFFECT.CALL" in codes) == deny_call
    assert result.results["effects"].records["effect_policy"].value["effect_scope"] == recorded["effect_scope"]


def test_application_source_scan_keeps_default_none_and_explicit_selection(tmp_path):
    path = tmp_path / "ordinary.py"
    path.write_text('def read():\n    return open("data.txt").read()\n')
    selected = scan_code_quality(tmp_path, check_side_effects=True)
    effects = [item for item in selected.findings if item.code == "QUALITY.SIDE_EFFECT.CALL"]
    assert len(effects) == 1 and effects[0].source_location["path"] == str(path)
    execution = selected.rule_executions[-1]
    assert execution["plan"]["calls"][0]["params"]["effect_scope"] == "none"
    call_id = execution["plan"]["calls"][0]["id"]
    assert execution["results"][call_id]["records"]["effect_policy"]["value"]["effect_scope"] == "none"
    unselected = scan_code_quality(tmp_path)
    assert not any(item.code.startswith("QUALITY.SIDE_EFFECT.") for item in unselected.findings)


def test_source_effects_follow_real_helper_bodies_without_importing_node_contracts():
    text = ('def write():\n    return 1\n'
            'def caller():\n    return write()\n'
            'CACHE = {}\n')
    source = PythonSource("ordinary", "ordinary.py", "/virtual/ordinary.py", text)
    parsed = PythonSourceFile(source.source_path, source.module, source.text, _tree=ast.parse(text))
    context = RuleContext(subject={"kind":"python_source"}, facts={"python_source":source,"source_file":parsed})
    assert no_side_effects(context, {}, {"effect_scope":"none", "policy":{}}).findings == ()
    text = text.replace("return 1", 'return open("data.txt").read()')
    source = PythonSource(source.module, source.relative_path, source.source_path, text)
    parsed = PythonSourceFile(source.source_path, source.module, source.text, _tree=ast.parse(text))
    context = RuleContext(subject={"kind":"python_source"}, facts={"python_source":source,"source_file":parsed})
    assert {item.code for item in no_side_effects(context, {}, {"effect_scope":"none", "policy":{}}).findings} == {"QUALITY.SIDE_EFFECT.CALL"}


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body,allowed", [
    ("from sys import stdout\nreturn stdout", {"terminal", "python_io"}),
    ("from io import open as file_open\nreturn 1", {"python_io"}),
    ("from http import client\nreturn 1", {"python_io"}),
    ("import sys\nreturn sys.stdout", {"terminal", "python_io"}),
    ("import sys\nsys.path = []\nreturn 1", set()),
])
def test_shared_effect_traversal_covers_named_imports_and_process_state(scope, body, allowed):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert bool(result.findings) == (scope not in allowed), (kind, scope, result.findings)


def _resource_context(kind, text, helpers=()):
    parsed = PythonSourceFile.parse("/virtual/entry.py", "entry", text)
    sources = build_python_source_context((), (parsed, *helpers))
    owners = tuple({"kind":kind, "id":"example.resource", "role":"entry" if file.path == parsed.path else "support",
        "path":file.path, "symbol":""} for file in sources.files)
    return RuleContext(subject={"kind":kind, "id":"example.resource", "type_key":"example.resource"}, target="python",
        facts={"source_context":sources,"resource_source_file":parsed,"base_lib_file":parsed,
               "source_owners":owners,"resource_symbol":""})


@pytest.mark.parametrize("kind", ["plugin", "base_lib"])
@pytest.mark.parametrize("name", ["write", "read", "close", "identity"])
def test_resolved_helpers_have_the_same_result_under_any_name(kind, name):
    helper = PythonSourceFile.parse("/virtual/helper.py", "helper", f"def {name}(value):\n    return value\n")
    context = _resource_context(kind, f"from helper import {name}\ndef caller(value):\n    return {name}(value)\n", (helper,))
    assert no_side_effects(context, {}, {"effect_scope":"none"}).findings == ()
    helper = PythonSourceFile.parse(helper.path, helper.module, f'def {name}(value):\n    return open("never-read").read()\n')
    context = _resource_context(kind, f"from helper import {name}\ndef caller(value):\n    return {name}(value)\n", (helper,))
    denied = no_side_effects(context, {}, {"effect_scope":"none"})
    assert denied.findings and all(item.source_location["path"] == helper.path for item in denied.findings)


def test_resolved_plugin_methods_are_reviewed_by_their_bodies():
    context = _resource_context("plugin", "class Value:\n    @staticmethod\n    def close(value):\n        return value\ndef caller(value):\n    return Value.close(value)\n")
    assert no_side_effects(context, {}, {"effect_scope":"none"}).findings == ()


def test_base_library_structure_and_initializers_remain_separate_from_node_constraints():
    pure = _resource_context("base_lib", 'def constructor():\n    return {}\nCACHE = constructor()\ndef helper(value):\n    setattr(value, "x", 1)\n')
    assert no_side_effects(pure, {}, {"effect_scope":"global_state"}).findings == ()
    denied = _resource_context("base_lib", 'CACHE = open("never-read")\n')
    assert {item.code for item in no_side_effects(denied, {}, {"effect_scope":"global_state"}).findings} == {"BASE_LIB.SIDE_EFFECT_CALL"}
    alias = _resource_context("base_lib", 'writer = open\ndef helper():\n    return writer("never-read")\n')
    assert {item.code for item in no_side_effects(alias, {}, {"effect_scope":"none"}).findings} == {"BASE_LIB.GLOBAL_STATE", "BASE_LIB.SIDE_EFFECT_CALL"}
    structure = _resource_context("base_lib", 'for value in ():\n    pass\n')
    assert {item.code for item in no_side_effects(structure, {}, {"effect_scope":"none"}).findings} == {"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"}


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body", [
    "import sys\nsys.path = []\nreturn 1",
    "import sys\nsys.meta_path = []\nreturn 1",
    "import sys\nsys.modules = {}\nreturn 1",
    "import sys\nsys.path_hooks = []\nreturn 1",
    "import os\nos.environ = {}\nreturn 1",
    "import sys as process\np = process\np.path = []\nreturn 1",
    "from sys import path as p\np[:] = []\nreturn 1",
    "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\np.path = []\nreturn 1",
    "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\np.path.clear()\nreturn 1",
])
def test_shared_hard_process_state_assignment_tracks_canonical_aliases(scope, body):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert result.state == "completed" and result.findings, (kind, scope, body, result)
        assert all(item.source_location["path"] == "/virtual/example.py" for item in result.findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body", [
    "import sys\np = sys\np = {'path': []}\np['path'] = []\nreturn 1",
    "import sys\nsys = {'path': []}\nsys['path'] = []\nreturn 1",
    "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\np = {'path': []}\np['path'] = []\nreturn 1",
])
def test_local_replacement_clears_previous_host_alias_facts(scope, body):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        assert no_side_effects(_context(kind, body), {}, {"effect_scope":scope}).findings == (), (kind, scope, body)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_branch_alias_candidates_are_also_consumed_by_attribute_effects(scope):
    body = "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\nreturn p.stdout"
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert bool(result.findings) == (scope not in {"terminal", "python_io"}), (kind, scope, result)


@pytest.mark.parametrize("statement,allowed", [
    ('CACHE = open("never-open")', {"python_io"}),
    ('CACHE: object = open("never-open")', {"python_io"}),
    ('with open("never-open") as value:\n    pass', {"python_io"}),
    ('from sys import stdout', {"terminal", "python_io"}),
    ('CACHE = {"value": tuple((1, 2))}', {"none", "terminal", "python_io", "global_state", "trusted"}),
])
@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_node_class_body_uses_shared_effect_traversal_through_catalog_plan(statement, allowed, scope):
    text = "class Task:\n" + indent(statement, "    ") + "\n    def run_pure(self, inputs, params):\n        return {}\n"
    parsed = PythonSourceFile.parse("/virtual/class_body.py", "class_body", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Class body effect probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, parsed.path, "Task"),), (parsed,))
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources,"node_catalog":(),"source_owners":()})
    catalog = load_builtin_plugins("python").catalogs
    rules = {item.id:item for item in catalog.rules}
    handlers = {item.id:native_binding(catalog, "rule", item.id) for item in catalog.rules}
    ruleset = RulesetDescriptor("example.class.effects", calls=(RuleCall("effects", rule_id="vibeflow.no_side_effects",
        params={"effect_scope":scope}),))
    plan = complete_source_policy_plan(compile_ruleset(ruleset, rules=rules, rulesets={ruleset.id:ruleset}), handlers=handlers)
    result = execute_rule_plan(plan, context, handlers=handlers)
    assert bool(result.findings) == (scope not in allowed), (scope, statement, result.findings)
    assert result.results["effects"].records["effect_policy"].value["effect_scope"] == scope
    assert all(item.source_location["path"] == parsed.path for item in result.findings)
    assert all(item.source_location["line"] == 2 for item in result.findings)


def test_branch_join_drops_alias_overwritten_in_every_branch():
    body = "import sys\nimport math\np = sys\nif marker:\n    p = math\nelse:\n    p = math\np.path = []\nreturn 1"
    for kind in ("python_source", "node", "base_lib", "plugin"):
        assert no_side_effects(_context(kind, body), {}, {"effect_scope":"global_state"}).findings == (), kind


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body,allowed", [
    ("import sys\nreturn getattr(sys, 'stdout')", {"terminal", "python_io"}),
    ("import sys\nreturn getattr(sys, 'argv')", set()),
    ("import sys\nreturn vars(sys)['stdout']", {"terminal", "python_io"}),
    ("import sys\nreturn vars(sys)['argv']", set()),
    ("import sys\nsys = object()\nreturn getattr(sys, 'stdout', None)", {"none", "terminal", "python_io", "global_state", "trusted"}),
])
def test_literal_reflected_values_use_the_same_reference_effects(scope, body, allowed):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert bool(result.findings) == (scope not in allowed), (kind, scope, body, result.findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_assignment_from_joined_alias_keeps_possible_host_targets(scope):
    body = "import sys\nimport math\nif marker:\n    p = math\nelse:\n    p = sys\nq = p\nq.path = []\nreturn 1"
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert result.findings, (kind, scope, result)


def test_function_scope_restores_alias_candidates_for_later_definitions():
    text = ("import sys\nimport math\np = math\n"
            "def first():\n    if marker:\n        p = sys\n    else:\n        p = math\n    return 1\n"
            "def after():\n    p.path = []\n    return 1\n")
    context = _resource_context("base_lib", text)
    assert no_side_effects(context, {}, {"effect_scope":"global_state"}).findings == ()


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("header", [
    'class Task(constructor(open("never-open"))):',
    '@constructor(open("never-open"))\nclass Task:',
])
def test_node_class_base_and_decorator_arguments_use_shared_effects(header, scope):
    text = ('def constructor(value):\n    return object\n' + header
            + '\n    def run_pure(self, inputs, params):\n        return {}\n')
    parsed = PythonSourceFile.parse("/virtual/class_header.py", "class_header", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Class header effect probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, parsed.path, "Task"),), (parsed,))
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources,"node_catalog":(),"source_owners":()})
    result = no_side_effects(context, {}, {"effect_scope":scope})
    assert result.state == "completed"
    assert bool(result.findings) == (scope != "python_io"), (scope, header, result.findings)
    assert all(item.source_location["path"] == parsed.path and item.source_location["line"] == 3 for item in result.findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
def test_existing_hard_ffi_markers_stay_forbidden_on_local_receivers(scope):
    body = "resource = object()\nresource.CDLL(None)\nreturn 1"
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert result.findings and any("CDLL" in item.message for item in result.findings), (kind, scope, result)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body,marker", [
    ("connection = params.get('connection')\nconnection.close()\nreturn 1", "connection.close"),
    ("from pathlib import Path\npath = Path('never-open')\npath.write_text('probe')\nreturn 1", "write_text"),
    ("file = open('never-open', 'w')\nfile.close()\nreturn 1", "file.close"),
    ("from contextlib import ExitStack\nstack = ExitStack()\nstack = params.get('connection')\nstack.close()\nreturn 1", "stack.close"),
    ("from contextlib import ExitStack\nstack = ExitStack()\nif marker:\n    stack = params.get('connection')\nstack.close()\nreturn 1", "stack.close"),
])
def test_local_receiver_calls_keep_conservative_io_classification(scope, body, marker):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert result.state == "completed"
        assert any(marker in item.message for item in result.findings) == (scope != "python_io"), (kind, scope, body, result.findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("body", [
    "import sys\nsys = object()\nsys.path.clear()\nreturn 1",
    "import builtins\nbuiltins = object()\nbuiltins.print('local')\nreturn 1",
    "builtins = object()\nbuiltins.eval('local')\nreturn 1",
    "os = object()\nos._exit(0)\nos.environ.clear()\nreturn 1",
    "ctypes = object()\nctypes.LibraryLoader(None)\nreturn 1",
    "cffi = object()\ncffi.FFI()\nreturn 1",
])
def test_local_shadow_removes_host_namespace_identity_without_whole_call_grant(scope, body):
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert result.findings == (), (kind, scope, body, result.findings)


@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("argv,denied", [("", True), ("[]", False), ("args=None", True)])
def test_local_parser_still_distinguishes_host_and_explicit_argv(scope, argv, denied):
    body = f"import argparse\nparser = argparse.ArgumentParser()\nparser.parse_args({argv})\nreturn 1"
    for kind in ("python_source", "node", "base_lib", "plugin"):
        result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
        assert any("parse_args" in item.message for item in result.findings) == denied, (kind, scope, argv, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("prefix", ["def", "async def"])
@pytest.mark.parametrize("reference", ["stdout", "argv"])
@pytest.mark.parametrize("signature", [
    "sys=sys.{reference}",
    "stream=sys.{reference}",
    "*, sys=sys.{reference}",
    "sys=None, stream=sys.{reference}",
    "*, sys=None, stream=sys.{reference}",
])
def test_function_defaults_use_enclosing_scope_before_parameter_bindings(kind, prefix, reference, signature):
    body = "import sys\n" + prefix + " helper(" + signature.format(reference=reference) + "):\n    return 1\nreturn 1"
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":"none"})
    assert result.state == "completed"
    matches = [item for item in result.findings if "sys." + reference in item.message]
    assert len(matches) == 1, (kind, prefix, reference, signature, result.findings)
    assert matches[0].source_location["path"] == "/virtual/example.py"


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("reference,allowed", [("stdout", {"terminal", "python_io"}), ("argv", set())])
def test_definition_time_host_references_preserve_selected_scope(kind, scope, reference, allowed):
    body = f"import sys\ndef helper(sys=sys.{reference}):\n    return sys\nreturn 1"
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
    assert result.state == "completed"
    assert bool(result.findings) == (scope not in allowed), (kind, scope, reference, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("prefix", ["def", "async def"])
@pytest.mark.parametrize("body,denied", [
    ("import sys\ndef helper(stream=sys.stdout):\n    sys = object()\n    return stream\nreturn 1", True),
    ("import sys as process\np = process\ndef helper(p=p.stdout):\n    return p\nreturn 1", True),
    ("import sys as process\np = process\ndef helper(p=None, stream=p.stdout):\n    return stream\nreturn 1", True),
    ("import sys\nsys = object()\ndef helper(sys=sys.stdout):\n    return sys\nreturn 1", False),
    ("import sys\ndef outer(sys):\n    def helper(stream=sys.stdout):\n        return stream\n    return helper\nreturn 1", False),
    ("import sys\ndef helper(sys=None):\n    return 1\ndef sibling(stream=sys.stdout):\n    return stream\nreturn 1", True),
    ("import sys\ndef helper(sys):\n    return sys.stdout\nreturn 1", False),
])
def test_default_scope_keeps_real_outer_aliases_and_shadows(kind, prefix, body, denied):
    # Change the checked nested helper while keeping its enclosing scope stable.
    body = body.replace("def helper(", prefix + " helper(")
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":"none"})
    assert result.state == "completed"
    assert bool(result.findings) == denied, (kind, prefix, body, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("scope", ["none", "terminal", "python_io", "global_state", "trusted"])
@pytest.mark.parametrize("expression,allowed", [
    ("lambda sys=sys.stdout: sys", {"terminal", "python_io"}),
    ("lambda sys=None, stream=sys.stdout: stream", {"terminal", "python_io"}),
    ("lambda sys: sys.stdout", {"none", "terminal", "python_io", "global_state", "trusted"}),
])
def test_lambda_defaults_and_parameter_body_use_separate_scopes(kind, scope, expression, allowed):
    body = "import sys\nhelper = " + expression + "\nreturn 1"
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":scope})
    assert result.state == "completed"
    assert bool(result.findings) == (scope not in allowed), (kind, scope, expression, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("prefix", ["def", "async def"])
@pytest.mark.parametrize("definition", [
    "def helper(emit=None, value=emit('default')):\n    return value",
    "def helper(*, emit=emit('kw-default')):\n    return emit",
    "def helper(emit: emit('argument-annotation')):\n    return 1",
    "def helper(emit) -> emit('return-annotation'):\n    return 1",
    "@emit('decorator')\ndef helper(emit):\n    return 1",
    "@emit('decorator')\ndef helper():\n    emit = lambda value: value\n    return 1",
])
def test_function_headers_resolve_effect_call_aliases_before_body_bindings(kind, prefix, definition):
    body = "from builtins import print as emit\n" + definition.replace("def helper(", prefix + " helper(") + "\nreturn 1"
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":"none"})
    assert result.state == "completed"
    assert any("builtins.print" in item.message for item in result.findings), (kind, prefix, definition, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("prefix", ["def", "async def"])
def test_function_header_call_preserves_real_enclosing_parameter_shadow(kind, prefix):
    body = ("from builtins import print as emit\ndef outer(emit):\n    " + prefix +
            " helper(emit=None, value=emit('local')):\n        return value\n    return helper\nreturn 1")
    result = no_side_effects(_context(kind, body), {}, {"effect_scope":"none"})
    assert result.state == "completed"
    assert result.findings == (), (kind, prefix, result.findings)


@pytest.mark.parametrize("target", ["method", "helper"])
@pytest.mark.parametrize("in_body", [False, True])
def test_function_headers_keep_enclosing_input_ownership_until_body(target, in_body):
    module = "inputs = {'seed': 1}\n"
    mutation = "inputs.pop('seed', None)"
    if target == "method":
        signature = "self, inputs, params" + ("" if in_body else "=" + mutation)
        body = ("        " + mutation + "\n" if in_body else "") + "        return {}\n"
        module += "class Task:\n    def run_pure(" + signature + "):\n" + body
    else:
        signature = "inputs" if in_body else "inputs, params=" + mutation
        body = ("    " + mutation + "\n" if in_body else "") + "    return {}\n"
        module += "def helper(" + signature + "):\n" + body
        module += "class Task:\n    def run_pure(self, inputs, params):\n        helper(inputs)\n        return {}\n"
    parsed = PythonSourceFile.parse("/virtual/definition_inputs.py", "definition_inputs", module)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Definition input scope probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, parsed.path, "Task"),), (parsed,))
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources, "node_catalog":(), "source_owners":()})
    result = no_side_effects(context, {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    assert any("mutate inputs" in item.message for item in result.findings) == in_body, (target, in_body, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("name", ["sys", "process"])
def test_nested_global_restores_module_host_alias_beyond_enclosing_parameter_shadow(kind, name):
    imported = "import sys" + (" as " + name if name != "sys" else "")
    text = (imported + "\ndef outer(" + name + "):\n    def helper():\n        global " + name +
            "\n        return " + name + ".argv\n    return helper\nclass Task:\n"
            "    def run_pure(self, inputs, params):\n        outer(None)\n        return {}\n")
    parsed = PythonSourceFile.parse("/virtual/global_function.py", "global_function", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Global header scope probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(descriptor, parsed.path, "Task"),) if kind == "node" else ()
    sources = build_python_source_context(nodes, (parsed,))
    owners = ({"kind":kind, "id":"example.task", "role":"entry", "path":parsed.path,
               "symbol":"Task" if kind == "node" else ""},)
    facts = {"source_context":sources, "node_catalog":(), "source_owners":owners}
    if kind == "python_source":
        facts.update(python_source=PythonSource(parsed.module, "global_function.py", parsed.path, text), source_file=parsed)
    elif kind == "base_lib":
        facts.update(base_lib_file=parsed, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=parsed, resource_symbol="")
    context = RuleContext(subject={"kind":kind, "id":"example.task", "type_key":"example.task"}, facts=facts, target="python")
    result = no_side_effects(context, {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    assert any("sys.argv" in item.message for item in result.findings), (kind, name, result.findings)



def _module_definition_context(kind, text, path):
    parsed = PythonSourceFile.parse(path, "definition_scope", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Definition scope probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(descriptor, parsed.path, "Task"),) if kind == "node" else ()
    sources = build_python_source_context(nodes, (parsed,))
    owners = ({"kind":kind, "id":"example.task", "role":"entry", "path":parsed.path,
               "symbol":"Task" if kind == "node" else ""},)
    facts = {"source_context":sources, "node_catalog":(), "source_owners":owners}
    if kind == "python_source":
        facts.update(python_source=PythonSource(parsed.module, "definition_scope.py", parsed.path, text), source_file=parsed)
    elif kind == "base_lib":
        facts.update(base_lib_file=parsed, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=parsed, resource_symbol="")
    return RuleContext(subject={"kind":kind, "id":"example.task", "type_key":"example.task"}, facts=facts, target="python")


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
def test_nested_global_restores_assignment_alias_from_real_module_scope(kind):
    text = ("from builtins import print as p\nemit = p\ndef outer(emit):\n"
            "    def helper():\n        global emit\n        emit('terminal')\n        return 1\n"
            "    return helper\nclass Task:\n    def run_pure(self, inputs, params):\n"
            "        outer(None)\n        return {}\n")
    result = no_side_effects(_module_definition_context(kind, text, "/virtual/global_assignment.py"),
        {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    assert any("builtins.print" in item.message for item in result.findings), (kind, result.findings)


@pytest.mark.parametrize("target", ["method", "helper"])
@pytest.mark.parametrize("body,denied", [
    ("def inner():\n    inputs.pop('seed', None)\ninner()", True),
    ("owned = inputs\ndef inner():\n    owned.pop('seed', None)\ninner()", True),
    ("def inner():\n    inputs = {}\n    inputs.pop('seed', None)\ninner()", False),
    ("inner = lambda inputs: inputs.pop('seed', None)\ninner({})", False),
    ("inner = lambda: inputs.pop('seed', None)\ninner()", True),
    ("inner = lambda inputs=inputs.pop('seed', None): inputs\ninner()", True),
    ("def inner(inputs=inputs.pop('seed', None)):\n    return inputs\ninner()", True),
])
def test_nested_function_and_lambda_input_ownership_follows_real_bindings(target, body, denied):
    statements = body + "\nreturn {}\n"
    if target == "method":
        text = "class Task:\n    def run_pure(self, inputs, params):\n" + indent(statements, "        ")
    else:
        text = "def helper(inputs):\n" + indent(statements, "    ")
        text += "class Task:\n    def run_pure(self, inputs, params):\n        helper(inputs)\n        return {}\n"
    result = no_side_effects(_module_definition_context("node", text, "/virtual/owned_nested.py"),
        {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    assert any("mutate inputs" in item.message for item in result.findings) == denied, (target, body, result.findings)



def test_node_helper_slice_excludes_same_named_module_initializer_under_real_parameter_shadow():
    text = ("from builtins import print as p\nemit = p('unselected initializer')\ndef outer(emit):\n"
            "    def helper():\n        emit('local receiver')\n        return 1\n"
            "    return helper\nclass Task:\n    def run_pure(self, inputs, params):\n"
            "        outer(lambda value: value)\n        return {}\n")
    result = no_side_effects(_module_definition_context("node", text, "/virtual/shadowed_initializer.py"),
        {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    assert result.findings == (), result.findings


@pytest.mark.parametrize("parameter", ["emit", "value"])
def test_node_helper_defaults_resolve_module_assignment_alias_before_own_parameter_shadow(parameter):
    text = ("from builtins import print as p\nemit = p\ndef helper(" + parameter + "=emit('default')):\n"
            "    return {}\nclass Task:\n    def run_pure(self, inputs, params):\n"
            "        helper()\n        return {}\n")
    result = no_side_effects(_module_definition_context("node", text, "/virtual/assigned_header_alias.py"),
        {}, {"effect_scope":"global_state"})
    assert result.state == "completed"
    matches = [item for item in result.findings if "builtins.print" in item.message]
    assert matches, (parameter, result.findings)
    assert all(item.source_location["line"] == 3 for item in matches)



def _cross_file_callable_scope_context(kind, text, *, helper_effect=False):
    entry = PythonSourceFile.parse("/virtual/callable_entry.py", "callable_entry", text)
    helper_text = "def close():\n    return " + ("open('never-open').read()" if helper_effect else "1") + "\n"
    helper = PythonSourceFile.parse("/virtual/callable_helper.py", "callable_helper", helper_text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Callable scope facts probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(descriptor, entry.path, "Task"),) if kind == "node" else ()
    sources = build_python_source_context(nodes, (entry, helper))
    assert helper.path in {item.path for item in sources.import_closure(entry.path)}
    owners = tuple({"kind":kind, "id":"example.task", "role":"entry" if source is entry else "support",
                   "path":source.path, "symbol":"Task" if kind == "node" and source is entry else ""}
                   for source in (entry, helper))
    facts = {"source_context":sources, "node_catalog":(), "source_owners":owners}
    if kind == "python_source":
        pairs = tuple((PythonSource(source.module, source.module + ".py", source.path, source.text), source)
                      for source in (entry, helper))
        facts.update(python_source=pairs[0][0], source_file=entry, python_sources=pairs)
    elif kind == "base_lib":
        facts.update(base_lib_file=entry, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=entry, resource_symbol="")
    context = RuleContext(subject={"kind":kind, "id":"example.task", "type_key":"example.task"}, facts=facts, target="python")
    return context, sources, entry, helper


def _effect_call_findings(result):
    return tuple(item for item in result.findings if item.code in
                 {"QUALITY.SIDE_EFFECT.CALL", "NODE.EFFECT.CALL_FORBIDDEN", "BASE_LIB.SIDE_EFFECT_CALL"})


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("placement", ["function_default", "function_body"])
@pytest.mark.parametrize("expression,resolved", [
    ("lambda close: close()", False),
    ("lambda *, close: close()", False),
    ("lambda close=close: close()", False),
    ("lambda value=close(): value", True),
    ("lambda close=close(): close", True),
    ("lambda: close()", True),
])
def test_lambda_reference_facts_distinguish_defaults_and_bound_parameters(kind, placement, expression, resolved):
    if placement == "function_default":
        definition = "def task(fn=" + expression + "):\n    return fn\n"
    else:
        definition = "def task():\n    return " + expression + "\n"
    text = ("from callable_helper import close\n" + definition +
            "class Task:\n    def run_pure(self, inputs, params):\n        task()\n        return {}\n")
    context, sources, entry, helper = _cross_file_callable_scope_context(kind, text)
    function = next(item for item in entry._tree.body if isinstance(item, ast.FunctionDef))
    lambda_node = next(item for item in ast.walk(function) if isinstance(item, ast.Lambda))
    calls = tuple(item for item in ast.walk(lambda_node) if isinstance(item, ast.Call)
                  and isinstance(item.func, ast.Name) and item.func.id == "close")
    assert len(calls) == 1
    site = (calls[0].lineno, calls[0].col_offset + 1)
    available = sources.resolved_function_calls(entry.path)
    assert (site in available) == resolved, (kind, placement, expression, available)
    # Returning a parameter value is not a source-proven callable reference,
    # even when a same-named imported function was used by its default.
    parameter_names = {argument.arg for argument in
                       (*lambda_node.args.posonlyargs, *lambda_node.args.args, *lambda_node.args.kwonlyargs)}
    for reference in ast.walk(lambda_node.body):
        if isinstance(reference, ast.Name) and reference.id in parameter_names:
            assert (reference.lineno, reference.col_offset + 1) not in available, (kind, expression, available)
    result = no_side_effects(context, {}, {"effect_scope":"none"})
    assert result.state == "completed"
    effects = _effect_call_findings(result)
    matches = tuple(item for item in effects if item.source_location["path"] == entry.path
                    and (item.source_location["line"], item.source_location["column"]) == site)
    assert bool(matches) == (not resolved), (kind, placement, expression, result.findings)
    if resolved:
        assert effects == (), (kind, placement, expression, result.findings)


@pytest.mark.parametrize("kind", ["python_source", "node", "base_lib", "plugin"])
@pytest.mark.parametrize("parameter", ["clean", "value"])
@pytest.mark.parametrize("helper_effect", [False, True])
def test_module_callable_alias_default_keeps_real_function_body_and_structure(kind, parameter, helper_effect):
    text = ("from callable_helper import close\nclean = close\ndef task(" + parameter + "=clean()):\n"
            "    return 1\nclass Task:\n    def run_pure(self, inputs, params):\n        task()\n        return {}\n")
    context, sources, entry, helper = _cross_file_callable_scope_context(kind, text, helper_effect=helper_effect)
    call = next(item for item in ast.walk(entry._tree) if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name) and item.func.id == "clean")
    site = (call.lineno, call.col_offset + 1)
    assert site in sources.resolved_function_calls(entry.path), (kind, parameter, sources.references)
    result = no_side_effects(context, {}, {"effect_scope":"none"})
    assert result.state == "completed"
    effects = _effect_call_findings(result)
    assert bool(effects) == helper_effect, (kind, parameter, helper_effect, result.findings)
    assert all(item.source_location["path"] == helper.path for item in effects), (kind, parameter, result.findings)
    if kind in {"node", "base_lib", "plugin"}:
        assert any(item.code in {"BASE_LIB.GLOBAL_STATE", "NODE.PURITY.MODULE_GLOBAL_STATE"}
                   and item.source_location["path"] == entry.path for item in result.findings), (kind, result.findings)
