"""Declared binding identity of owned inputs remains stable across closures."""
import ast
from textwrap import indent

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_analysis.input_tracking import (
    _input_call_facts, _trace_helper_input_parameters, source_input_parameters,
)
from vibeflow.targets.python.quality.source_context import (
    PythonSourceFile, PythonSourceNode, build_python_source_context,
)


CASES = (('nonlocal_assign',
  'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs\ninner()\nsink(alias)',
  True),
 ('nonlocal_walrus',
  'alias = {}\ndef inner():\n    nonlocal alias\n    (alias := inputs)\ninner()\nsink(alias)',
  True),
 ('nonlocal_get',
  'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs.get("nested")\ninner()\nsink(alias)',
  True),
 ('nonlocal_multilevel',
  'alias = {}\n'
  'def middle():\n'
  '    def inner():\n'
  '        nonlocal alias\n'
  '        alias = inputs\n'
  '    inner()\n'
  'middle()\n'
  'sink(alias)',
  True),
 ('nonlocal_multilevel_declarations',
  'alias = {}\n'
  'def middle():\n'
  '    nonlocal alias\n'
  '    def inner():\n'
  '        nonlocal alias\n'
  '        alias = inputs\n'
  '    inner()\n'
  'middle()\n'
  'sink(alias)',
  True),
 ('nonlocal_nearest_binding_keeps_caller_local',
  'alias = {}\n'
  'def middle():\n'
  '    alias = {}\n'
  '    def inner():\n'
  '        nonlocal alias\n'
  '        alias = inputs\n'
  '    inner()\n'
  'middle()\n'
  'sink(alias)',
  False),
 ('nonlocal_keyword',
  'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs\ninner()\nsink(payload=alias)',
  True),
 ('nonlocal_comp_walrus',
  'alias = {}\n'
  'def inner():\n'
  '    nonlocal alias\n'
  '    list(alias := inputs for item in (0,))\n'
  'inner()\n'
  'sink(alias)',
  True),
 ('nonlocal_comp_local_inputs',
  'alias = {}\n'
  'def inner():\n'
  '    nonlocal alias\n'
  '    list(alias := inputs for inputs in ({},))\n'
  'inner()\n'
  'sink(alias)',
  False),
 ('nonlocal_lambda_default_comp',
  'alias = {}\n'
  'def inner():\n'
  '    nonlocal alias\n'
  '    values = [lambda value=(alias := inputs): value for item in (0,)]\n'
  'inner()\n'
  'sink(alias)',
  True),
 ('nonlocal_function_default',
  'alias = {}\n'
  'def inner():\n'
  '    nonlocal alias\n'
  '    def nested(value=(alias := inputs)):\n'
  '        return value\n'
  'inner()\n'
  'sink(alias)',
  True),
 ('nonlocal_lambda_body_stays_local',
  'alias = {}\n'
  'def inner():\n'
  '    nonlocal alias\n'
  '    fn = lambda: (alias := inputs)\n'
  '    fn()\n'
  'inner()\n'
  'sink(alias)',
  False),
 ('global_assign', 'def inner():\n    global alias\n    alias = inputs\ninner()\nsink(alias)', True),
 ('local_annotated_alias', 'alias: dict = inputs\nsink(alias)', True),
 ('annotated_child_local_stays_local',
  'alias = {}\ndef inner():\n    alias: dict = inputs\ninner()\nsink(alias)',
  False),
 ('global_outer_decl_free_closure',
  'global alias\nalias = inputs\ndef inner():\n    sink(alias)\ninner()',
  True),
 ('middle_global_decl_free_closure',
  'alias = {}\n'
  'def middle():\n'
  '    global alias\n'
  '    alias = inputs\n'
  '    def inner():\n'
  '        sink(alias)\n'
  '    inner()\n'
  'middle()',
  True),
 ('global_direct', 'global alias\nalias = inputs\nsink(alias)', True),
 ('global_walrus', 'def inner():\n    global alias\n    (alias := inputs)\ninner()\nsink(alias)', True),
 ('global_same_named_caller_local',
  'alias = {}\ndef inner():\n    global alias\n    alias = inputs\ninner()\nsink(alias)',
  False),
 ('global_multilevel_with_middle_local',
  'def middle():\n'
  '    alias = {}\n'
  '    def inner():\n'
  '        global alias\n'
  '        alias = inputs\n'
  '    inner()\n'
  'middle()\n'
  'sink(alias)',
  True),
 ('global_inner_same_named_local_stays_local',
  'def middle():\n'
  '    alias = {}\n'
  '    def inner():\n'
  '        global alias\n'
  '        alias = inputs\n'
  '    inner()\n'
  '    sink(alias)\n'
  'middle()',
  False),
 ('global_comp_lambda_default',
  'def inner():\n'
  '    global alias\n'
  '    values = [lambda value=(alias := inputs): value for item in (0,)]\n'
  'inner()\n'
  'sink(alias)',
  True),
 ('global_comp_lambda_default_local_control',
  'alias = {}\n'
  'def inner():\n'
  '    global alias\n'
  '    values = [lambda value=(alias := inputs): value for item in (0,)]\n'
  'inner()\n'
  'sink(alias)',
  False),
 ('global_lambda_body_stays_local',
  'def inner():\n    global alias\n    fn = lambda: (alias := inputs)\n    fn()\ninner()\nsink(alias)',
  False),
 ('global_read_does_not_capture_same_named_outer_inputs',
  'def inner():\n    global inputs\n    sink(inputs)\ninner()',
  False),
 ('ordinary_child_local_does_not_escape',
  'alias = {}\ndef inner():\n    alias = inputs\ninner()\nsink(alias)',
  False),
 ('lambda_default_binds_parent', 'fn = lambda value=(alias := inputs): value\nsink(alias)', True),
 ('function_default_binds_parent',
  'def inner(value=(alias := inputs)):\n    return value\nsink(alias)',
  True),
 ('lambda_parameter_shadows_inputs', '(lambda inputs: sink(inputs))({})', False),
 ('lambda_captures_inputs', '(lambda: sink(inputs))()', True),
 ('branch_possible_alias_preserved', 'if params["flag"]:\n    alias = inputs\nsink(alias)', True),
 ('loop_possible_alias_preserved', 'for item in ():\n    alias = inputs\nsink(alias)', True),
 ('late_closure_preserved', 'def inner():\n    return sink(alias)\nalias = inputs\ninner()', True))


def _source(text):
    compile(text, "/virtual/input_binding.py", "exec")
    source = PythonSourceFile.parse("/virtual/input_binding.py", "input_binding", text)
    descriptor = NodeDescriptor(type_key="example.task", display_name="Task", description="Declared binding ownership.",
        version="1", flow_kind="process", contract=NodeContractDescriptor())
    node = PythonSourceNode(descriptor, source.path, "Task")
    context = build_python_source_context((node,), (source,))
    return source, node, context


@pytest.mark.parametrize("label,body,owned", CASES, ids=[row[0] for row in CASES])
def test_declared_input_binding_owner_reaches_helper_without_tainting_other_bindings(label, body, owned):
    text = ("alias = None\ninputs = {}\ndef sink(payload):\n    return payload.pop('seed', None)\n"
            "class Task:\n    def run_pure(self, inputs, params):\n") + indent(body + "\nreturn {}\n", "        ")
    source, node, sources = _source(text)
    before = ast.dump(source._tree)
    formal = source_input_parameters(sources, node)
    fallback = _trace_helper_input_parameters(source._tree, "Task")
    result = no_side_effects(RuleContext(subject={"kind":"node", "type_key":"example.task"}, target="python",
        facts={"source_context":sources, "node_catalog":(), "source_owners":()}), {}, {"effect_scope":"global_state"})
    mutations = tuple(item for item in result.findings if "mutate inputs" in item.message)
    assert ("payload" in formal.get(source.path + ":sink", set())) == owned, (label, formal)
    assert ("payload" in fallback.get("sink", set())) == owned, (label, fallback)
    assert bool(mutations) == owned, (label, result.findings)
    assert result.state == "completed"
    if owned:
        assert all(item.source_location["line"] == 4 for item in mutations), (label, result.findings)
    assert {"alias", "inputs"} <= {symbol.name for symbol in sources.symbols if symbol.kind == "global"}
    assert ast.dump(source._tree) == before


def test_selected_function_root_keeps_external_nonlocal_cell_separate_from_module_global():
    text = ("alias = None\ndef sink(payload):\n    return payload.pop('seed', None)\nclass Task:\n"
            "    def run_pure(self, inputs, params):\n        alias = {}\n        def inner(owned):\n"
            "            nonlocal alias\n            alias = owned\n            sink(alias)\n"
            "            def global_reader():\n                global alias\n                sink(alias)\n"
            "            global_reader()\n        inner(inputs)\n        return {}\n")
    source, node, sources = _source(text)
    inner = next(symbol for symbol in sources.symbols if symbol.name == "Task.run_pure.inner")
    calls = _input_call_facts(inner._node, {"owned"})
    sites = {call.lineno: flags[0][0] for call, flags in calls.items() if getattr(call.func, "id", None) == "sink"}
    assert sites == {10: True, 13: False}
    # Actual parameter seeds come from the resolved inner(inputs) call even
    # when the selected helper root no longer includes the containing frame.
    formal = source_input_parameters(sources, node)
    assert formal[inner.id] == {"owned"}
    assert formal[source.path + ":sink"] == {"payload"}


@pytest.mark.parametrize("text", (
    "def outer():\n    alias = None\n    def middle():\n        global alias\n        def inner():\n            nonlocal alias\n",
    "def outer():\n    values = [alias for alias in ()]\n    def inner():\n        nonlocal alias\n",
    "def outer():\n    alias = None\n    def inner():\n        nonlocal alias\n        alias: dict = {}\n",
    "def outer():\n    global alias\n    alias: dict = {}\n",
))
def test_invalid_nonlocal_binders_are_syntax_controls_not_permission_exceptions(text):
    with pytest.raises(SyntaxError):
        compile(text, "/virtual/invalid_binding.py", "exec")
