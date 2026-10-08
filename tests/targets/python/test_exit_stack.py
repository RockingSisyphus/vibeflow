"""Source analysis and actual CLI controls for deferred stack cleanup."""

import ast

import pytest

from sandbox.python.exit_stack.probe import CASES, observe
from vibeflow.targets.python.quality.source_analysis.exit_stacks import analyze_exit_stacks


@pytest.fixture(scope="module")
def observation(tmp_path_factory):
    report = observe(tmp_path_factory.mktemp("exit-stack"))
    return {item["id"]: item for item in report["cases"]}


@pytest.mark.parametrize("case_id", [case[0] for case in CASES])
def test_formal_cli_case(observation, case_id):
    case = observation[case_id]
    assert case["matched"], case
    if not case["expected_allowed"]:
        target = next(item for item in case["validate"]["diagnostics"] if item["code"] == case["expected_code"])
        assert target["severity"] == "error"
        if case_id == "readonly_deepcopy":
            # Provider execution failure has no fabricated source coordinates.
            assert "mappingproxy" in target["message"]
        else:
            assert target["source_location"]["path"].endswith(".py")
            assert target["source_location"]["line"] > 0
    if "run" in case:
        assert "probe.defaults" in case["run"]["executed_node_types"]
    if case_id == "node_file":
        assert any("file.close" in item["message"] for item in case["validate"]["diagnostics"])


def test_analysis_preserves_ast_and_callback_location():
    tree = ast.parse('''from contextlib import ExitStack
def compute():
    with ExitStack() as stack:
        stack.callback(open, "output", "w")
        stack.close()
''')
    before = ast.dump(tree, include_attributes=True)
    facts = analyze_exit_stacks(tree)
    calls = [item for item in ast.walk(tree) if isinstance(item, ast.Call)]
    registration = next(item for item in calls if isinstance(item.func, ast.Attribute) and item.func.attr == "callback")
    deferred = facts.deferred[id(registration)]
    assert deferred.func.id == "open"
    assert deferred.lineno == registration.lineno
    assert len(facts.closes) == 1
    assert ast.dump(tree, include_attributes=True) == before
    with pytest.raises(TypeError):
        facts.deferred[0] = deferred


@pytest.mark.parametrize("write", ["stack = get_connection()", "ExitStack = get_factory(); stack = ExitStack()"])
def test_unknown_assignments_do_not_authorize_close(write):
    tree = ast.parse('from contextlib import ExitStack\ndef compute():\n    stack = ExitStack()\n    ' + write + '\n    stack.close()\n')
    assert not analyze_exit_stacks(tree).closes
