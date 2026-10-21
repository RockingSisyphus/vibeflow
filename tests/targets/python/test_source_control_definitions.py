"""Control suites preserve canonical definitions and their lexical calls."""

import ast
from textwrap import indent

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import (
    PythonSourceFile, PythonSourceNode, build_python_source_context,
)


CONTROL_SUITES = (
    ("if_body", "if params:\n{body}", 4, False),
    ("if_else", "if params:\n    pass\nelse:\n{body}", 4, False),
    ("for_body", "for item in (0,):\n{body}", 4, False),
    ("for_else", "for item in ():\n    pass\nelse:\n{body}", 4, False),
    ("while_body", "while params:\n{body}\n    break", 4, False),
    ("while_else", "while False:\n    pass\nelse:\n{body}", 4, False),
    ("with_body", "with manager:\n{body}", 4, False),
    ("try_body", "try:\n{body}\nexcept Exception:\n    pass", 4, False),
    ("try_handler", "try:\n    pass\nexcept (KeyError, ValueError):\n{body}", 4, False),
    ("try_else", "try:\n    pass\nexcept Exception:\n    pass\nelse:\n{body}", 4, False),
    ("try_finally", "try:\n    pass\nfinally:\n{body}", 4, False),
    ("try_star_handler", "try:\n    pass\nexcept* Exception:\n{body}", 4, False),
    ("match_case", "match params:\n    case _:\n{body}", 8, False),
    ("async_for_body", "async for item in stream:\n{body}", 4, True),
    ("async_with_body", "async with manager:\n{body}", 4, True),
)


def _context(text):
    path = "/virtual/source_control_definitions.py"
    compile(text, path, "exec")
    source = PythonSourceFile.parse(path, "source_control_definitions", text)
    descriptor = NodeDescriptor(rulesets=(), id="probe.controls", display_name="Controls", description="Control definitions.",
        version="1", flow_kind="process", contract=NodeContractDescriptor(), node_type="vibeflow.node")
    resource = PythonSourceNode(descriptor, path, "Task")
    return source, resource, build_python_source_context((resource,), (source,))


def _references(sources, source_name):
    return tuple(reference for reference in sources.references
                 if reference.kind == "call" and reference.source == sources.files[0].path + ":" + source_name)


@pytest.mark.parametrize("label,template,depth,asynchronous", CONTROL_SUITES,
                         ids=[row[0] for row in CONTROL_SUITES])
def test_control_suites_provide_same_scope_function_ast_and_call(label, template, depth, asynchronous):
    declaration = "def close():\n    return 1\nclose()"
    body = template.format(body=indent(declaration, " " * depth)) + "\nreturn {}\n"
    text = "class Task:\n    " + ("async " if asynchronous else "") + "def run_pure(self, inputs, params):\n" + indent(body, "        ")
    source, resource, sources = _context(text)
    before = ast.dump(source._tree)
    helper = sources.symbol(source.path, "Task.run_pure.close")
    actual = next(item for item in ast.walk(source._tree) if isinstance(item, ast.FunctionDef) and item.name == "close")
    assert helper is not None and helper._node is actual, label
    references = _references(sources, "Task.run_pure")
    calls = [item for item in ast.walk(source._tree) if isinstance(item, ast.Call)
             and isinstance(item.func, ast.Name) and item.func.id == "close"]
    assert len(calls) == 1
    assert [(item.target, item.line, item.column) for item in references] == [
        (helper.id, calls[0].lineno, calls[0].col_offset + 1)]
    assert (calls[0].lineno, calls[0].col_offset + 1) in sources.resolved_function_calls(source.path)
    assert helper in sources.helpers(resource.definition_id)
    assert ast.dump(source._tree) == before


def test_deeper_typed_control_suites_keep_the_actual_nested_function_target():
    source, _, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        try:
            if params:
                for item in (0,):
                    try:
                        pass
                    except (KeyError, ValueError):
                        with manager:
                            async def later(payload):
                                return payload
                            later(inputs)
        finally:
            pass
        return {}
""")
    helper = sources.symbol(source.path, "Task.run_pure.later")
    assert helper is not None and isinstance(helper._node, ast.AsyncFunctionDef)
    assert [item.target for item in _references(sources, "Task.run_pure")] == [helper.id]


def test_same_named_control_definitions_preserve_independent_lexical_identity():
    source, resource, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        def first():
            try:
                def mutate(payload):
                    payload.pop('seed', None)
                mutate(inputs)
            finally:
                pass
        def second():
            if params:
                def mutate(payload):
                    payload.pop('seed', None)
                mutate({})
        first()
        second()
        return {}
""")
    first = sources.symbol(source.path, "Task.run_pure.first.mutate")
    second = sources.symbol(source.path, "Task.run_pure.second.mutate")
    assert first is not None and second is not None
    assert first.id != second.id and first._node is not second._node
    assert [item.target for item in _references(sources, "Task.run_pure.first")] == [first.id]
    assert [item.target for item in _references(sources, "Task.run_pure.second")] == [second.id]


def test_child_function_body_references_are_not_reported_as_parent_calls():
    source, _, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        try:
            def outer():
                if params:
                    def hidden():
                        return 1
                    hidden()
            outer()
        finally:
            pass
        hidden()
        return {}
""")
    outer = sources.symbol(source.path, "Task.run_pure.outer")
    hidden = sources.symbol(source.path, "Task.run_pure.outer.hidden")
    assert outer is not None and hidden is not None
    assert [item.target for item in _references(sources, "Task.run_pure")] == [outer.id]
    assert [item.target for item in _references(sources, "Task.run_pure.outer")] == [hidden.id]
    outside = next(item for item in source._tree.body[0].body[0].body
                   if isinstance(item, ast.Expr) and isinstance(item.value, ast.Call))
    assert (outside.lineno, outside.col_offset + 1) not in sources.resolved_function_calls(source.path)


def test_module_control_definitions_keep_import_and_global_structure():
    source, _, sources = _context("""import math
try:
    marker = 1
    def close():
        return math.sqrt(marker)
except Exception:
    pass
class Task:
    def run_pure(self, inputs, params):
        close()
        return {}
""")
    helper = sources.symbol(source.path, "close")
    marker = sources.symbol(source.path, "marker")
    assert helper is not None and marker is not None and marker.kind == "global"
    assert [item.target for item in _references(sources, "Task.run_pure")] == [helper.id]
    assert any(item.kind == "global_reference" and item.source == helper.id and item.target == marker.id
               for item in sources.references)
    assert [(item.specifier, item.alias) for item in sources.imports] == [("math", "math")]


def test_same_scope_branch_redefinitions_keep_existing_qualified_identity_convention():
    source, _, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        if params:
            def close():
                return 1
        else:
            def close():
                return 2
        close()
        return {}
""")
    helpers = tuple(item for item in sources.symbols if item.name == "Task.run_pure.close")
    assert len(helpers) == 2 and helpers[0]._node is not helpers[1]._node
    assert helpers[0].id == helpers[1].id
    assert sources.symbol(source.path, helpers[0].name) is helpers[0]
    assert [item.target for item in _references(sources, "Task.run_pure")] == [helpers[0].id]


def test_pure_close_declared_in_try_uses_its_resolved_body_in_formal_effects():
    source, resource, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        try:
            def close():
                return 1
            close()
        except Exception:
            pass
        return {}
""")
    context = RuleContext(subject={"kind": "node", "definition_id": resource.definition_id}, target="python",
        facts={"source_context": sources, "node_definitions": (), "source_owners": ()})
    result = no_side_effects(context, {}, {"effect_scope": "none"})
    assert result.state == "completed"
    assert result.findings == (), result.findings


def test_unrelated_object_close_is_not_resolved_by_the_helpers_name():
    source, resource, sources = _context("""class Task:
    def run_pure(self, inputs, params):
        try:
            def close():
                return 1
        except Exception:
            pass
        value = {}
        value.close()
        return {}
""")
    call = next(item for item in ast.walk(source._tree) if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute) and item.func.attr == "close")
    assert (call.lineno, call.col_offset + 1) not in sources.resolved_function_calls(source.path)
    context = RuleContext(subject={"kind": "node", "definition_id": resource.definition_id}, target="python",
        facts={"source_context": sources, "node_definitions": (), "source_owners": ()})
    result = no_side_effects(context, {}, {"effect_scope": "none"})
    assert result.findings == (), result.findings
