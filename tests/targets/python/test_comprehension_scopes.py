"""Comprehension bindings preserve effect, input and source-reference scopes."""

import ast
from textwrap import indent

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality import PythonSource
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context


KINDS = ("python_source", "node", "base_lib", "plugin")
SCOPES = ("none", "terminal", "python_io", "global_state", "trusted")
FORMS = ("list", "set", "dict", "generator")
CALL_CODES = {"QUALITY.SIDE_EFFECT.CALL", "NODE.EFFECT.CALL_FORBIDDEN", "BASE_LIB.SIDE_EFFECT_CALL"}


def _comprehension(form, target, iterable="()", value=None):
    value = target if value is None else value
    if form == "list":
        return "[" + value + " for " + target + " in " + iterable + "]"
    if form == "set":
        return "{" + value + " for " + target + " in " + iterable + "}"
    if form == "dict":
        return "{" + value + ": " + value + " for " + target + " in " + iterable + "}"
    return "(" + value + " for " + target + " in " + iterable + ")"


def _definition(expression, placement):
    if placement == "lambda":
        return "def task():\n    return (lambda: " + expression + ")()\n"
    return "def task():\n    return " + expression + "\n"


def _context(kind, definition, *, prefix="import sys\n", helper_effect=None):
    text = prefix + definition
    if kind == "node":
        text += "class Task:\n    def run_pure(self, inputs, params):\n        task()\n        return {}\n"
    entry = PythonSourceFile.parse("/virtual/comprehension_entry.py", "comprehension_entry", text)
    files = (entry,)
    helper = None
    if helper_effect is not None:
        helper_text = "def close():\n    return " + ("open('never-open').read()" if helper_effect else "(1,)") + "\n"
        helper = PythonSourceFile.parse("/virtual/comprehension_helper.py", "comprehension_helper", helper_text)
        files += (helper,)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Comprehension scope probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(descriptor, entry.path, "Task"),) if kind == "node" else ()
    sources = build_python_source_context(nodes, files)
    owners = tuple({"kind":kind, "id":"example.task", "role":"entry" if source is entry else "support",
                   "path":source.path, "symbol":"Task" if kind == "node" and source is entry else ""}
                   for source in files)
    facts = {"source_context":sources, "node_catalog":(), "source_owners":owners}
    if kind == "python_source":
        pairs = tuple((PythonSource(source.module, source.module + ".py", source.path, source.text), source)
                      for source in files)
        facts.update(python_source=pairs[0][0], source_file=entry, python_sources=pairs)
    elif kind == "base_lib":
        facts.update(base_lib_file=entry, resource_symbol="")
    elif kind == "plugin":
        facts.update(resource_source_file=entry, resource_symbol="")
    context = RuleContext(subject={"kind":kind, "id":"example.task", "type_key":"example.task"},
                          facts=facts, target="python")
    return context, sources, entry, helper


def _evaluate(context, scope="global_state"):
    result = no_side_effects(context, {}, {"effect_scope":scope})
    assert result.state == "completed"
    return result


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("placement", ("function", "lambda"))
def test_comprehension_targets_do_not_bind_enclosing_function_or_lambda(kind, scope, form, placement):
    expression = "(sys.argv, " + _comprehension(form, "sys") + ")"
    context, _, _, _ = _context(kind, _definition(expression, placement))
    result = _evaluate(context, scope)
    assert any("sys.argv" in item.message for item in result.findings), (kind, scope, form, placement, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("placement", ("function", "lambda"))
def test_first_comprehension_iterable_keeps_enclosing_host_identity(kind, form, placement):
    expression = _comprehension(form, "sys", "sys.argv")
    context, _, _, _ = _context(kind, _definition(expression, placement))
    result = _evaluate(context)
    assert any("sys.argv" in item.message for item in result.findings), (kind, form, placement, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("expression,denied", [
    ("[sys.argv for sys in ()]", False),
    ("{sys.argv for sys in ()}", False),
    ("{sys.argv: sys.argv for sys in ()}", False),
    ("(sys.argv for sys in ())", False),
    ("[sys.argv for (sys, item) in ()]", False),
    ("[sys.argv for sys in () if sys.argv for item in sys.argv]", False),
    ("[sys.argv for item in () for sys in () if sys.argv]", False),
    ("[([sys.argv for sys in ()], sys.argv) for sys in ()]", False),
    ("[([sys.argv for sys in ()], sys.argv) for item in ()]", True),
    ("[(lambda: sys.argv) for sys in ()]", False),
    ("[(lambda: sys.argv) for item in ()]", True),
    ("[(lambda: (sys.argv, [sys for sys in ()])) for item in ()]", True),
])
def test_comprehension_internal_bindings_restore_at_nested_boundaries(kind, expression, denied):
    context, _, _, _ = _context(kind, _definition(expression, "lambda"))
    result = _evaluate(context)
    matches = [item for item in result.findings if "sys.argv" in item.message]
    assert bool(matches) == denied, (kind, expression, result.findings)
    if not denied:
        assert result.findings == (), (kind, expression, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("placement", ("function", "lambda"))
@pytest.mark.parametrize("expression,denied", [
    ("([(sys := None) for item in (0,)], sys.argv)", False),
    ("([(process := sys) for item in (0,)], process.argv)", True),
    ("([(process := sys) for item in (0,)], (lambda: process.argv)())", True),
])
def test_comprehension_walrus_binds_and_preserves_aliases_in_enclosing_scope(kind, placement, expression, denied):
    context, _, _, _ = _context(kind, _definition(expression, placement))
    result = _evaluate(context)
    assert any("sys.argv" in item.message for item in result.findings) == denied, (kind, placement, expression, result.findings)
    if not denied:
        assert result.findings == (), (kind, placement, expression, result.findings)


INPUT_CASES = tuple((form + "." + mode, expression, denied)
    for form in FORMS
    for mode, expression, denied in (
        ("outside", "(" + _comprehension(form, "inputs") + ", inputs.pop('seed', None))", True),
        ("lambda_outside", "(lambda: (inputs.pop('seed', None), " + _comprehension(form, "inputs") + "))()", True),
        ("first_iterable", _comprehension(form, "inputs", "inputs.pop('seed', ())"), True),
        ("inside", _comprehension(form, "inputs", value="inputs.pop('seed', None)"), False),
    )) + (
    ("lambda_captures_local_target", "[(lambda: inputs.pop('seed', None))() for inputs in ()]", False),
    ("lambda_captures_owned_outer", "[(lambda: inputs.pop('seed', None))() for item in ()]", True),
)


@pytest.mark.parametrize("placement", ("method", "helper"))
@pytest.mark.parametrize("label,expression,denied", INPUT_CASES, ids=[item[0] for item in INPUT_CASES])
def test_comprehension_input_ownership_uses_actual_outer_and_target_bindings(placement, label, expression, denied):
    statements = "value = " + expression + "\nreturn {}\n"
    if placement == "method":
        text = "class Task:\n    def run_pure(self, inputs, params):\n" + indent(statements, "        ")
    else:
        text = "def task(inputs):\n" + indent(statements, "    ")
        text += "class Task:\n    def run_pure(self, inputs, params):\n        task(inputs)\n        return {}\n"
    entry = PythonSourceFile.parse("/virtual/comprehension_inputs.py", "comprehension_inputs", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Owned comprehension input probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, entry.path, "Task"),), (entry,))
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources, "node_catalog":(), "source_owners":()})
    result = _evaluate(context)
    assert any("mutate inputs" in item.message for item in result.findings) == denied, (placement, label, result.findings)


CALLABLE_CASES = tuple((form + "." + mode, expression, resolved)
    for form in FORMS
    for mode, expression, resolved in (
        ("outside", "(close(), " + _comprehension(form, "close") + ")", True),
        ("inside", _comprehension(form, "close", value="close()"), False),
        ("first_iterable", _comprehension(form, "close", "close()", value="1"), True),
    )) + (
    ("lambda_captures_local_target", "[(lambda: close())() for close in ()]", False),
    ("lambda_captures_import", "[(lambda: close())() for item in ()]", True),
    ("nested_comprehension_captures_local_target", "[[close() for item in ()] for close in ()]", False),
    # This compiles, but would raise UnboundLocalError on iteration. Its call
    # must never be granted an imported function's body proof; we only parse it.
    ("later_target_is_lexical_local", "[item for item in (1,) if close() for close in ()]", False),
)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("helper_effect", (False, True))
@pytest.mark.parametrize("label,expression,resolved", CALLABLE_CASES, ids=[item[0] for item in CALLABLE_CASES])
def test_comprehension_callable_facts_follow_real_cross_file_bindings(kind, helper_effect, label, expression, resolved):
    context, sources, entry, helper = _context(kind, _definition(expression, "lambda"),
        prefix="from comprehension_helper import close\n", helper_effect=helper_effect)
    assert helper.path in {source.path for source in sources.import_closure(entry.path)}
    calls = tuple(item for item in ast.walk(entry._tree) if isinstance(item, ast.Call)
                  and isinstance(item.func, ast.Name) and item.func.id == "close")
    assert calls
    sites = {(call.lineno, call.col_offset + 1) for call in calls}
    actual = sources.resolved_function_calls(entry.path)
    assert all((site in actual) == resolved for site in sites), (kind, helper_effect, label, actual, sources.references)
    result = _evaluate(context, "none")
    effects = tuple(item for item in result.findings if item.code in CALL_CODES)
    entry_effects = tuple(item for item in effects if item.source_location["path"] == entry.path
                         and (item.source_location["line"], item.source_location["column"]) in sites)
    actual_sites = {(item.source_location["line"], item.source_location["column"]) for item in entry_effects}
    assert actual_sites == (set() if resolved else sites), (kind, helper_effect, label, result.findings)
    if resolved:
        assert bool(effects) == helper_effect, (kind, helper_effect, label, result.findings)
        assert all(item.source_location["path"] == helper.path for item in effects), (kind, label, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("form", FORMS)
def test_incremental_starred_tuple_target_keeps_host_name_local(kind, form):
    expression = _comprehension(form, "(item, *sys)", value="sys.argv")
    context, _, _, _ = _context(kind, _definition(expression, "lambda"))
    assert _evaluate(context).findings == ()


def _walrus_comprehension(form, target, iterable, value):
    # Dictionary keys stay immutable so a real temporary-input evaluation is
    # valid too; the assignment expression belongs only to its value.
    if form == "dict":
        return "{0: " + value + " for " + target + " in " + iterable + "}"
    return _comprehension(form, target, iterable, value)


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("via_helper", (False, True))
@pytest.mark.parametrize("owned", (False, True))
def test_incremental_comprehension_walrus_preserves_real_input_aliases(form, via_helper, owned):
    target, iterable = ("item", "(0,)") if owned else ("inputs", "({},)")
    expression = _walrus_comprehension(form, target, iterable, "(alias := inputs)")
    # Consuming the generator makes its walrus assignment real before use.
    statements = "values = list(" + expression + ")\n"
    statements += "sink(alias)\n" if via_helper else "alias.pop('seed', None)\n"
    text = "def sink(payload):\n    return payload.pop('seed', None)\n" if via_helper else ""
    text += "class Task:\n    def run_pure(self, inputs, params):\n" + indent(statements + "return {}\n", "        ")
    entry = PythonSourceFile.parse("/virtual/comprehension_walrus_inputs.py", "comprehension_walrus_inputs", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Walrus-owned input probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, entry.path, "Task"),), (entry,))
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources, "node_catalog":(), "source_owners":()})
    result = _evaluate(context)
    assert any("mutate inputs" in item.message for item in result.findings) == owned, (form, via_helper, owned, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("placement", ("function", "lambda"))
def test_incremental_walrus_host_alias_escapes_each_comprehension_form(kind, form, placement):
    comprehension = _walrus_comprehension(form, "item", "(0,)", "(sys_alias := sys)")
    expression = "(list(" + comprehension + "), sys_alias.argv)"
    context, _, _, _ = _context(kind, _definition(expression, placement))
    result = _evaluate(context)
    assert any("sys.argv" in item.message for item in result.findings), (kind, form, placement, result.findings)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("placement", ("function", "lambda"))
@pytest.mark.parametrize("value,reference,denied", [
    ("(lambda value=(sys := None): value)", "sys.argv", False),
    ("(lambda value=(sys_alias := sys): value)", "sys_alias.argv", True),
    ("(lambda: (sys := None))", "sys.argv", True),
])
def test_incremental_lambda_default_walrus_uses_outer_scope_but_body_stays_local(kind, form, placement, value, reference, denied):
    comprehension = _walrus_comprehension(form, "item", "(0,)", value)
    expression = "(list(" + comprehension + "), " + reference + ")"
    context, _, _, _ = _context(kind, _definition(expression, placement))
    result = _evaluate(context)
    assert any("sys.argv" in item.message for item in result.findings) == denied, (kind, form, placement, value, result.findings)
    if not denied:
        assert result.findings == (), (kind, form, placement, value, result.findings)


HELPER_CALLSITE_CASES = tuple((form + (".owned" if owned else ".local"), expression, owned)
    for form in FORMS
    for owned in (False, True)
    for expression in (_comprehension(form, "item" if owned else "inputs", "(0,)" if owned else "({},)",
                                      "sink(inputs)"),)) + (
    ("lambda_parameter_is_local", "(lambda inputs: sink(inputs))({})", False),
    ("lambda_captures_owned_input", "(lambda: sink(inputs))()", True),
    ("local_comprehension_plus_real_owned_call", "([sink(inputs) for inputs in ({},)], sink(inputs))", True),
    ("local_lambda_plus_real_owned_call", "((lambda inputs: sink(inputs))({}), sink(inputs))", True),
)


@pytest.mark.parametrize("label,expression,owned", HELPER_CALLSITE_CASES, ids=[item[0] for item in HELPER_CALLSITE_CASES])
def test_incremental_helper_callsite_input_identity_respects_local_scopes(label, expression, owned):
    text = ("def sink(payload):\n    return payload.pop('seed', None)\n"
            "class Task:\n    def run_pure(self, inputs, params):\n        value = " + expression + "\n        return {}\n")
    # Compilation validates only syntax. Inspected Node/helper code is never
    # imported or run, and this test does not construct real business inputs.
    compile(text, "/virtual/comprehension_helper_callsite.py", "exec")
    entry = PythonSourceFile.parse("/virtual/comprehension_helper_callsite.py", "comprehension_helper_callsite", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Call-site input scope probe.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    sources = build_python_source_context((PythonSourceNode(descriptor, entry.path, "Task"),), (entry,))
    helper = next(symbol for symbol in sources.symbols if symbol.name == "sink")
    assert any(reference.kind == "call" and reference.target == helper.id for reference in sources.references)
    context = RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources, "node_catalog":(), "source_owners":()})
    result = _evaluate(context)
    mutations = tuple(item for item in result.findings if "mutate inputs" in item.message)
    assert bool(mutations) == owned, (label, result.findings)
    if owned:
        assert all(item.source_location["line"] == 2 for item in mutations), (label, result.findings)
