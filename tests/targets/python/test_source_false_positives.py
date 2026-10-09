"""Real selected-plugin CLI regressions for source binding and inherited entrypoints."""

import ast

import pytest

from tests.fixtures.python.source_false_positives.probe import CASES, observe
from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context


@pytest.fixture(scope="module")
def observation(tmp_path_factory):
    report = observe(tmp_path_factory.mktemp("source-false-positives"))
    return {item["id"]: item for item in report["cases"]}


@pytest.mark.parametrize("case_id", [case[0] for case in CASES])
def test_formal_cli_case(observation, case_id):
    case = observation[case_id]
    assert case["matched"], case
    if not case["expected_allowed"]:
        target = next(item for item in case["validate"]["diagnostics"] if item["code"] == case["expected_code"])
        assert target["severity"] == "error"
        assert target["source_location"]["path"].endswith(".py")
        assert target["source_location"]["line"] > 0
    if case_id in {"inherited_bad_signature", "inherited_async"}:
        # Point to the actual parent method, rather than the derived class.
        assert target["source_location"]["line"] == 3


def test_source_members_follow_c3_and_preserve_ast():
    file = PythonSourceFile.parse("/project/nodes.py", "nodes", '''
class A:
    def run_pure(self, inputs, params):
        return {}
class B(A):
    pass
class C(A):
    def run_pure(self, inputs, params):
        return {"selected": True}
class D(B, C):
    pass
class Shadow(A):
    run_pure = None
''')
    sources = build_python_source_context((), (file,))
    before = ast.dump(file.tree)
    assert sources.class_members(sources.symbol(file.path, "D"))["run_pure"].name == "C.run_pure"
    assert "run_pure" not in sources.class_members(sources.symbol(file.path, "Shadow"))
    assert ast.dump(file.tree) == before
    with pytest.raises(TypeError):
        sources.class_members(sources.symbol(file.path, "D"))["run_pure"] = None


@pytest.mark.parametrize("text", ["class A(A):\n    pass\n", '''
class A:
    pass
class B:
    pass
class X(A, B):
    pass
class Y(B, A):
    pass
class Z(X, Y):
    pass
'''])
def test_unresolvable_mro_is_real_failure_without_import(text):
    file = PythonSourceFile.parse("/project/invalid.py", "invalid", text)
    sources = build_python_source_context((), (file,))
    with pytest.raises(ValueError, match="class inheritance"):
        sources.class_members(sources.symbol(file.path, "A" if text.startswith("class A(A)") else "Z"))
