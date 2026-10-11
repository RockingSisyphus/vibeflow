"""Target analysis borrows ASTs while public rule views stay isolated."""

import ast
from dataclasses import replace

import pytest

from tests.fixtures.support.declarations import node_declaration
from vibeflow.core.rules import RuleContext
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
from vibeflow.targets.python.rules.plugin import builtin_plugin
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import (
    PythonSourceFile, PythonSourceNode, PythonSymbol, build_python_source_context,
)


def _sources():
    path = "/project/implementations.py"
    helper_path = "/project/shared.py"
    descriptors = tuple(node_declaration(NodeDescriptor(type_key='test.' + name.lower(), display_name=name, description='Checks an implementation.', version='1', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor()) for name in ("First", "Second"))
    files = (
        PythonSourceFile.parse(path, "implementations", '''from math import sqrt, ceil
from shared import announce
def local(value):
    return sqrt(value)
class Parent:
    def _calculate(self, value):
        return local(value)
class First(Parent):
    @staticmethod
    def _identity(value):
        return value
    def run_pure(self, inputs, params):
        announce(inputs["value"])
        return {"value": self._calculate(inputs["value"])}
class Second:
    def run_pure(self, inputs, params):
        announce(inputs["value"])
        return {"value": ceil(inputs["value"])}
'''),
        PythonSourceFile.parse(helper_path, "shared", '''def announce(value):
    print(value)
    return value
'''),
    )
    nodes = tuple(PythonSourceNode(descriptor, path, name) for descriptor, name in zip(descriptors, ("First", "Second")))
    return build_python_source_context(nodes, files)


def _context(sources, kind="node", name="First"):
    node = next(item for item in sources.nodes if item.symbol == name)
    identity = node.type_key if kind == "node" else "test.resource"
    owners = tuple({"kind":kind, "id":identity, "path":file.path,
        "role":"entry" if file.path == node.path else "support",
        "symbol":name if file.path == node.path else "", "base_libs":[], "dependencies":[]}
        for file in sources.files)
    return RuleContext(facts={"source_context":sources, "resource_source_file":sources.file(node.path),
        "base_lib_file":sources.file(node.path), "resource_symbol":name, "source_owners":owners,
        "node_catalog":tuple(item.descriptor for item in sources.nodes)},
        subject={"kind":kind, "id":identity, "type_key":identity})


def _ast_snapshot(sources):
    return tuple((file.path, ast.dump(file._tree, include_attributes=True),
        tuple(tuple(vars(node)) for node in ast.walk(file._tree))) for file in sources.files)


def _reject_public_views(monkeypatch):
    def unavailable(*args):
        pytest.fail("built-in analysis must borrow the Target AST, not copy a public view")
    monkeypatch.setattr(PythonSourceFile, "tree", property(unavailable))
    monkeypatch.setattr(PythonSymbol, "node", property(unavailable))
    from vibeflow.targets.python.quality.source_context import PythonSourceContext
    monkeypatch.setattr(PythonSourceContext, "implementation_tree", unavailable)


@pytest.mark.parametrize("kind", ("node", "base_lib", "plugin", "plugin_declaration"))
def test_builtins_preserve_all_target_asts_without_public_copies(monkeypatch, kind):
    sources = _sources()
    before = _ast_snapshot(sources)
    context = _context(sources, kind)
    handlers = {key:value for (kind,key),value in builtin_plugin().bindings().items() if kind == "rule"}
    selected = ["vibeflow.import_side_effects", "vibeflow.maintainability",
        "vibeflow.implementation.base_lib", "vibeflow.implementation.dependency_chain"]
    if kind != "plugin_declaration":
        selected.append("vibeflow.no_side_effects")
    if kind in {"node", "plugin"}:
        selected.append("vibeflow.node_interface")
    if kind == "node":
        selected.append("vibeflow.implementation.node")
    _reject_public_views(monkeypatch)
    for rule_id in selected:
        first = handlers[rule_id](context, {}, {})
        second = handlers[rule_id](context, {}, {})
        assert first.to_dict() == second.to_dict()
        assert _ast_snapshot(sources) == before, rule_id


def test_public_implementation_projection_is_deeply_isolated_and_symbol_specific():
    sources = _sources()
    path = sources.nodes[0].path
    before = _ast_snapshot(sources)
    first = sources.implementation_tree(path, "First")
    second = sources.implementation_tree(path, "Second")
    assert {item.name for item in first.body if isinstance(item, ast.ClassDef)} == {"First"}
    assert {item.name for item in second.body if isinstance(item, ast.ClassDef)} == {"Second"}
    assert "local" not in {item.name for item in second.body if isinstance(item, ast.FunctionDef)}
    expected = ast.dump(first, include_attributes=True)
    first_class = next(item for item in first.body if isinstance(item, ast.ClassDef))
    first_class.body[0].args.args[0].arg = "changed"
    first_class.body[-1].body.clear()
    first.body[0].names[0].name = "changed_import"
    source_view = sources.file(path).tree
    source_view.body.clear()
    sources.symbol(path, "Second").node.body[-1].body.clear()
    assert _ast_snapshot(sources) == before
    assert ast.dump(sources.implementation_tree(path, "First"), include_attributes=True) == expected
    private = sources._analysis._implementation_tree(sources, path, "First")
    assert private is sources._analysis._implementation_tree(sources, path, "First")
    assert private is not sources._analysis._implementation_tree(sources, path, "Second")
    assert sources.implementation_tree(path, "missing") is None
    full = sources.implementation_tree(path, "")
    full.body.clear()
    assert _ast_snapshot(sources) == before


def test_metrics_cache_hits_skip_projection_and_shared_file_remeasurement(monkeypatch):
    from vibeflow.targets.python.quality import analysis_metrics
    sources = _sources()
    first, second = _context(sources, "base_lib", "First"), _context(sources, "base_lib", "Second")
    calls = []
    original = analysis_metrics.measure_tree
    def measure(*args, **kwargs):
        calls.append(args[1])
        return original(*args, **kwargs)
    monkeypatch.setattr(analysis_metrics, "measure_tree", measure)
    _reject_public_views(monkeypatch)
    analysis = PythonSourceAnalysis()
    measured = analysis.measurements(first)
    assert len(calls) == 2  # Selected implementation and the one shared helper file.
    def no_projection(*args):
        pytest.fail("a metric cache hit must not construct an implementation projection")
    with monkeypatch.context() as patch:
        patch.setattr(sources._analysis, "_implementation_tree", no_projection)
        assert analysis.measurements(first) is measured
    assert len(calls) == 2
    analysis.measurements(second)
    assert len(calls) == 3  # A different export is measured; the shared helper is reused.
    fresh = replace(sources)
    assert fresh._analysis is not sources._analysis
    analysis.measurements(_context(fresh, "base_lib", "First"))
    assert len(calls) == 5


@pytest.mark.parametrize("kind", ("node", "base_lib", "plugin"))
def test_borrowed_shared_helpers_do_not_merge_effect_permissions(kind):
    sources = _sources()
    before = _ast_snapshot(sources)
    first = _context(sources, kind, "First")
    second = _context(sources, kind, "Second")
    allowed = no_side_effects(first, {}, {"effect_scope":"terminal"})
    rejected = no_side_effects(second, {}, {"effect_scope":"none"})
    assert not any("print" in item.message for item in allowed.findings)
    assert any("print" in item.message and item.source_location["path"] == "/project/shared.py"
        for item in rejected.findings)
    assert no_side_effects(second, {}, {"effect_scope":"none"}).to_dict() == rejected.to_dict()
    assert _ast_snapshot(sources) == before
